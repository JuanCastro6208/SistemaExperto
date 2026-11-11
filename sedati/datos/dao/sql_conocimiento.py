"""DAO de la base de conocimiento (sedati_kb: hipotesis, evidencia, granulo) sobre SQL.

El motor no carga la base completa: le pide al DAO solo los gránulos que necesita en cada paso
(los que contienen una evidencia, los de una categoría, las condiciones de unas reglas...). Cada
consulta se notifica a los observadores para que la interfaz muestre la traza de consultas.
"""
import re

from .interfaces import AdministracionConocimientoDAO, ConocimientoDAO

_COLUMNAS_CONDICION = '''
    g.regla, g.orden, g.conector, g.peso, g.hipotesis_id, g.factor_certeza, g.conclusion, g.accion,
    g.riesgo_perdida_datos, g.categoria_codigo, g.categoria_nombre, g.rama_codigo, g.rama_nombre,
    g.procesos, g.version, g.activo AS granulo_activo, g.fuente, g.actualizado_en,
    e.id AS evidencia_id, e.codigo AS evidencia_codigo, e.tipo, e.enunciado, e.pregunta,
    e.variable, e.polaridad'''


def _marcadores(n):
    return ', '.join('?' * n)


class ConocimientoDAOSQL(ConocimientoDAO):
    def __init__(self, conexion):
        self._cx = conexion
        self._observadores = []

    # ------------------------------------------------------------ traza
    def suscribir(self, observador):
        """observador(descripcion: str, filas: int) se llama después de cada consulta."""
        self._observadores.append(observador)

    def desuscribir(self, observador):
        if observador in self._observadores:
            self._observadores.remove(observador)

    def _consultar(self, descripcion, sql, parametros=()):
        filas = self._cx.consultar(sql, parametros)
        for obs in list(self._observadores):
            obs(descripcion, len(filas))
        return filas

    # ------------------------------------------------------------ consultas del motor
    def reglas_que_contienen(self, evidencia_ids):
        """Reglas activas que tienen alguna de estas evidencias como condición."""
        ids = list(evidencia_ids)
        if not ids:
            return []
        filas = self._consultar(
            f'Gránulos que contienen {len(ids)} evidencia(s)',
            f'SELECT DISTINCT regla FROM granulo WHERE activo = 1 AND evidencia_id IN ({_marcadores(len(ids))})',
            ids)
        return [f['regla'] for f in filas]

    def reglas_de_categorias(self, categorias):
        """Reglas activas de las categorías del árbol indicadas (diagnóstico diferencial)."""
        cats = list(categorias)
        if not cats:
            return []
        filas = self._consultar(
            f'Gránulos de la(s) categoría(s) {", ".join(cats)}',
            f'SELECT DISTINCT regla FROM granulo WHERE activo = 1 AND categoria_codigo IN ({_marcadores(len(cats))})',
            cats)
        return [f['regla'] for f in filas]

    def condiciones_de_reglas(self, reglas):
        """Todas las condiciones (filas de granulo) de las reglas indicadas, con su evidencia."""
        rs = list(reglas)
        if not rs:
            return []
        return self._consultar(
            f'Condiciones If / And de {len(rs)} regla(s)',
            f'''SELECT {_COLUMNAS_CONDICION}
                  FROM granulo g
                  JOIN evidencia e ON e.id = g.evidencia_id
                 WHERE g.activo = 1 AND e.activo = 1 AND g.regla IN ({_marcadores(len(rs))})
                 ORDER BY g.regla, g.orden''',
            rs)

    def hipotesis_por_ids(self, ids):
        ids = list(ids)
        if not ids:
            return []
        return self._consultar(
            f'Datos de {len(ids)} hipótesis',
            f'''SELECT h.id, h.codigo, h.nombre, h.dominio, h.probabilidad_previa,
                       (SELECT COUNT(DISTINCT g.regla) FROM granulo g
                         WHERE g.hipotesis_id = h.id AND g.activo = 1) AS reglas
                  FROM hipotesis h WHERE h.activo = 1 AND h.id IN ({_marcadores(len(ids))})''',
            ids)

    def evidencias_de_variables(self, variables):
        """Evidencias que describen las mismas observaciones (para deducir respuestas)."""
        vs = list(variables)
        if not vs:
            return []
        return self._consultar(
            f'Evidencias equivalentes u opuestas ({len(vs)} variable(s))',
            f'''SELECT id, codigo, tipo, enunciado, pregunta, variable, polaridad
                  FROM evidencia WHERE activo = 1 AND variable IN ({_marcadores(len(vs))})''',
            vs)

    def evidencias_por_ids(self, ids):
        ids = list(ids)
        if not ids:
            return []
        return self._consultar(
            f'Datos de {len(ids)} evidencia(s)',
            f'''SELECT id, codigo, tipo, enunciado, pregunta, variable, polaridad
                  FROM evidencia WHERE id IN ({_marcadores(len(ids))})''',
            ids)

    def evidencias_por_codigos(self, codigos):
        cs = list(codigos)
        if not cs:
            return []
        return self._cx.consultar(
            f'''SELECT id, codigo, tipo, enunciado, pregunta, variable, polaridad
                  FROM evidencia WHERE codigo IN ({_marcadores(len(cs))})''', cs)

    def hipotesis_por_codigos(self, codigos):
        cs = list(codigos)
        if not cs:
            return []
        return self._cx.consultar(
            f'SELECT id, codigo, nombre, dominio, activo FROM hipotesis WHERE codigo IN ({_marcadores(len(cs))})', cs)

    def reglas_de_hipotesis_mas_probables(self, excluir, limite):
        """Reglas de las hipótesis con mayor probabilidad previa que aún no están en el diferencial.

        Se usa como respaldo cuando las categorías activadas tienen menos hipótesis de las que
        el sistema debe entregar.
        """
        excl = list(excluir) or [0]
        hips = self._consultar(
            f'Hipótesis de mayor probabilidad previa (respaldo, {limite})',
            f'''SELECT id FROM hipotesis
                 WHERE activo = 1 AND id NOT IN ({_marcadores(len(excl))})
                 ORDER BY probabilidad_previa DESC, id LIMIT ?''',
            excl + [limite])
        ids = [h['id'] for h in hips]
        if not ids:
            return []
        filas = self._consultar(
            f'Gránulos de {len(ids)} hipótesis de respaldo',
            f'SELECT DISTINCT regla FROM granulo WHERE activo = 1 AND hipotesis_id IN ({_marcadores(len(ids))})',
            ids)
        return [f['regla'] for f in filas]

    # ------------------------------------------------------------ catálogos para la interfaz
    def categorias(self):
        return self._cx.consultar(
            '''SELECT categoria_codigo AS codigo, categoria_nombre AS nombre, COUNT(DISTINCT regla) AS reglas
                 FROM granulo WHERE activo = 1
                GROUP BY categoria_codigo, categoria_nombre ORDER BY categoria_codigo''')

    def sintomas_por_categoria(self, categoria):
        """Síntomas con los que empieza alguna regla de la categoría (condición If)."""
        return self._cx.consultar(
            '''SELECT DISTINCT e.id, e.codigo, e.enunciado, e.pregunta
                 FROM granulo g JOIN evidencia e ON e.id = g.evidencia_id
                WHERE g.activo = 1 AND e.activo = 1 AND g.orden = 1 AND g.categoria_codigo = ?
                ORDER BY e.codigo''', (categoria,))

    def resumen_hipotesis(self, incluir_inactivas=False):
        filtro = '' if incluir_inactivas else 'WHERE h.activo = 1'
        return self._cx.consultar(
            f'''SELECT h.id, h.codigo, h.nombre, h.dominio, h.probabilidad_previa, h.activo,
                       COUNT(DISTINCT g.regla) AS reglas, MIN(g.factor_certeza) AS fc_min,
                       MAX(g.factor_certeza) AS fc_max
                  FROM hipotesis h LEFT JOIN granulo g ON g.hipotesis_id = h.id AND g.activo = 1
                  {filtro}
                 GROUP BY h.id, h.codigo, h.nombre, h.dominio, h.probabilidad_previa, h.activo
                 ORDER BY h.codigo''')

    def condiciones_de_hipotesis(self, hipotesis_id, incluir_inactivos=False):
        filtro = '' if incluir_inactivos else 'AND g.activo = 1'
        return self._cx.consultar(
            f'''SELECT {_COLUMNAS_CONDICION}
                  FROM granulo g JOIN evidencia e ON e.id = g.evidencia_id
                 WHERE g.hipotesis_id = ? {filtro}
                 ORDER BY g.regla, g.orden''', (hipotesis_id,))

    def listar_evidencias(self, incluir_inactivas=False):
        filtro = '' if incluir_inactivas else 'WHERE e.activo = 1'
        return self._cx.consultar(
            f'''SELECT e.id, e.codigo, e.tipo, e.enunciado, e.pregunta, e.variable, e.polaridad, e.activo,
                       COUNT(DISTINCT g.regla) AS reglas
                  FROM evidencia e LEFT JOIN granulo g ON g.evidencia_id = e.id AND g.activo = 1
                  {filtro}
                 GROUP BY e.id, e.codigo, e.tipo, e.enunciado, e.pregunta, e.variable, e.polaridad, e.activo
                 ORDER BY e.codigo''')

    def estadisticas(self):
        return self._cx.uno(
            '''SELECT (SELECT COUNT(*) FROM hipotesis WHERE activo = 1) AS hipotesis,
                      (SELECT COUNT(*) FROM evidencia WHERE activo = 1) AS evidencias,
                      (SELECT COUNT(DISTINCT regla) FROM granulo WHERE activo = 1) AS reglas,
                      (SELECT COUNT(*) FROM granulo WHERE activo = 1) AS filas_granulo''')


