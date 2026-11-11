"""Pruebas del servicio web (API REST), de los procesos transaccionales y del handler de AWS Lambda.

    python -m unittest discover -s tests -v

Con la variable SEDATI_PRUEBAS_MYSQL=host:puerto:usuario:contraseña las mismas pruebas corren contra
un servidor MySQL 8 (las bases sedati_kb y sedati_trx se reinstalan antes de cada clase).
"""
import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from sedati.configuracion import Configuracion, ParametrosMotor, cargar_configuracion  # noqa: E402
from sedati.servicio import ApiSEDATI  # noqa: E402

CLAVE = 'Sedati2026*'
MYSQL = os.environ.get('SEDATI_PRUEBAS_MYSQL')


def nueva_api(directorio, demo=False):
    if MYSQL:
        host, puerto, usuario, contrasena = MYSQL.split(':')
        sys.path.insert(0, str(RAIZ / 'bd'))
        import instalar_mysql
        cx = instalar_mysql.conectar(host, int(puerto), usuario, contrasena)
        for s in instalar_mysql.SCRIPTS[:4]:
            instalar_mysql.ejecutar_script(cx, s, mostrar=False)
        cx.close()
        conf = replace(cargar_configuracion(), motor_bd='mysql', datos_demostracion=False,
                       mysql={'host': host, 'port': int(puerto), 'user': usuario, 'password': contrasena,
                              'base_kb': 'sedati_kb', 'base_trx': 'sedati_trx'}, secreto='prueba')
        api = ApiSEDATI(conf)
        if demo:
            from sedati.servicio.demostracion import cargar_demostracion
            cargar_demostracion(api)
        return api
    conf = Configuracion('sqlite', Path(directorio) / 'kb.db', Path(directorio) / 'trx.db', {}, ParametrosMotor(),
                         secreto='prueba', datos_demostracion=demo)
    return ApiSEDATI(conf)


class BaseApi(unittest.TestCase):
    demo = False

    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        cls.api = nueva_api(cls._dir.name, cls.demo)
        cls.admin = cls.ingresar('admin@sedati.example')
        _, cat = cls.pedir('GET', '/catalogo', token=cls.admin)
        cls.ids = {s['codigo']: s['id'] for c in cat['categorias'] for s in c['sintomas']}

    @classmethod
    def tearDownClass(cls):
        cls.api.fabrica.cerrar()
        cls._dir.cleanup()

    @classmethod
    def pedir(cls, metodo, ruta, cuerpo=None, token=None, consulta=None):
        cabeceras = {'Authorization': f'Bearer {token}'} if token else {}
        return cls.api.atender(metodo, f'/api{ruta}', cuerpo, cabeceras, consulta)

    @classmethod
    def ingresar(cls, correo, clave=CLAVE):
        estado, datos = cls.api.atender('POST', '/api/auth/ingresar', {'correo': correo, 'contrasena': clave})
        assert estado == 200, datos
        return datos['_sesion']['token']

    def ok(self, metodo, ruta, cuerpo=None, token=None, consulta=None):
        estado, datos = self.pedir(metodo, ruta, cuerpo, token or self.admin, consulta)
        self.assertEqual(estado, 200, datos)
        return datos

    def futuro(self, horas, duracion=1):
        inicio = self.api.configuracion.ahora() + timedelta(days=2, hours=horas)
        return {'inicio': inicio.strftime('%Y-%m-%d %H:%M'),
                'fin': (inicio + timedelta(hours=duracion)).strftime('%Y-%m-%d %H:%M'), 'lugar': 'Sala 2'}


