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


DEMO = {'correo': 'usuario@sedati.example', 'contrasena': 'Sedati2026*'}


class BaseApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        cls.api = nueva_api(cls._dir.name)
        cls.token = None
        _, cat = cls.pedir('GET', '/catalogo')
        cls.catalogo = cat
        cls.ids = {s['codigo']: s['id'] for c in cat['categorias'] for r in c['ramas'] for s in r['sintomas']}
        estado, datos = cls.pedir('POST', '/auth/ingresar', DEMO)
        assert estado == 200, datos
        cls.token = datos['_sesion']['token']

    @classmethod
    def tearDownClass(cls):
        cls.api.fabrica.cerrar()
        cls._dir.cleanup()

    @classmethod
    def pedir(cls, metodo, ruta, cuerpo=None, consulta=None, token=None):
        """Petición con el token de la cuenta de demostración (token='' la envía sin sesión)."""
        token = cls.token if token is None else token
        cabeceras = {'Authorization': f'Bearer {token}'} if token else {}
        return cls.api.atender(metodo, f'/api{ruta}', cuerpo, cabeceras, consulta)

    def ok(self, metodo, ruta, cuerpo=None, consulta=None, token=None):
        estado, datos = self.pedir(metodo, ruta, cuerpo, consulta, token)
        self.assertEqual(estado, 200, datos)
        return datos

    def crear_cuenta(self, nombre, correo, contrasena='Clave1234'):
        datos = self.ok('POST', '/auth/registro', {'nombre': nombre, 'correo': correo, 'contrasena': contrasena},
                        token='')
        return datos['_sesion']['token']


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

    def test_arbol_completo_de_si_y_no(self):
        """Las 22 ramas de la figura tienen su pregunta de Sí / No, sus detalles y las causas de cada hoja."""
        ramas = [r for c in self.catalogo['categorias'] for r in c['ramas']]
        self.assertEqual(len(ramas), 22)
        hojas = []

        def recorrer(n):
            self.assertTrue(n['pregunta'].startswith('¿') and n['pregunta'].endswith('?'), n['pregunta'])
            for e in n['si'] + n['no']:
                self.assertIn(e['escala'], ('SI', 'NO'))
            if n['hijos']:
                for h in n['hijos']:
                    recorrer(h)
            else:
                hojas.append(n)
        for r in ramas:
            self.assertGreaterEqual(len(r['nodo']['hijos']), 2, r['codigo'])
            recorrer(r['nodo'])
        self.assertEqual(len(hojas), 47)          # B1 y F1 tienen un cuarto nivel
        self.assertTrue(all(len(h['causas']) == 3 for h in hojas))
        c = self.catalogo['categorias'][2]
        self.assertEqual([r['nodo']['pregunta'] for r in c['ramas']],
                         ['¿El sistema operativo no inicia?', '¿El equipo está demasiado lento?',
                          '¿Hay errores después de una actualización?'])

    def test_recorrido_hasta_una_hoja_y_luego_el_motor(self):
        """C → «el sistema operativo no inicia» Sí → «no bootable» No → «bucle de reparación» Sí: el motor sigue
        con preguntas graduadas y no repite lo que ya se respondió en el árbol."""
        c1 = self.catalogo['categorias'][2]['ramas'][0]['nodo']
        no_bootable, bucle = c1['hijos']
        evid = c1['si'] + no_bootable['no'] + bucle['si']
        sintomas = [e['evidencia_id'] for e in evid if e['escala'] == 'SI']
        respuestas = [{'evidencia_id': e['evidencia_id'], 'escala': 'NO'} for e in evid if e['escala'] == 'NO']
        self.assertEqual(sintomas, [self.ids['E-034']])
        d = self.ok('POST', '/diagnostico', {'categoria': 'C', 'sintomas': sintomas, 'respuestas': respuestas})
        self.assertEqual(d['pregunta']['evidencia']['codigo'], 'E-039')   # ¿actualización en las últimas 72 horas?
        respondidas = {r['evidencia']['codigo'] for r in d['respuestas']}
        self.assertEqual(respondidas, {'E-034', 'E-035'})
        self.assertEqual(len(d['top']), 5)

    def test_no_hay_rutas_de_administracion(self):
        for metodo, ruta in [('GET', '/usuarios'), ('GET', '/incidentes'), ('POST', '/conocimiento/granulos'),
                             ('GET', '/indicadores')]:
            self.assertEqual(self.pedir(metodo, ruta, {})[0], 404, ruta)