class AdministracionConocimientoDAOSQL(AdministracionConocimientoDAO):
    _CODIGOS = {'HIPOTESIS': ('hipotesis', 'codigo', 'HIP-', 2),
                'EVIDENCIA': ('evidencia', 'codigo', 'E-', 3),
                'GRANULO': ('granulo', 'regla', 'R-', 2)}

    def __init__(self, conexion):
        self._cx = conexion

    def siguiente_codigo(self, entidad):
        tabla, columna, prefijo, digitos = self._CODIGOS[entidad]
        numeros = [int(m.group(1)) for f in self._cx.consultar(f'SELECT DISTINCT {columna} AS c FROM {tabla}')
                   if (m := re.fullmatch(re.escape(prefijo) + r'(\d+)', f['c']))]
        return f'{prefijo}{(max(numeros) if numeros else 0) + 1:0{digitos}d}'

    # ------------------------------------------------------------ hipótesis
    def hipotesis(self, hipotesis_id):
        return self._cx.uno('SELECT * FROM hipotesis WHERE id = ?', (hipotesis_id,))

    def crear_hipotesis(self, codigo, nombre, dominio, probabilidad_previa):
        return self._cx.ejecutar(
            'INSERT INTO hipotesis (codigo, nombre, dominio, probabilidad_previa, activo) VALUES (?, ?, ?, ?, 1)',
            (codigo, nombre, dominio, probabilidad_previa))

    def cambiar_estado_hipotesis(self, hipotesis_id, activo):
        self._cx.ejecutar('UPDATE hipotesis SET activo = ? WHERE id = ?', (1 if activo else 0, hipotesis_id))

    # ------------------------------------------------------------ evidencias
    def evidencia(self, evidencia_id):
        return self._cx.uno('SELECT * FROM evidencia WHERE id = ?', (evidencia_id,))

    def crear_evidencia(self, codigo, tipo, enunciado, pregunta, variable, polaridad):
        return self._cx.ejecutar(
            '''INSERT INTO evidencia (codigo, tipo, enunciado, pregunta, variable, polaridad, activo)
               VALUES (?, ?, ?, ?, ?, ?, 1)''', (codigo, tipo, enunciado, pregunta, variable, polaridad))

    def cambiar_estado_evidencia(self, evidencia_id, activo):
        self._cx.ejecutar('UPDATE evidencia SET activo = ? WHERE id = ?', (1 if activo else 0, evidencia_id))

    # ------------------------------------------------------------ gránulos
    def filas_granulo(self, regla):
        return self._cx.consultar(
            f'''SELECT {_COLUMNAS_CONDICION}
                  FROM granulo g JOIN evidencia e ON e.id = g.evidencia_id
                 WHERE g.regla = ? ORDER BY g.orden''', (regla,))

    def crear_granulo(self, regla, hipotesis_id, condiciones, datos, ahora):
        """condiciones: lista de (evidencia_id, peso) en orden; la primera lleva If y las demás And."""
        with self._cx.transaccion():
            for orden, (evidencia_id, peso) in enumerate(condiciones, 1):
                self._cx.ejecutar(
                    '''INSERT INTO granulo (regla, hipotesis_id, evidencia_id, orden, conector, peso,
                                            categoria_codigo, categoria_nombre, rama_codigo, rama_nombre, procesos,
                                            conclusion, accion, factor_certeza, riesgo_perdida_datos, fuente,
                                            version, activo, creado_en, actualizado_en)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)''',
                    (regla, hipotesis_id, evidencia_id, orden, 'If' if orden == 1 else 'And', peso,
                     datos['categoria_codigo'], datos['categoria_nombre'], datos['rama_codigo'], datos['rama_nombre'],
                     datos['procesos'], datos['conclusion'], datos['accion'], datos['factor_certeza'],
                     1 if datos['riesgo_perdida_datos'] else 0, datos['fuente'], ahora, ahora))

    def modificar_granulo(self, regla, cambios, ahora):
        """Cambia la conclusión, la acción, el factor de certeza o el riesgo y sube la versión."""
        self._cx.ejecutar(
            '''UPDATE granulo SET conclusion = ?, accion = ?, factor_certeza = ?, riesgo_perdida_datos = ?,
                                  version = version + 1, actualizado_en = ?
                WHERE regla = ?''',
            (cambios['conclusion'], cambios['accion'], cambios['factor_certeza'],
             1 if cambios['riesgo_perdida_datos'] else 0, ahora, regla))

    def cambiar_estado_granulo(self, regla, activo, ahora):
        self._cx.ejecutar('UPDATE granulo SET activo = ?, actualizado_en = ? WHERE regla = ?',
                          (1 if activo else 0, ahora, regla))

    def ramas(self):
        return self._cx.consultar(
            '''SELECT categoria_codigo, categoria_nombre, rama_codigo, rama_nombre, MIN(procesos) AS procesos,
                      COUNT(DISTINCT regla) AS reglas
                 FROM granulo
                GROUP BY categoria_codigo, categoria_nombre, rama_codigo, rama_nombre
                ORDER BY rama_codigo''')