class PruebasDiagnostico(BaseApi):
    def test_catalogo(self):
        cat = self.ok('GET', '/catalogo')
        self.assertEqual([o['codigo'] for o in cat['escala']], ['SI', 'PROB_SI', 'NO_SE', 'PROB_NO', 'NO'])
        self.assertEqual(cat['estadisticas']['reglas'], 88)
        self.assertIn('E-079', self.ids)

    def test_diagnostico_sin_estado_llega_a_la_hipotesis(self):
        """Caso «impresora con IP cambiada»: el cliente envía todas las respuestas en cada petición."""
        verdad = {'IMPRESORA_RESPONDE_RED': 'NO', 'E-081': 'SI', 'E-082': 'NO', 'E-087': 'NO'}
        respuestas = []
        for _ in range(20):
            d = self.ok('POST', '/diagnostico', {'sintomas': [self.ids['E-079']], 'respuestas': respuestas})
            q = d['pregunta']
            if d['motivo_conclusion'] or q is None:
                break
            ev = self.api.fabrica.conocimiento().evidencias_por_ids([q['evidencia']['id']])[0]
            escala = verdad.get(ev['codigo']) or verdad.get(ev['variable']) or 'NO_SE'
            respuestas.append({'evidencia_id': q['evidencia']['id'], 'escala': escala})
        self.assertEqual(d['top'][0]['hipotesis']['codigo'], 'HIP-20')
        self.assertEqual(len(d['top']), 5)
        self.assertAlmostEqual(sum(r['probabilidad'] for r in d['top']), 1.0, delta=0.05)
        self.assertTrue(d['traza'])
        self.assertEqual(len(d['evolucion']), len(respuestas) + 1)
        json.dumps(d)   # todo el estado es serializable

    def test_guardar_y_reconstruir_consulta_libre(self):
        cuerpo = {'sintomas': [self.ids['E-001']], 'respuestas': [], 'equipo': 'PC-01'}
        d = self.ok('POST', '/diagnostico', cuerpo)
        cuerpo['respuestas'] = [{'evidencia_id': d['pregunta']['evidencia']['id'], 'escala': 'SI'}]
        guardada = self.ok('POST', '/consultas', cuerpo)
        self.assertTrue(guardada['finalizada'])
        cid = guardada['consulta_id']
        rec = self.ok('GET', f'/consultas/{cid}')
        self.assertEqual([r['hipotesis']['id'] for r in rec['top']], [r['hipotesis']['id'] for r in guardada['top']])
        self.assertIn(cid, [c['id'] for c in self.ok('GET', '/consultas')['consultas']])
        self.assertIn('SEDATI - Informe de diagnóstico', self.ok('GET', f'/consultas/{cid}/informe')['informe'])

    def test_errores(self):
        a = self.admin
        self.assertEqual(self.pedir('POST', '/diagnostico', {'sintomas': []}, a)[0], 400)
        self.assertEqual(self.pedir('POST', '/diagnostico', {'sintomas': ['x']}, a)[0], 400)
        self.assertEqual(self.pedir('POST', '/diagnostico', {
            'sintomas': [self.ids['E-001']], 'respuestas': [{'evidencia_id': 1, 'escala': 'TAL_VEZ'}]}, a)[0], 400)
        self.assertEqual(self.pedir('POST', '/diagnostico', {
            'sintomas': [self.ids['E-001']], 'respuestas': [{'evidencia_id': 9999, 'escala': 'SI'}]}, a)[0], 400)
        self.assertEqual(self.pedir('GET', '/consultas/999999', token=a)[0], 404)
        self.assertEqual(self.pedir('GET', '/no-existe', token=a)[0], 404)
        self.assertEqual(self.pedir('GET', '/diagnostico', token=a)[0], 405)

    def test_conocimiento(self):
        h = self.ok('GET', '/conocimiento/hipotesis')
        self.assertEqual(len(h['hipotesis']), 38)
        g = self.ok('GET', f"/conocimiento/hipotesis/{h['hipotesis'][0]['id']}")
        self.assertEqual(g['granulos'][0]['condiciones'][0]['conector'], 'If')
        self.assertEqual(len(self.ok('GET', '/conocimiento/evidencias')['evidencias']), 153)


