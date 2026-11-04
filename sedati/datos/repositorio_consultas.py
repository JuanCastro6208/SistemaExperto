"""Persistencia de las sesiones de diagnóstico (consulta, respuestas y resultado)."""
from datetime import datetime


def _ahora():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class RepositorioConsultas:
    def __init__(self, conexion):
        self._cx = conexion

    def escala(self):
        return self._cx.consultar(
            'SELECT codigo, etiqueta, valor, orden, color FROM escala_respuesta ORDER BY orden')

    def crear(self, equipo, ubicacion, descripcion, parametros):
        return self._cx.ejecutar(
            '''INSERT INTO consulta (fecha_inicio, equipo, ubicacion, descripcion, estado, parametros)
               VALUES (?, ?, ?, ?, 'EN_CURSO', ?)''',
            (_ahora(), equipo or None, ubicacion or None, descripcion or None, parametros))

    def guardar_respuesta(self, consulta_id, orden, evidencia_id, escala_codigo, valor, origen):
        existe = self._cx.consultar(
            'SELECT id FROM consulta_respuesta WHERE consulta_id = ? AND evidencia_id = ?',
            (consulta_id, evidencia_id))
        if existe:
            self._cx.ejecutar(
                '''UPDATE consulta_respuesta SET escala_codigo = ?, valor = ?, registrado_en = ?
                    WHERE consulta_id = ? AND evidencia_id = ?''',
                (escala_codigo, valor, _ahora(), consulta_id, evidencia_id))
        else:
            self._cx.ejecutar(
                '''INSERT INTO consulta_respuesta (consulta_id, orden, evidencia_id, escala_codigo, valor, origen,
                                                   registrado_en)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (consulta_id, orden, evidencia_id, escala_codigo, valor, origen, _ahora()))

    def finalizar(self, consulta_id, total_preguntas, resultados):
        """resultados: lista de (posicion, hipotesis_id, probabilidad, certeza, regla_principal)."""
        for pos, hid, prob, cf, regla in resultados:
            self._cx.ejecutar(
                '''INSERT INTO consulta_hipotesis (consulta_id, posicion, hipotesis_id, probabilidad, certeza,
                                                   regla_principal)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (consulta_id, pos, hid, round(prob, 5), round(cf, 4), regla))
        self._cx.ejecutar(
            '''UPDATE consulta SET estado = 'FINALIZADA', fecha_fin = ?, total_preguntas = ? WHERE id = ?''',
            (_ahora(), total_preguntas, consulta_id))

    def cancelar(self, consulta_id):
        self._cx.ejecutar(
            "UPDATE consulta SET estado = 'CANCELADA', fecha_fin = ? WHERE id = ? AND estado = 'EN_CURSO'",
            (_ahora(), consulta_id))

    def listar(self):
        return self._cx.consultar(
            '''SELECT c.id, c.fecha_inicio, c.fecha_fin, c.equipo, c.ubicacion, c.estado, c.total_preguntas,
                      h.codigo AS hipotesis_codigo, h.nombre AS hipotesis_nombre, ch.probabilidad
                 FROM consulta c
                 LEFT JOIN consulta_hipotesis ch ON ch.consulta_id = c.id AND ch.posicion = 1
                 LEFT JOIN hipotesis h ON h.id = ch.hipotesis_id
                ORDER BY c.id DESC''')

    def obtener(self, consulta_id):
        cab = self._cx.consultar('SELECT * FROM consulta WHERE id = ?', (consulta_id,))
        if not cab:
            return None
        respuestas = self._cx.consultar(
            '''SELECT r.orden, r.evidencia_id, r.escala_codigo, r.valor, r.origen
                 FROM consulta_respuesta r WHERE r.consulta_id = ? ORDER BY r.orden''', (consulta_id,))
        hipotesis = self._cx.consultar(
            '''SELECT ch.posicion, ch.hipotesis_id, ch.probabilidad, ch.certeza, ch.regla_principal,
                      h.codigo, h.nombre
                 FROM consulta_hipotesis ch JOIN hipotesis h ON h.id = ch.hipotesis_id
                WHERE ch.consulta_id = ? ORDER BY ch.posicion''', (consulta_id,))
        return {'consulta': cab[0], 'respuestas': respuestas, 'hipotesis': hipotesis}
