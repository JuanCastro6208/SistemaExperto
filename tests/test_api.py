"""Pruebas del servicio web (API REST) y del handler de AWS Lambda.

    python -m unittest discover -s tests -v

Con la variable SEDATI_PRUEBAS_MYSQL=host:puerto:usuario:contraseña las mismas pruebas corren contra
un servidor MySQL 8 (las bases sedati_kb y sedati_trx se reinstalan antes de cada clase).
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from sedati.configuracion import Configuracion, ParametrosMotor, cargar_configuracion  # noqa: E402
from sedati.servicio import ApiSEDATI  # noqa: E402

MYSQL = os.environ.get('SEDATI_PRUEBAS_MYSQL')


def nueva_api(directorio):
    if MYSQL:
        host, puerto, usuario, contrasena = MYSQL.split(':')
        sys.path.insert(0, str(RAIZ / 'bd'))
        import instalar_mysql
        cx = instalar_mysql.conectar(host, int(puerto), usuario, contrasena)
        for s in instalar_mysql.SCRIPTS[:4]:
            instalar_mysql.ejecutar_script(cx, s, mostrar=False)
        cx.close()
        conf = replace(cargar_configuracion(), motor_bd='mysql',
                       mysql={'host': host, 'port': int(puerto), 'user': usuario, 'password': contrasena,
                              'base_kb': 'sedati_kb', 'base_trx': 'sedati_trx'})
        return ApiSEDATI(conf)
    conf = Configuracion('sqlite', Path(directorio) / 'kb.db', Path(directorio) / 'trx.db', {}, ParametrosMotor())
    return ApiSEDATI(conf)


class BaseApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        cls.api = nueva_api(cls._dir.name)
        _, cat = cls.pedir('GET', '/catalogo')
        cls.catalogo = cat
        cls.ids = {s['codigo']: s['id'] for c in cat['categorias'] for r in c['ramas'] for s in r['sintomas']}

    @classmethod
    def tearDownClass(cls):
        cls.api.fabrica.cerrar()
        cls._dir.cleanup()

    @classmethod
    def pedir(cls, metodo, ruta, cuerpo=None, consulta=None):
        return cls.api.atender(metodo, f'/api{ruta}', cuerpo, {}, consulta)

    def ok(self, metodo, ruta, cuerpo=None, consulta=None):
        estado, datos = self.pedir(metodo, ruta, cuerpo, consulta)
        self.assertEqual(estado, 200, datos)
        return datos


class PruebasArbol(BaseApi):
    def test_catalogo_sigue_el_orden_del_arbol(self):
        cat = self.catalogo
        self.assertEqual([c['codigo'] for c in cat['categorias']], list('ABCDEFG'))
        energia = cat['categorias'][0]
        self.assertEqual(energia['nombre'], 'Energía y arranque')
        self.assertEqual([r['nombre'] for r in energia['ramas']],
                         ['Equipo no enciende', 'Equipo se apaga solo', 'Reinicios inesperados'])
        self.assertEqual([o['codigo'] for o in cat['escala']], ['SI', 'PROB_SI', 'NO_SE', 'PROB_NO', 'NO'])
        self.assertEqual(cat['estadisticas']['reglas'], 88)

    def test_no_hay_rutas_de_cuentas_ni_de_administracion(self):
        for metodo, ruta in [('POST', '/auth/ingresar'), ('GET', '/usuarios'), ('GET', '/incidentes'),
                             ('POST', '/conocimiento/granulos'), ('GET', '/indicadores')]:
            self.assertEqual(self.pedir(metodo, ruta, {})[0], 404, ruta)


class PruebasDiagnostico(BaseApi):
    def test_diagnostico_sin_estado_llega_a_la_hipotesis(self):
        """Caso «impresora con IP cambiada»: el cliente envía todas las respuestas en cada petición."""
        verdad = {'IMPRESORA_RESPONDE_RED': 'NO', 'E-081': 'SI', 'E-082': 'NO', 'E-087': 'NO'}
        respuestas = []
        for _ in range(20):
            d = self.ok('POST', '/diagnostico', {'nombre': 'Ana', 'categoria': 'E', 'sintomas': [self.ids['E-079']],
                                                 'respuestas': respuestas})
            q = d['pregunta']
            if d['motivo_conclusion'] or q is None:
                break
            ev = self.api.fabrica.conocimiento().evidencias_por_ids([q['evidencia']['id']])[0]
            escala = verdad.get(ev['codigo']) or verdad.get(ev['variable']) or 'NO_SE'
            respuestas.append({'evidencia_id': q['evidencia']['id'], 'escala': escala})
        self.assertEqual(d['top'][0]['hipotesis']['codigo'], 'HIP-20')
        self.assertEqual(len(d['top']), 5)
        self.assertEqual((d['nombre'], d['categoria']), ('Ana', 'E'))
        self.assertAlmostEqual(sum(r['probabilidad'] for r in d['top']), 1.0, delta=0.05)
        self.assertTrue(d['traza'])
        self.assertEqual(len(d['evolucion']), len(respuestas) + 1)
        json.dumps(d)   # todo el estado es serializable

    def test_guardar_con_el_nombre_y_reconstruir(self):
        cuerpo = {'nombre': '  María   López ', 'categoria': 'A', 'sintomas': [self.ids['E-001']], 'respuestas': []}
        d = self.ok('POST', '/diagnostico', cuerpo)
        cuerpo['respuestas'] = [{'evidencia_id': d['pregunta']['evidencia']['id'], 'escala': 'SI'}]
        guardada = self.ok('POST', '/consultas', cuerpo)
        self.assertTrue(guardada['finalizada'])
        cid = guardada['consulta_id']
        rec = self.ok('GET', f'/consultas/{cid}')
        self.assertEqual([r['hipotesis']['id'] for r in rec['top']], [r['hipotesis']['id'] for r in guardada['top']])
        self.assertEqual((rec['nombre'], rec['categoria']), ('María López', 'A'))
        fila = next(c for c in self.ok('GET', '/consultas')['consultas'] if c['id'] == cid)
        self.assertEqual((fila['nombre_usuario'], fila['categoria_codigo']), ('María López', 'A'))
        mias = self.ok('GET', '/consultas', consulta={'nombre': 'María López'})['consultas']
        self.assertEqual([c['id'] for c in mias], [cid])
        self.assertEqual(self.ok('GET', '/consultas', consulta={'nombre': 'Nadie'})['consultas'], [])
        informe = self.ok('GET', f'/consultas/{cid}/informe')['informe']
        self.assertIn('SEDATI - Informe de diagnóstico', informe)
        self.assertIn('Consultó: María López', informe)

    def test_guardar_exige_el_nombre(self):
        cuerpo = {'sintomas': [self.ids['E-001']], 'respuestas': []}
        estado, datos = self.pedir('POST', '/consultas', cuerpo)
        self.assertEqual(estado, 400)
        self.assertIn('nombre', datos['error'])
        self.assertEqual(self.pedir('POST', '/consultas', dict(cuerpo, nombre='   '))[0], 400)

    def test_errores(self):
        e = self.ids['E-001']
        self.assertEqual(self.pedir('POST', '/diagnostico', {'sintomas': []})[0], 400)
        self.assertEqual(self.pedir('POST', '/diagnostico', {'sintomas': ['x']})[0], 400)
        self.assertEqual(self.pedir('POST', '/diagnostico', {'sintomas': [e], 'categoria': 'Z'})[0], 400)
        self.assertEqual(self.pedir('POST', '/diagnostico', {
            'sintomas': [e], 'respuestas': [{'evidencia_id': 1, 'escala': 'TAL_VEZ'}]})[0], 400)
        self.assertEqual(self.pedir('POST', '/diagnostico', {
            'sintomas': [e], 'respuestas': [{'evidencia_id': 9999, 'escala': 'SI'}]})[0], 400)
        self.assertEqual(self.pedir('GET', '/consultas/999999')[0], 404)
        self.assertEqual(self.pedir('GET', '/no-existe')[0], 404)
        self.assertEqual(self.pedir('GET', '/diagnostico')[0], 405)

    def test_conocimiento(self):
        h = self.ok('GET', '/conocimiento/hipotesis')
        self.assertEqual(len(h['hipotesis']), 38)
        g = self.ok('GET', f"/conocimiento/hipotesis/{h['hipotesis'][0]['id']}")
        self.assertEqual(g['granulos'][0]['condiciones'][0]['conector'], 'If')
        self.assertEqual(len(self.ok('GET', '/conocimiento/evidencias')['evidencias']), 153)

    def test_la_base_impide_borrar_y_cambiar_codigos(self):
        from sedati.datos import ErrorIntegridad
        kb = self.api.fabrica.conexion_kb
        with self.assertRaises(Exception):
            kb.ejecutar('DELETE FROM granulo WHERE regla = ?', ('R-01',))
        with self.assertRaises(ErrorIntegridad):
            kb.ejecutar("UPDATE hipotesis SET codigo = 'HIP-77' WHERE id = 1")
        with self.assertRaises(Exception):
            self.api.fabrica.conexion_trx.ejecutar('DELETE FROM escala_respuesta')


class PruebasBaseAnterior(unittest.TestCase):
    @unittest.skipIf(MYSQL, 'solo aplica a SQLite')
    def test_una_base_sqlite_de_la_version_con_cuentas_se_aparta_y_se_crea_de_nuevo(self):
        with tempfile.TemporaryDirectory() as d:
            trx = Path(d) / 'trx.db'
            cx = sqlite3.connect(trx)
            cx.execute('CREATE TABLE usuario (id INTEGER PRIMARY KEY, correo TEXT)')
            cx.execute('CREATE TABLE diagnostico (id INTEGER PRIMARY KEY, registrado_por INTEGER)')
            cx.commit()
            cx.close()
            api = ApiSEDATI(Configuracion('sqlite', Path(d) / 'kb.db', trx, {}, ParametrosMotor()))
            try:
                self.assertTrue((Path(d) / 'trx.db.anterior').exists())
                tablas = {f['name'] for f in api.fabrica.conexion_trx.consultar(
                    "SELECT name FROM sqlite_master WHERE type = 'table'")}
                self.assertEqual(tablas, {'escala_respuesta', 'diagnostico', 'incidente_evidencia',
                                          'diagnostico_hipotesis'})
            finally:
                api.fabrica.cerrar()


class PruebasLambda(unittest.TestCase):
    def test_handler_api_gateway(self):
        with tempfile.TemporaryDirectory() as d:
            variables = {'SEDATI_RUTA_SQLITE_KB': str(Path(d) / 'kb.db'), 'SEDATI_RUTA_SQLITE_TRX': str(Path(d) / 'trx.db'),
                         'SEDATI_MOTOR_BD': 'sqlite'}
            anteriores = {k: os.environ.get(k) for k in variables}
            os.environ.update(variables)
            try:
                import lambda_function as lf
                lf._api = None
                evento = {'rawPath': '/api/diagnostico', 'requestContext': {'http': {'method': 'POST'}},
                          'headers': {}, 'body': json.dumps({'nombre': 'Ana', 'sintomas': [88]}),
                          'isBase64Encoded': False}
                r = lf.lambda_handler(evento, None)
                self.assertEqual(r['statusCode'], 200)
                self.assertEqual(r['headers']['Access-Control-Allow-Headers'], 'Content-Type')
                self.assertIsNotNone(json.loads(r['body'])['pregunta'])
                self.assertEqual(lf.lambda_handler(dict(evento, body='{no es json'), None)['statusCode'], 400)
                previa = {'rawPath': '/api/catalogo', 'requestContext': {'http': {'method': 'OPTIONS'}}}
                self.assertEqual(lf.lambda_handler(previa, None)['statusCode'], 204)
                consulta = {'rawPath': '/api/consultas', 'requestContext': {'http': {'method': 'GET'}},
                            'queryStringParameters': {'nombre': 'Ana'}}
                self.assertEqual(lf.lambda_handler(consulta, None)['statusCode'], 200)
                lf._api.fabrica.cerrar()
                lf._api = None
            finally:
                for k, v in anteriores.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v


if __name__ == '__main__':
    unittest.main()