class PruebasAcceso(BaseApi):
    def test_sin_token_o_con_token_alterado(self):
        self.assertEqual(self.pedir('GET', '/incidentes')[0], 401)
        self.assertEqual(self.pedir('GET', '/incidentes', token=self.admin[:-2] + 'xx')[0], 401)
        self.assertEqual(self.pedir('GET', '/salud')[0], 200)          # pública

    def test_credenciales_invalidas_no_revelan_el_motivo(self):
        e1, d1 = self.pedir('POST', '/auth/ingresar', {'correo': 'nadie@sedati.example', 'contrasena': 'x1234567'})
        e2, d2 = self.pedir('POST', '/auth/ingresar', {'correo': 'admin@sedati.example', 'contrasena': 'x1234567'})
        self.assertEqual((e1, e2), (401, 401))
        self.assertEqual(d1['error'], d2['error'])

    def test_bloqueo_tras_cinco_intentos_y_desbloqueo(self):
        correo = 'miguel.torres@sedati.example'
        for _ in range(5):
            estado, _ = self.pedir('POST', '/auth/ingresar', {'correo': correo, 'contrasena': 'equivocada1'})
            self.assertEqual(estado, 401)
        estado, d = self.pedir('POST', '/auth/ingresar', {'correo': correo, 'contrasena': CLAVE})
        self.assertEqual(estado, 401)
        self.assertIn('bloqueada', d['error'])
        usuarios = self.ok('GET', '/usuarios')['usuarios']
        uid = next(u['id'] for u in usuarios if u['correo'] == correo)
        self.assertNotIn('contrasena_hash', usuarios[0])                  # el hash nunca sale
        self.ok('POST', f'/usuarios/{uid}/desbloquear', {})
        self.ingresar(correo)
        motivos = [b['motivo'] for b in self.ok('GET', '/usuarios/bitacora')['accesos']]
        self.assertIn('BLOQUEADA', motivos)

    def test_el_solicitante_no_accede_a_funciones_del_administrador(self):
        s = self.ingresar('solicitante@sedati.example')
        for metodo, ruta in [('GET', '/usuarios'), ('GET', '/conocimiento/hipotesis'), ('GET', '/catalogo'),
                             ('GET', '/indicadores'), ('POST', '/conocimiento/hipotesis'), ('GET', '/consultas')]:
            self.assertEqual(self.pedir(metodo, ruta, {}, s)[0], 403, ruta)

    def test_crear_cuenta_contrasena_temporal_y_cambio(self):
        datos = {'documento': '2000000099', 'nombre': 'Persona de Prueba', 'correo': 'prueba@sedati.example',
                 'rol': 'SOLICITANTE', 'dependencia_id': 1}
        creada = self.ok('POST', '/usuarios', datos)
        temporal = creada['contrasena_temporal']
        self.assertEqual(self.pedir('POST', '/usuarios', datos, self.admin)[0], 409)     # documento repetido
        token = self.ingresar('prueba@sedati.example', temporal)
        self.assertTrue(self.ok('GET', '/auth/sesion', token=token)['usuario']['debe_cambiar_contrasena'])
        self.assertEqual(self.pedir('GET', '/incidentes', token=token)[0], 403)     # primero cambia la clave
        self.ok('POST', '/auth/contrasena', {'actual': temporal, 'nueva': 'NuevaClave2026'}, token)
        self.ingresar('prueba@sedati.example', 'NuevaClave2026')
        self.ok('POST', f"/usuarios/{creada['usuario']['id']}/estado", {'activo': False})
        self.assertEqual(self.pedir('POST', '/auth/ingresar', {'correo': 'prueba@sedati.example',
                                                               'contrasena': 'NuevaClave2026'})[0], 401)