class PruebasAcceso(BaseApi):
    def test_ingresar_con_la_cuenta_demo(self):
        d = self.ok('POST', '/auth/ingresar', {'correo': '  USUARIO@sedati.example ', 'contrasena': 'Sedati2026*'},
                    token='')
        self.assertEqual(d['usuario']['correo'], 'usuario@sedati.example')
        self.assertNotIn('contrasena_hash', d['usuario'])
        s = self.ok('GET', '/auth/sesion', token=d['_sesion']['token'])
        self.assertEqual(s['usuario']['nombre'], 'Usuario de demostración')
        self.assertIn('token', s['_sesion'])            # cada respuesta autenticada renueva el token

    def test_credenciales_incorrectas(self):
        estado, datos = self.pedir('POST', '/auth/ingresar', {'correo': DEMO['correo'], 'contrasena': 'otra1234'},
                                   token='')
        self.assertEqual(estado, 401)
        self.assertEqual(datos['error'], 'Correo o contraseña incorrectos.')
        estado, datos = self.pedir('POST', '/auth/ingresar', {'correo': 'nadie@x.co', 'contrasena': 'otra1234'},
                                   token='')
        self.assertEqual((estado, datos['error']), (401, 'Correo o contraseña incorrectos.'))
        self.assertEqual(self.pedir('POST', '/auth/ingresar', {}, token='')[0], 401)
        # el ingreso correcto reinicia el contador de intentos
        self.ok('POST', '/auth/ingresar', DEMO, token='')

    def test_registro_y_validaciones(self):
        token = self.crear_cuenta('  Pedro   Pérez ', 'Pedro.Perez@Correo.co')
        u = self.ok('GET', '/auth/sesion', token=token)['usuario']
        self.assertEqual((u['nombre'], u['correo']), ('Pedro Pérez', 'pedro.perez@correo.co'))
        self.ok('POST', '/auth/ingresar', {'correo': 'pedro.perez@correo.co', 'contrasena': 'Clave1234'}, token='')
        casos = [({'nombre': 'Otra', 'correo': 'PEDRO.perez@correo.co', 'contrasena': 'Clave1234'}, 409),
                 ({'nombre': 'X', 'correo': 'x@correo.co', 'contrasena': 'Clave1234'}, 400),
                 ({'nombre': 'Ana', 'correo': 'sin-arroba', 'contrasena': 'Clave1234'}, 400),
                 ({'nombre': 'Ana', 'correo': 'ana@correo.co', 'contrasena': 'corta1'}, 400),
                 ({'nombre': 'Ana', 'correo': 'ana@correo.co', 'contrasena': 'sololetras'}, 400),
                 ({'nombre': 'Ana', 'correo': 'ana@correo.co', 'contrasena': 12345678}, 400)]
        for cuerpo, esperado in casos:
            self.assertEqual(self.pedir('POST', '/auth/registro', cuerpo, token='')[0], esperado, cuerpo)
        fila = self.api.fabrica.conexion_trx.uno('SELECT contrasena_hash FROM usuario WHERE correo = ?',
                                                 ('pedro.perez@correo.co',))
        self.assertTrue(fila['contrasena_hash'].startswith('pbkdf2_sha256$'))
        self.assertNotIn('Clave1234', fila['contrasena_hash'])

    def test_bloqueo_tras_cinco_intentos(self):
        self.crear_cuenta('Lucía Mora', 'lucia@correo.co')
        malo = {'correo': 'lucia@correo.co', 'contrasena': 'Incorrecta9'}
        for _ in range(4):
            self.assertEqual(self.pedir('POST', '/auth/ingresar', malo, token='')[1]['error'],
                             'Correo o contraseña incorrectos.')
        estado, datos = self.pedir('POST', '/auth/ingresar', malo, token='')
        self.assertEqual(estado, 401)
        self.assertIn('bloqueada', datos['error'])
        estado, datos = self.pedir('POST', '/auth/ingresar', {'correo': 'lucia@correo.co', 'contrasena': 'Clave1234'},
                                   token='')
        self.assertEqual(estado, 401)                    # ni con la contraseña correcta mientras dure el bloqueo
        self.assertIn('bloqueada', datos['error'])

    def test_rutas_protegidas_exigen_sesion(self):
        e = self.ids['E-001']
        for metodo, ruta, cuerpo in [('POST', '/diagnostico', {'sintomas': [e]}), ('POST', '/consultas', {'sintomas': [e]}),
                                     ('GET', '/consultas', None), ('GET', '/consultas/1', None),
                                     ('GET', '/consultas/1/informe', None), ('GET', '/auth/sesion', None)]:
            self.assertEqual(self.pedir(metodo, ruta, cuerpo, token='')[0], 401, ruta)
            self.assertEqual(self.pedir(metodo, ruta, cuerpo, token='abc.def')[0], 401, ruta)
            self.assertEqual(self.pedir(metodo, ruta, cuerpo, token='añ.ñ')[0], 401, ruta)
        alterado = self.token[:-2] + ('AA' if not self.token.endswith('AA') else 'BB')
        self.assertEqual(self.pedir('GET', '/consultas', token=alterado)[0], 401)
        for ruta in ['/salud', '/catalogo', '/conocimiento/hipotesis', '/conocimiento/evidencias']:
            self.assertEqual(self.pedir('GET', ruta, token='')[0], 200, ruta)

    def test_sesion_vencida(self):
        from sedati.negocio.seguridad import FirmadorSesion
        f = FirmadorSesion('clave')
        token, exp = f.emitir(1, ahora=1000)
        self.assertEqual(f.leer(token, ahora=exp - 1)['uid'], 1)
        self.assertIsNone(f.leer(token, ahora=exp + 1))
        self.assertIsNone(FirmadorSesion('otra clave').leer(token, ahora=exp - 1))
        vencido, _ = self.api.acceso._firmador.emitir(1, ahora=0)
        self.assertEqual(self.pedir('GET', '/consultas', token=vencido)[0], 401)

    def test_cada_cuenta_ve_solo_sus_diagnosticos(self):
        cuerpo = {'categoria': 'A', 'sintomas': [self.ids['E-001']], 'respuestas': []}
        de_demo = self.ok('POST', '/consultas', cuerpo)['consulta_id']
        otro = self.crear_cuenta('Carlos Ruiz', 'carlos@correo.co')
        suyo = self.ok('POST', '/consultas', cuerpo, token=otro)
        self.assertEqual(suyo['nombre'], 'Carlos Ruiz')
        self.assertEqual([c['id'] for c in self.ok('GET', '/consultas', token=otro)['consultas']], [suyo['consulta_id']])
        self.assertNotIn(suyo['consulta_id'], [c['id'] for c in self.ok('GET', '/consultas')['consultas']])
        self.assertEqual(self.pedir('GET', f'/consultas/{de_demo}', token=otro)[0], 404)
        self.assertEqual(self.pedir('GET', f'/consultas/{de_demo}/informe', token=otro)[0], 404)


