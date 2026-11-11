"""Pruebas del sistema de inferencia de SEDATI.

    python -m unittest discover -s tests -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime  # noqa: E402

from sedati.configuracion import ParametrosMotor  # noqa: E402
from sedati.datos import FabricaDAO  # noqa: E402
from sedati.datos.conexion import SCRIPTS_SQLITE_KB, SCRIPTS_SQLITE_TRX, ConexionSQLite  # noqa: E402
from sedati.negocio import ServicioDiagnostico  # noqa: E402
from sedati.negocio import certeza  # noqa: E402

# (nombre, síntomas iniciales, «verdad» del caso {código o variable: respuesta}, hipótesis esperada)
CASOS = [
    ('impresora con cola detenida', ['E-079'],
     {'IMPRESORA_RESPONDE_RED': 'SI', 'E-084': 'SI', 'COLA_IMPRESION_ACTIVA': 'NO', 'E-087': 'NO'}, 'HIP-21'),
    ('impresora con IP cambiada', ['E-079'],
     {'IMPRESORA_RESPONDE_RED': 'NO', 'E-081': 'SI', 'E-082': 'NO', 'E-087': 'NO'}, 'HIP-20'),
    ('equipo que no enciende por la fuente', ['E-001'], {'TENSION_TOMA': 'SI', 'E-004': 'SI', 'E-005': 'NO'},
     'HIP-02'),
    ('sin Internet por DHCP o VLAN', ['E-088'],
     {'IP_ENLACE_LOCAL': 'SI', 'E-090': 'SI', 'E-091': 'NO', 'E-098': 'NO'}, 'HIP-23'),
    ('sin Internet por DNS', ['E-088'],
     {'IP_ENLACE_LOCAL': 'NO', 'RESPONDE_PUERTA_ENLACE': 'SI', 'RESPONDE_DIRECCION_PUBLICA': 'SI',
      'NO_RESUELVE_NOMBRES': 'SI', 'E-099': 'NO', 'E-100': 'SI'}, 'HIP-27'),
    ('lentitud por disco saturado', ['E-042'],
     {'E-043': 'SI', 'E-044': 'SI', 'E-045': 'NO', 'E-046': 'NO', 'E-048': 'NO'}, 'HIP-16'),
    ('usuario con la cuenta bloqueada', ['E-114'],
     {'E-115': 'SI', 'E-116': 'SI', 'E-117': 'NO', 'E-118': 'NO', 'CONECTIVIDAD_CON_RED': 'SI', 'E-122': 'NO',
      'E-121': 'NO'}, 'HIP-30'),
    ('antivirus con la licencia vencida', ['E-142'], {'E-143': 'SI', 'E-144': 'NO'}, 'HIP-36'),
    ('puerto USB dañado', ['E-074'], {'OTRO_PUERTO_LO_RECONOCE': 'SI', 'E-077': 'NO'}, 'HIP-18'),
    ('teclado averiado', ['E-067'], {'DISPOSITIVO_EN_OTRO_EQUIPO': 'NO'}, 'HIP-19'),
    ('reinicios por la memoria RAM', ['E-014'], {'E-017': 'SI', 'MENSAJE_ERROR_REINICIO': 'SI', 'E-016': 'NO'},
     'HIP-06'),
    ('sistema operativo que no inicia por el arranque', ['E-034'],
     {'E-035': 'SI', 'DISCO_EN_BIOS': 'SI', 'E-038': 'NO', 'E-040': 'NO'}, 'HIP-13'),
]


class BaseSEDATI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        cls.cx = ConexionSQLite(Path(cls._dir.name) / 'kb.db', SCRIPTS_SQLITE_KB)
        cls.trx = ConexionSQLite(Path(cls._dir.name) / 'trx.db', SCRIPTS_SQLITE_TRX)
        cls.fabrica = FabricaDAO(cls.cx, cls.trx)
        cls.kb = cls.fabrica.conocimiento()
        cls.consultas = cls.fabrica.diagnosticos()
        cls.servicio = ServicioDiagnostico(cls.kb, cls.consultas, cls.fabrica.catalogo(), ParametrosMotor(),
                                           lambda: datetime(2026, 11, 11, 9, 0))
        cls.ids = {f['codigo']: f['id'] for f in cls.cx.consultar('SELECT id, codigo FROM evidencia')}

    @classmethod
    def tearDownClass(cls):
        cls.fabrica.cerrar()
        cls._dir.cleanup()

    def simular(self, sintomas, verdad, registrar=False):
        """El motor pregunta y se responde con la verdad del caso (lo no previsto se responde «No»)."""
        sesion = self.servicio.iniciar([self.ids[c] for c in sintomas], registrar=registrar)
        while sesion.pregunta_actual is not None and not sesion.motivo_conclusion:
            e = sesion.pregunta_actual.evidencia
            sesion.responder(e, sesion.opcion(verdad.get(e.variable) or verdad.get(e.codigo) or 'NO'))
        return sesion


class PruebasBaseDeConocimiento(BaseSEDATI):
    def test_tamano_de_la_base(self):
        self.assertEqual(self.kb.estadisticas(),
                         {'hipotesis': 38, 'evidencias': 153, 'reglas': 88, 'filas_granulo': 224})

    def test_la_base_de_conocimiento_tiene_tres_tablas(self):
        tablas = {f['name'] for f in self.cx.consultar("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue({'hipotesis', 'evidencia', 'granulo'} <= tablas)
        self.assertNotIn('granulo_condicion', tablas)

    def test_las_previas_suman_uno(self):
        total = self.cx.consultar('SELECT SUM(probabilidad_previa) AS s FROM hipotesis')[0]['s']
        self.assertAlmostEqual(total, 1.0, places=3)

    def test_cada_regla_empieza_con_if(self):
        filas = self.cx.consultar("SELECT COUNT(*) AS n FROM granulo WHERE orden = 1 AND conector <> 'If'")
        self.assertEqual(filas[0]['n'], 0)


class PruebasCerteza(unittest.TestCase):
    def test_combinacion_mycin(self):
        self.assertAlmostEqual(certeza.combinar(0.6, 0.5), 0.8)
        self.assertAlmostEqual(certeza.combinar(-0.6, -0.5), -0.8)
        self.assertAlmostEqual(certeza.combinar(0.6, -0.5), 0.2)

    def test_grado_con_todas_las_condiciones_es_uno(self):
        self.assertEqual(certeza.grado_cumplimiento([(1, 1.0), (1, 1.0)]), 1.0)
        self.assertAlmostEqual(certeza.grado_cumplimiento([(1, 1.0), (1, None), (1, None)]), 1 / 3)

    def test_negar_un_camino_no_descarta_la_hipotesis(self):
        self.assertAlmostEqual(certeza.certeza_hipotesis([-0.9, 0.3]), 0.3)
        self.assertAlmostEqual(certeza.certeza_hipotesis([-0.9, -0.2]), -0.2)

    def test_distribucion_suma_uno(self):
        p = certeza.distribucion({1: 0.2, 2: 0.3, 3: 0.5}, {1: 0.9, 2: 0.0, 3: -0.5}, 5.0)
        self.assertAlmostEqual(sum(p.values()), 1.0)
        self.assertEqual(max(p, key=p.get), 1)


class PruebasMotor(BaseSEDATI):
    def test_casos_de_diagnostico(self):
        for nombre, sintomas, verdad, esperada in CASOS:
            with self.subTest(caso=nombre):
                sesion = self.simular(sintomas, verdad)
                top = sesion.resultado()
                self.assertEqual(top[0].hipotesis.codigo, esperada)
                self.assertEqual(len(top), 5)

    def test_siempre_entrega_cinco_hipotesis_ordenadas(self):
        sesion = self.servicio.iniciar([self.ids['E-061']], registrar=False)   # categoría con solo 4 hipótesis
        top = sesion.resultado()
        self.assertEqual(len(top), 5)
        probs = [r.probabilidad for r in top]
        self.assertEqual(probs, sorted(probs, reverse=True))
        self.assertLessEqual(sum(probs), 1.0 + 1e-9)

    def test_no_concluye_sin_preguntar(self):
        for sintoma in ('E-001', 'E-079', 'E-088', 'E-114', 'E-142'):
            with self.subTest(sintoma=sintoma):
                sesion = self.servicio.iniciar([self.ids[sintoma]], registrar=False)
                self.assertIsNone(sesion.motivo_conclusion)
                self.assertIsNotNone(sesion.pregunta_actual)

    def test_respuesta_deduce_la_evidencia_opuesta(self):
        sesion = self.servicio.iniciar([self.ids['E-001']], registrar=False)
        mem = sesion.motor.memoria
        hay_tension = mem.evidencias[self.ids['E-003']]
        sesion.responder(hay_tension, sesion.opcion('SI'))
        no_hay_tension = mem.evidencias[self.ids['E-002']]
        valor = mem.valor(no_hay_tension)
        self.assertEqual(valor.valor, -1.0)
        self.assertTrue(valor.deducido)
        self.assertTrue(mem.ya_preguntada(no_hay_tension))

    def test_las_consultas_son_granulares(self):
        sesion = self.servicio.iniciar([self.ids['E-079']], registrar=False)
        self.assertLess(len(sesion.motor.memoria.granulos), 88)
        self.assertGreater(len(sesion.motor.traza_consultas), 2)
        antes = len(sesion.motor.traza_consultas)
        sesion.responder(sesion.pregunta_actual.evidencia, sesion.opcion('SI'))
        self.assertGreater(len(sesion.motor.traza_consultas), antes)

    def test_corregir_una_respuesta_cambia_el_resultado(self):
        sesion = self.servicio.iniciar([self.ids['E-142']], registrar=False)
        licencia = sesion.motor.memoria.evidencias[self.ids['E-143']]
        sesion.responder(licencia, sesion.opcion('SI'))
        con_licencia = sesion.resultado()[0].certeza
        sesion.responder(licencia, sesion.opcion('NO'))
        self.assertLess(sesion.resultado()[0].certeza, con_licencia)
        self.assertEqual(sesion.motor.preguntas_respondidas, 1)

    def test_respuesta_no_se_no_aporta_evidencia(self):
        sesion = self.servicio.iniciar([self.ids['E-079']], registrar=False)
        antes = sesion.motor.probabilidades()
        sesion.responder(sesion.pregunta_actual.evidencia, sesion.opcion('NO_SE'))
        despues = sesion.motor.probabilidades()
        for h in antes:
            self.assertAlmostEqual(antes[h], despues[h])


class PruebasPersistencia(BaseSEDATI):
    def test_guarda_y_reconstruye_la_consulta(self):
        nombre, sintomas, verdad, esperada = CASOS[0]
        sesion = self.simular(sintomas, verdad, registrar=True)
        top = sesion.finalizar()
        diagnostico = self.consultas.por_id(sesion.diagnostico_id)
        self.assertEqual(diagnostico.estado, 'FINALIZADO')
        propuestas = self.consultas.hipotesis(sesion.diagnostico_id)
        self.assertEqual(len(propuestas), 5)
        self.assertEqual(propuestas[0].hipotesis_codigo, esperada)
        self.assertTrue(propuestas[0].granulo_codigo.startswith('R-'))
        self.assertEqual(propuestas[0].granulo_version, 1)
        otra = self.servicio.reconstruir(sesion.diagnostico_id)
        self.assertEqual([r.hipotesis.id for r in otra.resultado()], [r.hipotesis.id for r in top])

    def test_las_hipotesis_descartadas_no_se_proponen(self):
        nombre, sintomas, verdad, esperada = CASOS[2]          # equipo que no enciende por la fuente
        sesion = self.servicio.iniciar([self.ids[c] for c in sintomas], registrar=False, descartadas=[esperada])
        codigos = [r.hipotesis.codigo for r in sesion.resultado()]
        self.assertNotIn(esperada, codigos)
        self.assertEqual(len(codigos), 5)


if __name__ == '__main__':
    unittest.main()