class PruebasAtencion(BaseApi):
    def reportar(self, token, inventario='PC-PRUEBA-01', descripcion='El equipo no enciende al oprimir el botón.'):
        return self.ok('POST', '/incidentes', {'inventario': inventario, 'tipo_equipo_id': 1, 'ubicacion': 'Sala 2',
                                               'descripcion': descripcion}, token)['incidente']

    def test_flujo_completo_hasta_el_cierre_en_segunda_ronda(self):
        s = self.ingresar('solicitante@sedati.example')
        inc = self.reportar(s)
        self.assertEqual(inc['estado'], 'ABIERTO')
        self.assertRegex(inc['codigo'], r'^INC-\d{4}-\d{6}$')
        iid = inc['id']
        # el solicitante aún no puede pedir cita (sin responsable); el administrador toma el caso
        self.assertEqual(self.pedir('POST', f'/incidentes/{iid}/citas', self.futuro(0), s)[0], 409)
        self.ok('POST', f'/incidentes/{iid}/tomar', {})
        cita = self.ok('POST', f'/incidentes/{iid}/citas', self.futuro(0), s)['cita']
        self.assertEqual(self.pedir('POST', f'/incidentes/{iid}/citas', self.futuro(0.5), self.admin)[0], 409)  # solape
        self.ok('POST', f"/citas/{cita['id']}", self.futuro(3), s)                                    # reprograma
        self.ok('POST', f"/citas/{cita['id']}/estado", {'estado': 'ATENDIDA'})
        # ronda 1: el técnico confirma la fuente y la solución no funciona
        cuerpo = {'sintomas': [self.ids['E-001']], 'respuestas': []}
        r1 = self.ok('POST', f'/incidentes/{iid}/diagnosticos', cuerpo)
        self.assertEqual(r1['ronda'], 1)
        det = self.ok('GET', f'/incidentes/{iid}')
        self.assertEqual(det['incidente']['estado'], 'EN_DIAGNOSTICO')
        self.assertEqual(det['incidente']['categoria_codigo'], 'A')
        propuestas = det['rondas'][0]['hipotesis']
        primera = propuestas[0]
        self.ok('POST', f"/propuestas/{primera['id']}/decision", {'estado': 'CONFIRMADA'})
        self.assertEqual(self.pedir('POST', f"/propuestas/{propuestas[1]['id']}/decision",
                                    {'estado': 'CONFIRMADA'}, self.admin)[0], 409)               # una sola confirmada
        self.ok('POST', f"/propuestas/{primera['id']}/intervencion",
                {'resultado': 'NO_SOLUCIONADO', 'tiempo_min': 20, 'accion_aplicada': 'Cambio de cable de poder.'})
        # ronda 2: la hipótesis que falló ya no se propone
        ronda = self.ok('GET', f'/incidentes/{iid}/ronda')
        self.assertEqual(ronda['ronda'], 2)
        self.assertIn(primera['hipotesis_codigo'], ronda['descartadas'])
        r2 = self.ok('POST', f'/incidentes/{iid}/diagnosticos', cuerpo)
        self.assertNotIn(primera['hipotesis_codigo'], [t['hipotesis']['codigo'] for t in r2['top']])
        det = self.ok('GET', f'/incidentes/{iid}')
        nueva = det['rondas'][1]['hipotesis'][0]
        self.assertEqual(self.pedir('POST', f"/propuestas/{primera['id']}/decision", {'estado': 'DESCARTADA'},
                                    self.admin)[0], 409)                                          # ronda anterior
        self.ok('POST', f"/propuestas/{nueva['id']}/decision", {'estado': 'CONFIRMADA'})
        cerrado = self.ok('POST', f"/propuestas/{nueva['id']}/intervencion",
                          {'resultado': 'SOLUCIONADO', 'tiempo_min': 15})['incidente']
        self.assertEqual(cerrado['estado'], 'CERRADO')
        self.assertIsNotNone(cerrado['fecha_cierre'])
        # un incidente cerrado no admite cambios
        self.assertEqual(self.pedir('POST', f'/incidentes/{iid}/diagnosticos', cuerpo, self.admin)[0], 409)
        self.assertEqual(self.pedir('POST', f'/incidentes/{iid}/citas', self.futuro(6), self.admin)[0], 409)
        estados = [h['estado_nuevo'] for h in self.ok('GET', f'/incidentes/{iid}')['historial']]
        self.assertEqual(estados, ['ABIERTO', 'EN_DIAGNOSTICO', 'CERRADO'])
        # historial del equipo e indicadores
        hist = self.ok('GET', '/equipos/PC-PRUEBA-01/historial')
        self.assertEqual(len(hist['incidentes']), 1)
        self.assertEqual(len(hist['incidentes'][0]['intervenciones']), 2)
        ind = self.ok('GET', '/indicadores')
        self.assertGreaterEqual(ind['por_estado']['CERRADO'], 1)
        self.assertIn('Incidente;Estado', self.ok('GET', '/reportes/incidentes')['contenido'])

    def test_escalamiento_y_filtro_por_solicitante(self):
        s = self.ingresar('ana.rodriguez@sedati.example')
        inc = self.reportar(s, 'PC-PRUEBA-02', 'El equipo no navega en Internet desde esta mañana.')
        iid = inc['id']
        self.assertEqual(self.pedir('POST', f'/incidentes/{iid}/escalar',
                                    {'motivo': 'Requiere el área de redes.', 'destino': 'Redes'}, self.admin)[0], 409)
        self.ok('POST', f'/incidentes/{iid}/diagnosticos', {'sintomas': [self.ids['E-088']], 'respuestas': []})
        self.assertEqual(self.pedir('POST', f'/incidentes/{iid}/escalar', {'motivo': 'corto', 'destino': 'R'},
                                    self.admin)[0], 400)
        esc = self.ok('POST', f'/incidentes/{iid}/escalar',
                      {'motivo': 'Se requiere acceso de administración al switch.', 'destino': 'Infraestructura'})
        self.assertEqual(esc['incidente']['estado'], 'ESCALADO')
        otro = self.ingresar('solicitante@sedati.example')
        self.assertEqual(self.pedir('GET', f'/incidentes/{iid}', token=otro)[0], 404)      # no es suyo
        propios = self.ok('GET', '/incidentes', token=s)['incidentes']
        self.assertTrue(all(i['solicitante_id'] == propios[0]['solicitante_id'] for i in propios))
        self.assertNotIn('rondas', self.ok('GET', f'/incidentes/{iid}', token=s))          # sin diagnóstico