class PruebasDiagnostico(BaseApi):
    def test_diagnostico_sin_estado_llega_a_la_hipotesis(self):
        """Caso «impresora con IP cambiada»: el cliente envía todas las respuestas en cada petición."""
        verdad = {'IMPRESORA_RESPONDE_RED': 'NO', 'E-081': 'SI', 'E-082': 'NO', 'E-087': 'NO'}
        respuestas = []
        for _ in range(20):
            d = self.ok('POST', '/diagnostico', {'categoria': 'E', 'sintomas': [self.ids['E-079']],
                                                 'respuestas': respuestas})
            q = d['pregunta']
            if d['motivo_conclusion'] or q is None:
                break
            ev = self.api.fabrica.conocimiento().evidencias_por_ids([q['evidencia']['id']])[0]
            escala = verdad.get(ev['codigo']) or verdad.get(ev['variable']) or 'NO_SE'
            respuestas.append({'evidencia_id': q['evidencia']['id'], 'escala': escala})
        self.assertEqual(d['top'][0]['hipotesis']['codigo'], 'HIP-20')
        self.assertEqual(len(d['top']), 5)
        self.assertEqual((d['nombre'], d['categoria']), ('Usuario de demostración', 'E'))
        self.assertAlmostEqual(sum(r['probabilidad'] for r in d['top']), 1.0, delta=0.05)
        self.assertTrue(d['traza'])
        self.assertEqual(len(d['evolucion']), len(respuestas) + 1)
        json.dumps(d)   # todo el estado es serializable

    def test_guardar_a_nombre_de_la_cuenta_y_reconstruir(self):
        token = self.crear_cuenta('  María   López ', 'maria.lopez@correo.co')
        cuerpo = {'nombre': 'Otro nombre', 'categoria': 'A', 'sintomas': [self.ids['E-001']], 'respuestas': []}
        d = self.ok('POST', '/diagnostico', cuerpo, token=token)
        cuerpo['respuestas'] = [{'evidencia_id': d['pregunta']['evidencia']['id'], 'escala': 'SI'}]
        guardada = self.ok('POST', '/consultas', cuerpo, token=token)
        self.assertTrue(guardada['finalizada'])
        cid = guardada['consulta_id']
        rec = self.ok('GET', f'/consultas/{cid}', token=token)
        self.assertEqual([r['hipotesis']['id'] for r in rec['top']], [r['hipotesis']['id'] for r in guardada['top']])
        self.assertEqual((rec['nombre'], rec['categoria']), ('María López', 'A'))   # el nombre sale de la cuenta
        mias = self.ok('GET', '/consultas', token=token)['consultas']
        self.assertEqual([c['id'] for c in mias], [cid])
        self.assertEqual((mias[0]['nombre_usuario'], mias[0]['categoria_codigo']), ('María López', 'A'))
        self.assertIsNotNone(mias[0]['usuario_id'])
        informe = self.ok('GET', f'/consultas/{cid}/informe', token=token)['informe']
        self.assertIn('SEDATI - Informe de diagnóstico', informe)
        self.assertIn('Consultó: María López', informe)

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
                self.assertEqual(tablas, {'escala_respuesta', 'usuario', 'diagnostico', 'incidente_evidencia',
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
                ingreso = {'rawPath': '/api/auth/ingresar', 'requestContext': {'http': {'method': 'POST'}},
                           'headers': {'content-type': 'application/json'}, 'body': json.dumps(DEMO)}
                r = lf.lambda_handler(ingreso, None)
                self.assertEqual(r['statusCode'], 200, r['body'])
                token = json.loads(r['body'])['_sesion']['token']
                evento = {'rawPath': '/api/diagnostico', 'requestContext': {'http': {'method': 'POST'}},
                          'headers': {'authorization': f'Bearer {token}'}, 'body': json.dumps({'sintomas': [88]}),
                          'isBase64Encoded': False}
                self.assertEqual(lf.lambda_handler(dict(evento, headers={}), None)['statusCode'], 401)
                r = lf.lambda_handler(evento, None)
                self.assertEqual(r['statusCode'], 200)
                self.assertIn('Authorization', r['headers']['Access-Control-Allow-Headers'])
                self.assertIsNotNone(json.loads(r['body'])['pregunta'])
                self.assertEqual(lf.lambda_handler(dict(evento, body='{no es json'), None)['statusCode'], 400)
                previa = {'rawPath': '/api/catalogo', 'requestContext': {'http': {'method': 'OPTIONS'}}}
                self.assertEqual(lf.lambda_handler(previa, None)['statusCode'], 204)
                consulta = {'rawPath': '/api/consultas', 'requestContext': {'http': {'method': 'GET'}},
                            'headers': {'Authorization': f'Bearer {token}'}}
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
