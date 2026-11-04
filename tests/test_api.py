"""Pruebas del servicio web (API REST) y del handler de AWS Lambda.

    python -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from sedati.configuracion import Configuracion, ParametrosMotor  # noqa: E402
from sedati.servicio import ApiSEDATI  # noqa: E402


class PruebasApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        conf = Configuracion('sqlite', Path(cls._dir.name) / 'api.db', {}, ParametrosMotor())
        cls.api = ApiSEDATI(conf)
        _, cat = cls.api.atender('GET', '/api/catalogo')
        cls.ids = {s['codigo']: s['id'] for c in cat['categorias'] for s in c['sintomas']}

    @classmethod
    def tearDownClass(cls):
        cls.api.conexion.cerrar()
        cls._dir.cleanup()

    def test_catalogo(self):
        estado, cat = self.api.atender('GET', '/api/catalogo')
        self.assertEqual(estado, 200)
        self.assertEqual([o['codigo'] for o in cat['escala']], ['SI', 'PROB_SI', 'NO_SE', 'PROB_NO', 'NO'])
        self.assertEqual(cat['estadisticas']['reglas'], 88)
        self.assertIn('E-079', self.ids)

    def test_diagnostico_sin_estado_llega_a_la_hipotesis(self):
        """Caso «impresora con IP cambiada»: el cliente envía todas las respuestas en cada petición."""
        verdad = {'IMPRESORA_RESPONDE_RED': 'NO', 'E-081': 'SI', 'E-082': 'NO', 'E-087': 'NO'}
        respuestas = []
        for _ in range(20):
            estado, d = self.api.atender('POST', '/api/diagnostico',
                                         {'sintomas': [self.ids['E-079']], 'respuestas': respuestas})
            self.assertEqual(estado, 200)
            q = d['pregunta']
            if d['motivo_conclusion'] or q is None:
                break
            ev = self.api.diagnostico._kb.evidencias_por_ids([q['evidencia']['id']])[0]
            escala = verdad.get(ev['codigo']) or verdad.get(ev['variable']) or 'NO_SE'
            respuestas.append({'evidencia_id': q['evidencia']['id'], 'escala': escala})
        self.assertEqual(d['top'][0]['hipotesis']['codigo'], 'HIP-20')
        self.assertEqual(len(d['top']), 5)
        self.assertAlmostEqual(sum(r['probabilidad'] for r in d['top']), 1.0, delta=0.05)
        self.assertTrue(d['traza'])
        self.assertEqual(len(d['evolucion']), len(respuestas) + 1)
        json.dumps(d)   # todo el estado es serializable

    def test_guardar_y_reconstruir_consulta(self):
        cuerpo = {'sintomas': [self.ids['E-001']], 'respuestas': [], 'equipo': 'PC-01'}
        _, d = self.api.atender('POST', '/api/diagnostico', cuerpo)
        cuerpo['respuestas'] = [{'evidencia_id': d['pregunta']['evidencia']['id'], 'escala': 'SI'}]
        estado, guardada = self.api.atender('POST', '/api/consultas', cuerpo)
        self.assertEqual(estado, 200)
        self.assertTrue(guardada['finalizada'])
        cid = guardada['consulta_id']
        estado, rec = self.api.atender('GET', f'/api/consultas/{cid}')
        self.assertEqual(estado, 200)
        self.assertEqual([r['hipotesis']['id'] for r in rec['top']], [r['hipotesis']['id'] for r in guardada['top']])
        _, hist = self.api.atender('GET', '/api/consultas')
        self.assertIn(cid, [c['id'] for c in hist['consultas']])
        _, inf = self.api.atender('GET', f'/api/consultas/{cid}/informe')
        self.assertIn('SEDATI - Informe de diagnóstico', inf['informe'])

    def test_errores(self):
        self.assertEqual(self.api.atender('POST', '/api/diagnostico', {'sintomas': []})[0], 400)
        self.assertEqual(self.api.atender('POST', '/api/diagnostico', {'sintomas': ['x']})[0], 400)
        self.assertEqual(self.api.atender('POST', '/api/diagnostico', {
            'sintomas': [self.ids['E-001']], 'respuestas': [{'evidencia_id': 1, 'escala': 'TAL_VEZ'}]})[0], 400)
        self.assertEqual(self.api.atender('POST', '/api/diagnostico', {
            'sintomas': [self.ids['E-001']], 'respuestas': [{'evidencia_id': 9999, 'escala': 'SI'}]})[0], 400)
        self.assertEqual(self.api.atender('GET', '/api/consultas/999999')[0], 404)
        self.assertEqual(self.api.atender('GET', '/api/no-existe')[0], 404)
        self.assertEqual(self.api.atender('GET', '/api/diagnostico')[0], 405)

    def test_conocimiento(self):
        _, h = self.api.atender('GET', '/api/conocimiento/hipotesis')
        self.assertEqual(len(h['hipotesis']), 38)
        _, g = self.api.atender('GET', f"/api/conocimiento/hipotesis/{h['hipotesis'][0]['id']}")
        self.assertEqual(g['granulos'][0]['condiciones'][0]['conector'], 'If')
        _, e = self.api.atender('GET', '/api/conocimiento/evidencias')
        self.assertEqual(len(e['evidencias']), 153)


class PruebasLambda(unittest.TestCase):
    def test_handler_api_gateway(self):
        with tempfile.TemporaryDirectory() as d:
            anterior = os.environ.get('SEDATI_RUTA_SQLITE')
            os.environ['SEDATI_RUTA_SQLITE'] = str(Path(d) / 'lambda.db')
            try:
                import lambda_function as lf
                lf._api = None
                evento = {'rawPath': '/api/diagnostico', 'requestContext': {'http': {'method': 'POST'}},
                          'body': json.dumps({'sintomas': [88]}), 'isBase64Encoded': False}
                r = lf.lambda_handler(evento, None)
                self.assertEqual(r['statusCode'], 200)
                self.assertIn('Access-Control-Allow-Origin', r['headers'])
                self.assertIsNotNone(json.loads(r['body'])['pregunta'])
                malo = dict(evento, body='{no es json')
                self.assertEqual(lf.lambda_handler(malo, None)['statusCode'], 400)
                previa = {'rawPath': '/api/catalogo', 'requestContext': {'http': {'method': 'OPTIONS'}}}
                self.assertEqual(lf.lambda_handler(previa, None)['statusCode'], 204)
                lf._api.conexion.cerrar()
                lf._api = None
            finally:
                if anterior is None:
                    os.environ.pop('SEDATI_RUTA_SQLITE', None)
                else:
                    os.environ['SEDATI_RUTA_SQLITE'] = anterior


if __name__ == '__main__':
    unittest.main()