class PruebasAdministracionConocimiento(BaseApi):
    def test_crear_modificar_y_desactivar_un_granulo(self):
        h = self.ok('POST', '/conocimiento/hipotesis', {'nombre': 'Batería del portátil', 'dominio': 'Hardware',
                                                        'probabilidad_previa': 0.02})['hipotesis']
        self.assertEqual(h['codigo'], 'HIP-39')
        e1 = self.ok('POST', '/conocimiento/evidencias', {'tipo': 'SINTOMA',
                                                          'enunciado': 'el portátil se apaga al desconectar el cargador'})
        e2 = self.ok('POST', '/conocimiento/evidencias', {'tipo': 'PRUEBA',
                                                          'enunciado': 'la batería reporta menos del 40 % de su capacidad'})
        self.assertEqual(e1['evidencia']['codigo'], 'E-154')
        self.assertEqual(self.pedir('POST', '/conocimiento/evidencias', {
            'tipo': 'SINTOMA', 'enunciado': 'el portátil se apaga al desconectar el cargador'}, self.admin)[0], 409)
        datos = {'hipotesis_id': h['id'], 'rama_codigo': 'A2', 'conclusion': 'la falla está en la batería del portátil',
                 'accion': 'Reemplazar la batería por una original de la misma referencia.', 'factor_certeza': 85,
                 'condiciones': [{'evidencia_id': e1['evidencia']['id']}, {'evidencia_id': e2['evidencia']['id']}]}
        self.assertEqual(self.pedir('POST', '/conocimiento/granulos', dict(datos, condiciones=[
            {'evidencia_id': e1['evidencia']['id']}, {'evidencia_id': e1['evidencia']['id']}]), self.admin)[0], 400)
        g = self.ok('POST', '/conocimiento/granulos', datos)['condiciones']
        regla = g[0]['regla']
        self.assertEqual(regla, 'R-89')
        self.assertEqual([c['conector'] for c in g], ['If', 'And'])
        # el gránulo nuevo se usa en el siguiente diagnóstico sin reiniciar ni tocar el código
        d = self.ok('POST', '/diagnostico', {'sintomas': [e1['evidencia']['id']],
                                             'respuestas': [{'evidencia_id': e2['evidencia']['id'], 'escala': 'SI'}]})
        self.assertEqual(d['top'][0]['hipotesis']['codigo'], 'HIP-39')
        sim = self.ok('POST', f'/conocimiento/granulos/{regla}/simular', {'evidencias': [e1['evidencia']['id']]})
        self.assertEqual((sim['cumplidas'], sim['total'], sim['certeza_proporcional']), (1, 2, 42.5))
        mod = self.ok('POST', f'/conocimiento/granulos/{regla}', dict(datos, factor_certeza=90))['condiciones']
        self.assertEqual(mod[0]['version'], 2)
        self.ok('POST', f'/conocimiento/granulos/{regla}/estado', {'activo': False})
        d = self.ok('POST', '/diagnostico', {'sintomas': [e1['evidencia']['id']], 'respuestas': []})
        self.assertNotIn('HIP-39', [t['hipotesis']['codigo'] for t in d['top']])
        acciones = [a['accion'] for a in self.ok('GET', '/conocimiento/auditoria', consulta={'codigo': regla})['auditoria']]
        self.assertEqual(acciones, ['DESACTIVAR', 'MODIFICAR', 'CREAR'])

    def test_la_base_impide_borrar_y_cambiar_codigos(self):
        from sedati.datos import ErrorIntegridad
        kb = self.api.fabrica.conexion_kb
        with self.assertRaises(Exception):
            kb.ejecutar('DELETE FROM granulo WHERE regla = ?', ('R-01',))
        with self.assertRaises(ErrorIntegridad):
            kb.ejecutar("UPDATE hipotesis SET codigo = 'HIP-77' WHERE id = 1")


class PruebasDemostracion(BaseApi):
    demo = True

    def test_casos_de_demostracion(self):
        estados = [i['estado'] for i in self.ok('GET', '/incidentes')['incidentes']]
        self.assertEqual(sorted(estados), sorted(['CERRADO', 'CERRADO', 'CERRADO', 'ESCALADO', 'EN_DIAGNOSTICO',
                                                  'ABIERTO']))
        ind = self.ok('GET', '/indicadores')
        self.assertEqual(ind['escalamientos'], 1)
        self.assertEqual(ind['resueltos_primera_ronda'], 2)


class PruebasLambda(unittest.TestCase):
    def test_handler_api_gateway(self):
        with tempfile.TemporaryDirectory() as d:
            variables = {'SEDATI_RUTA_SQLITE_KB': str(Path(d) / 'kb.db'), 'SEDATI_RUTA_SQLITE_TRX': str(Path(d) / 'trx.db'),
                         'SEDATI_SECRETO': 'prueba-lambda', 'SEDATI_DATOS_DEMO': 'no', 'SEDATI_MOTOR_BD': 'sqlite'}
            anteriores = {k: os.environ.get(k) for k in variables}
            os.environ.update(variables)
            try:
                import lambda_function as lf
                lf._api = None
                ingreso = {'rawPath': '/api/auth/ingresar', 'requestContext': {'http': {'method': 'POST',
                                                                                         'sourceIp': '10.0.0.1'}},
                           'body': json.dumps({'correo': 'admin@sedati.example', 'contrasena': CLAVE})}
                r = lf.lambda_handler(ingreso, None)
                self.assertEqual(r['statusCode'], 200)
                token = json.loads(r['body'])['_sesion']['token']
                evento = {'rawPath': '/api/diagnostico', 'requestContext': {'http': {'method': 'POST'}},
                          'headers': {'authorization': f'Bearer {token}'},
                          'body': json.dumps({'sintomas': [88]}), 'isBase64Encoded': False}
                r = lf.lambda_handler(evento, None)
                self.assertEqual(r['statusCode'], 200)
                self.assertIn('Authorization', r['headers']['Access-Control-Allow-Headers'])
                self.assertIsNotNone(json.loads(r['body'])['pregunta'])
                self.assertEqual(lf.lambda_handler(dict(evento, headers={}), None)['statusCode'], 401)
                self.assertEqual(lf.lambda_handler(dict(evento, body='{no es json'), None)['statusCode'], 400)
                previa = {'rawPath': '/api/catalogo', 'requestContext': {'http': {'method': 'OPTIONS'}}}
                self.assertEqual(lf.lambda_handler(previa, None)['statusCode'], 204)
                consulta = {'rawPath': '/api/incidentes', 'requestContext': {'http': {'method': 'GET'}},
                            'headers': {'authorization': f'Bearer {token}'},
                            'queryStringParameters': {'estado': 'ABIERTO'}}
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
