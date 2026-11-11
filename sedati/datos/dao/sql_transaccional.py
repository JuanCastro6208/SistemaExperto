"""DAO de la base transaccional (sedati_trx) sobre SQL. Funcionan igual con MySQL 8 y con SQLite."""
from ..dto import (AuditoriaDTO, CitaDTO, DiagnosticoDTO, EquipoDTO, EscalamientoDTO, EventoHistorialDTO,
                   HipotesisPropuestaDTO, IncidenteDTO, IntervencionDTO, RespuestaDTO, UsuarioDTO)
from .interfaces import (AuditoriaDAO, BitacoraAccesoDAO, CatalogoDAO, CitaDAO, DiagnosticoDAO, EquipoDAO,
                         EscalamientoDAO, IncidenteDAO, IndicadoresDAO, IntervencionDAO, UsuarioDAO)


def _marcadores(n):
    return ', '.join('?' * n)


# =====================================================================  catálogos
class CatalogoDAOSQL(CatalogoDAO):
    def __init__(self, conexion):
        self._cx = conexion

    def roles(self):
        return self._cx.consultar('SELECT id, codigo, nombre, descripcion FROM rol ORDER BY id')

    def permisos_de_rol(self, rol_codigo):
        filas = self._cx.consultar(
            '''SELECT m.codigo, p.puede_consultar, p.puede_crear, p.puede_modificar
                 FROM rol_permiso p JOIN rol r ON r.id = p.rol_id JOIN modulo m ON m.id = p.modulo_id
                WHERE r.codigo = ?''', (rol_codigo,))
        return {f['codigo']: {'consultar': bool(f['puede_consultar']), 'crear': bool(f['puede_crear']),
                              'modificar': bool(f['puede_modificar'])} for f in filas}

    def matriz_permisos(self):
        return self._cx.consultar(
            '''SELECT r.codigo AS rol, m.codigo AS modulo, m.nombre AS modulo_nombre,
                      p.puede_consultar, p.puede_crear, p.puede_modificar
                 FROM rol_permiso p JOIN rol r ON r.id = p.rol_id JOIN modulo m ON m.id = p.modulo_id
                ORDER BY m.id, r.id''')

    def dependencias(self):
        return self._cx.consultar('SELECT id, nombre FROM dependencia WHERE activo = 1 ORDER BY nombre')

    def tipos_equipo(self):
        return self._cx.consultar('SELECT id, codigo, nombre FROM tipo_equipo ORDER BY id')

    def escala_respuestas(self):
        return self._cx.consultar('SELECT codigo, etiqueta, valor, orden, color FROM escala_respuesta ORDER BY orden')


# =====================================================================  usuarios y acceso
_SQL_USUARIO = '''SELECT u.*, r.codigo AS rol_codigo, r.nombre AS rol_nombre, d.nombre AS dependencia
                    FROM usuario u JOIN rol r ON r.id = u.rol_id
                    LEFT JOIN dependencia d ON d.id = u.dependencia_id'''


class UsuarioDAOSQL(UsuarioDAO):
    def __init__(self, conexion):
        self._cx = conexion

    def por_id(self, usuario_id):
        return UsuarioDTO.desde_fila(self._cx.uno(f'{_SQL_USUARIO} WHERE u.id = ?', (usuario_id,)))

    def por_correo(self, correo):
        return UsuarioDTO.desde_fila(self._cx.uno(f'{_SQL_USUARIO} WHERE LOWER(u.correo) = LOWER(?)', (correo,)))

    def listar(self, rol_codigo=None, solo_activos=False):
        condiciones, parametros = [], []
        if rol_codigo:
            condiciones.append('r.codigo = ?')
            parametros.append(rol_codigo)
        if solo_activos:
            condiciones.append('u.activo = 1')
        where = f" WHERE {' AND '.join(condiciones)}" if condiciones else ''
        return [UsuarioDTO.desde_fila(f) for f in self._cx.consultar(f'{_SQL_USUARIO}{where} ORDER BY u.nombre', parametros)]

    def existe(self, documento=None, correo=None, excepto_id=None):
        f = self._cx.uno(
            '''SELECT COUNT(*) AS n FROM usuario
                WHERE (documento = ? OR LOWER(correo) = LOWER(?)) AND id <> ?''',
            (documento or '', correo or '', excepto_id or 0))
        return f['n'] > 0

    def crear(self, rol_id, dependencia_id, documento, nombre, correo, contrasena_hash, creado_en):
        return self._cx.ejecutar(
            '''INSERT INTO usuario (rol_id, dependencia_id, documento, nombre, correo, contrasena_hash,
                                    debe_cambiar_contrasena, activo, intentos_fallidos, creado_en)
               VALUES (?, ?, ?, ?, ?, ?, 1, 1, 0, ?)''',
            (rol_id, dependencia_id, documento, nombre, correo, contrasena_hash, creado_en))

    def actualizar(self, usuario_id, rol_id, dependencia_id, nombre, correo):
        self._cx.ejecutar('UPDATE usuario SET rol_id = ?, dependencia_id = ?, nombre = ?, correo = ? WHERE id = ?',
                          (rol_id, dependencia_id, nombre, correo, usuario_id))

    def cambiar_estado(self, usuario_id, activo):
        self._cx.ejecutar('UPDATE usuario SET activo = ? WHERE id = ?', (1 if activo else 0, usuario_id))

    def cambiar_contrasena(self, usuario_id, contrasena_hash, debe_cambiar):
        self._cx.ejecutar(
            '''UPDATE usuario SET contrasena_hash = ?, debe_cambiar_contrasena = ?, intentos_fallidos = 0,
                                  bloqueado_hasta = NULL WHERE id = ?''',
            (contrasena_hash, 1 if debe_cambiar else 0, usuario_id))

    def registrar_fallo(self, usuario_id, intentos, bloqueado_hasta):
        self._cx.ejecutar('UPDATE usuario SET intentos_fallidos = ?, bloqueado_hasta = ? WHERE id = ?',
                          (intentos, bloqueado_hasta, usuario_id))

    def registrar_ingreso(self, usuario_id, fecha):
        self._cx.ejecutar(
            'UPDATE usuario SET intentos_fallidos = 0, bloqueado_hasta = NULL, ultimo_ingreso = ? WHERE id = ?',
            (fecha, usuario_id))

    def desbloquear(self, usuario_id):
        self._cx.ejecutar('UPDATE usuario SET intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id = ?',
                          (usuario_id,))


class BitacoraAccesoDAOSQL(BitacoraAccesoDAO):
    def __init__(self, conexion):
        self._cx = conexion

    def registrar(self, usuario_id, correo, exitoso, motivo, ip, fecha):
        self._cx.ejecutar(
            '''INSERT INTO bitacora_acceso (usuario_id, correo_intentado, exitoso, motivo, ip, fecha)
               VALUES (?, ?, ?, ?, ?, ?)''', (usuario_id, correo[:120], 1 if exitoso else 0, motivo, ip, fecha))

    def recientes(self, limite=50):
        return self._cx.consultar(
            '''SELECT b.id, b.correo_intentado, b.exitoso, b.motivo, b.ip, b.fecha, u.nombre AS usuario
                 FROM bitacora_acceso b LEFT JOIN usuario u ON u.id = b.usuario_id
                ORDER BY b.id DESC LIMIT ?''', (limite,))


# =====================================================================  equipos
_SQL_EQUIPO = '''SELECT e.*, t.nombre AS tipo_nombre, d.nombre AS dependencia
                   FROM equipo e JOIN tipo_equipo t ON t.id = e.tipo_equipo_id
                   LEFT JOIN dependencia d ON d.id = e.dependencia_id'''


class EquipoDAOSQL(EquipoDAO):
    def __init__(self, conexion):
        self._cx = conexion

    def por_inventario(self, inventario):
        return EquipoDTO.desde_fila(self._cx.uno(f'{_SQL_EQUIPO} WHERE UPPER(e.inventario) = UPPER(?)', (inventario,)))

    def por_id(self, equipo_id):
        return EquipoDTO.desde_fila(self._cx.uno(f'{_SQL_EQUIPO} WHERE e.id = ?', (equipo_id,)))

    def crear(self, inventario, tipo_equipo_id, dependencia_id, marca, modelo, ubicacion):
        return self._cx.ejecutar(
            '''INSERT INTO equipo (inventario, tipo_equipo_id, dependencia_id, marca, modelo, ubicacion, activo)
               VALUES (?, ?, ?, ?, ?, ?, 1)''', (inventario, tipo_equipo_id, dependencia_id, marca, modelo, ubicacion))

    def listar(self):
        return self._cx.consultar(
            f'''SELECT x.*, (SELECT COUNT(*) FROM incidente i WHERE i.equipo_id = x.id) AS incidentes
                  FROM ({_SQL_EQUIPO}) x ORDER BY incidentes DESC, x.inventario''')


# =====================================================================  incidentes
_SQL_INCIDENTE = '''
    SELECT i.*, s.nombre AS solicitante, a.nombre AS administrador, e.inventario, t.nombre AS tipo_equipo,
           e.marca, e.modelo,
           (SELECT COUNT(*) FROM diagnostico d WHERE d.incidente_id = i.id) AS rondas,
           (SELECT MIN(c.inicio) FROM cita c WHERE c.incidente_id = i.id AND c.estado = 'PROGRAMADA') AS proxima_cita
      FROM incidente i
      JOIN usuario s ON s.id = i.solicitante_id
      LEFT JOIN usuario a ON a.id = i.administrador_id
      JOIN equipo e ON e.id = i.equipo_id
      JOIN tipo_equipo t ON t.id = e.tipo_equipo_id'''


class IncidenteDAOSQL(IncidenteDAO):
    def __init__(self, conexion):
        self._cx = conexion

    def crear(self, solicitante_id, equipo_id, ubicacion, descripcion, fecha):
        """Crea el incidente en estado ABIERTO y le asigna el consecutivo INC-AAAA-NNNNNN."""
        with self._cx.transaccion():
            nuevo = self._cx.ejecutar(
                '''INSERT INTO incidente (solicitante_id, equipo_id, ubicacion, descripcion, estado, fecha_apertura,
                                          actualizado_por, actualizado_en)
                   VALUES (?, ?, ?, ?, 'ABIERTO', ?, ?, ?)''',
                (solicitante_id, equipo_id, ubicacion, descripcion, fecha, solicitante_id, fecha))
            self._cx.ejecutar('UPDATE incidente SET codigo = ? WHERE id = ?',
                              (f'INC-{fecha[:4]}-{nuevo:06d}', nuevo))
        return nuevo

    def por_id(self, incidente_id):
        return IncidenteDTO.desde_fila(self._cx.uno(f'{_SQL_INCIDENTE} WHERE i.id = ?', (incidente_id,)))

    def listar(self, filtros):
        """filtros: estado, categoria, inventario, solicitante_id, administrador_id, desde, hasta, texto."""
        condiciones, p = [], []
        f = filtros or {}
        if f.get('estado'):
            condiciones.append('i.estado = ?'); p.append(f['estado'])
        if f.get('categoria'):
            condiciones.append('i.categoria_codigo = ?'); p.append(f['categoria'])
        if f.get('inventario'):
            condiciones.append('UPPER(e.inventario) LIKE UPPER(?)'); p.append(f"%{f['inventario']}%")
        if f.get('solicitante_id'):
            condiciones.append('i.solicitante_id = ?'); p.append(f['solicitante_id'])
        if f.get('administrador_id'):
            condiciones.append('i.administrador_id = ?'); p.append(f['administrador_id'])
        if f.get('sin_asignar'):
            condiciones.append('i.administrador_id IS NULL')
        if f.get('desde'):
            condiciones.append('i.fecha_apertura >= ?'); p.append(f"{f['desde']} 00:00:00")
        if f.get('hasta'):
            condiciones.append('i.fecha_apertura <= ?'); p.append(f"{f['hasta']} 23:59:59")
        if f.get('texto'):
            condiciones.append('(UPPER(i.descripcion) LIKE UPPER(?) OR UPPER(i.codigo) LIKE UPPER(?))')
            p += [f"%{f['texto']}%"] * 2
        where = f" WHERE {' AND '.join(condiciones)}" if condiciones else ''
        return [IncidenteDTO.desde_fila(x) for x in self._cx.consultar(f'{_SQL_INCIDENTE}{where} ORDER BY i.id DESC', p)]

    def asignar(self, incidente_id, administrador_id, usuario_id, fecha):
        self._cx.ejecutar('UPDATE incidente SET administrador_id = ?, actualizado_por = ?, actualizado_en = ? WHERE id = ?',
                          (administrador_id, usuario_id, fecha, incidente_id))

    def cambiar_estado(self, incidente_id, estado, usuario_id, fecha, categoria_codigo=None):
        cierre = fecha if estado == 'CERRADO' else None
        self._cx.ejecutar(
            '''UPDATE incidente SET estado = ?, fecha_cierre = ?, categoria_codigo = COALESCE(?, categoria_codigo),
                                    actualizado_por = ?, actualizado_en = ?
                WHERE id = ?''', (estado, cierre, categoria_codigo, usuario_id, fecha, incidente_id))

    def historial(self, incidente_id):
        return [EventoHistorialDTO.desde_fila(f) for f in self._cx.consultar(
            '''SELECT h.*, u.nombre AS usuario FROM incidente_historial h LEFT JOIN usuario u ON u.id = h.usuario_id
                WHERE h.incidente_id = ? ORDER BY h.id''', (incidente_id,))]

    def de_equipo(self, equipo_id):
        return [IncidenteDTO.desde_fila(x) for x in self._cx.consultar(
            f'{_SQL_INCIDENTE} WHERE i.equipo_id = ? ORDER BY i.fecha_apertura, i.id', (equipo_id,))]


# =====================================================================  citas
_SQL_CITA = '''SELECT c.*, a.nombre AS administrador, i.codigo AS incidente_codigo
                 FROM cita c JOIN usuario a ON a.id = c.administrador_id JOIN incidente i ON i.id = c.incidente_id'''


class CitaDAOSQL(CitaDAO):
    def __init__(self, conexion):
        self._cx = conexion

    def crear(self, incidente_id, administrador_id, inicio, fin, lugar, creado_por, fecha):
        return self._cx.ejecutar(
            '''INSERT INTO cita (incidente_id, administrador_id, inicio, fin, lugar, estado, creado_por, creado_en)
               VALUES (?, ?, ?, ?, ?, 'PROGRAMADA', ?, ?)''',
            (incidente_id, administrador_id, inicio, fin, lugar, creado_por, fecha))

    def por_id(self, cita_id):
        return CitaDTO.desde_fila(self._cx.uno(f'{_SQL_CITA} WHERE c.id = ?', (cita_id,)))

    def de_incidente(self, incidente_id):
        return [CitaDTO.desde_fila(f) for f in self._cx.consultar(
            f'{_SQL_CITA} WHERE c.incidente_id = ? ORDER BY c.inicio', (incidente_id,))]

    def listar(self, administrador_id=None, solicitante_id=None, desde=None):
        condiciones, p = [], []
        if administrador_id:
            condiciones.append('c.administrador_id = ?'); p.append(administrador_id)
        if solicitante_id:
            condiciones.append('i.solicitante_id = ?'); p.append(solicitante_id)
        if desde:
            condiciones.append('c.inicio >= ?'); p.append(desde)
        where = f" WHERE {' AND '.join(condiciones)}" if condiciones else ''
        return [CitaDTO.desde_fila(f) for f in self._cx.consultar(f'{_SQL_CITA}{where} ORDER BY c.inicio', p)]

    def reprogramar(self, cita_id, inicio, fin, lugar):
        self._cx.ejecutar('UPDATE cita SET inicio = ?, fin = ?, lugar = ? WHERE id = ?', (inicio, fin, lugar, cita_id))

    def cambiar_estado(self, cita_id, estado):
        self._cx.ejecutar('UPDATE cita SET estado = ? WHERE id = ?', (estado, cita_id))


# =====================================================================  diagnóstico
class DiagnosticoDAOSQL(DiagnosticoDAO):
    def __init__(self, conexion):
        self._cx = conexion

    def crear(self, incidente_id, registrado_por, parametros, datos, fecha):
        ronda = 1
        if incidente_id:
            ronda = self._cx.uno('SELECT COALESCE(MAX(ronda), 0) + 1 AS r FROM diagnostico WHERE incidente_id = ?',
                                 (incidente_id,))['r']
        return self._cx.ejecutar(
            '''INSERT INTO diagnostico (incidente_id, ronda, registrado_por, estado, parametros, equipo_texto,
                                        ubicacion_texto, descripcion, fecha_inicio)
               VALUES (?, ?, ?, 'EN_CURSO', ?, ?, ?, ?, ?)''',
            (incidente_id, ronda, registrado_por, parametros, (datos.get('equipo') or None),
             (datos.get('ubicacion') or None), (datos.get('descripcion') or None), fecha))

    def guardar_respuesta(self, diagnostico_id, orden, evidencia_codigo, escala_codigo, valor, origen, fecha):
        existe = self._cx.uno('SELECT id FROM incidente_evidencia WHERE diagnostico_id = ? AND evidencia_codigo = ?',
                              (diagnostico_id, evidencia_codigo))
        if existe:
            self._cx.ejecutar('UPDATE incidente_evidencia SET escala_codigo = ?, valor = ?, registrado_en = ? WHERE id = ?',
                              (escala_codigo, valor, fecha, existe['id']))
        else:
            self._cx.ejecutar(
                '''INSERT INTO incidente_evidencia (diagnostico_id, orden, evidencia_codigo, escala_codigo, valor, origen,
                                                    registrado_en)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (diagnostico_id, orden, evidencia_codigo, escala_codigo, valor, origen, fecha))

    def finalizar(self, diagnostico_id, total_preguntas, propuestas, fecha):
        """propuestas: lista de dict con posicion, hipotesis_codigo, hipotesis_nombre, granulo_codigo,
        granulo_version, conclusion, accion, probabilidad y certeza."""
        with self._cx.transaccion():
            for p in propuestas:
                self._cx.ejecutar(
                    '''INSERT INTO diagnostico_hipotesis (diagnostico_id, posicion, hipotesis_codigo, hipotesis_nombre,
                                                          granulo_codigo, granulo_version, conclusion, accion,
                                                          probabilidad, certeza, estado)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROPUESTA')''',
                    (diagnostico_id, p['posicion'], p['hipotesis_codigo'], p['hipotesis_nombre'], p['granulo_codigo'],
                     p['granulo_version'], p['conclusion'], p['accion'], round(p['probabilidad'], 5),
                     round(max(-1.0, min(1.0, p['certeza'])), 4)))
            self._cx.ejecutar("UPDATE diagnostico SET estado = 'FINALIZADO', fecha_fin = ?, total_preguntas = ? WHERE id = ?",
                              (fecha, total_preguntas, diagnostico_id))

    def cancelar(self, diagnostico_id, fecha):
        self._cx.ejecutar("UPDATE diagnostico SET estado = 'CANCELADO', fecha_fin = ? WHERE id = ? AND estado = 'EN_CURSO'",
                          (fecha, diagnostico_id))

    _SQL = '''SELECT d.*, i.codigo AS incidente_codigo, u.nombre AS administrador,
                     dh.hipotesis_codigo, dh.hipotesis_nombre, dh.probabilidad
                FROM diagnostico d
                LEFT JOIN incidente i ON i.id = d.incidente_id
                LEFT JOIN usuario u ON u.id = d.registrado_por
                LEFT JOIN diagnostico_hipotesis dh ON dh.diagnostico_id = d.id AND dh.posicion = 1'''

    def por_id(self, diagnostico_id):
        return DiagnosticoDTO.desde_fila(self._cx.uno(f'{self._SQL} WHERE d.id = ?', (diagnostico_id,)))

    def respuestas(self, diagnostico_id):
        return [RespuestaDTO.desde_fila(f) for f in self._cx.consultar(
            '''SELECT orden, evidencia_codigo, escala_codigo, valor, origen FROM incidente_evidencia
                WHERE diagnostico_id = ? ORDER BY orden''', (diagnostico_id,))]

    def hipotesis(self, diagnostico_id):
        return [HipotesisPropuestaDTO.desde_fila(f) for f in self._cx.consultar(
            '''SELECT dh.*, d.ronda FROM diagnostico_hipotesis dh JOIN diagnostico d ON d.id = dh.diagnostico_id
                WHERE dh.diagnostico_id = ? ORDER BY dh.posicion''', (diagnostico_id,))]

    def de_incidente(self, incidente_id):
        return [DiagnosticoDTO.desde_fila(f) for f in self._cx.consultar(
            f'{self._SQL} WHERE d.incidente_id = ? ORDER BY d.ronda', (incidente_id,))]

    def listar(self, limite=200):
        return [DiagnosticoDTO.desde_fila(f) for f in self._cx.consultar(
            f"{self._SQL} WHERE d.estado <> 'CANCELADO' ORDER BY d.id DESC LIMIT ?", (limite,))]

    def propuesta(self, diagnostico_hipotesis_id):
        return HipotesisPropuestaDTO.desde_fila(self._cx.uno(
            '''SELECT dh.*, d.ronda FROM diagnostico_hipotesis dh JOIN diagnostico d ON d.id = dh.diagnostico_id
                WHERE dh.id = ?''', (diagnostico_hipotesis_id,)))

    def decidir(self, diagnostico_hipotesis_id, estado):
        self._cx.ejecutar('UPDATE diagnostico_hipotesis SET estado = ? WHERE id = ?', (estado, diagnostico_hipotesis_id))

    def descartadas_de_incidente(self, incidente_id):
        """Hipótesis que no deben volver a proponerse: las descartadas y las confirmadas cuya solución falló."""
        filas = self._cx.consultar(
            '''SELECT DISTINCT dh.hipotesis_codigo
                 FROM diagnostico_hipotesis dh
                 JOIN diagnostico d ON d.id = dh.diagnostico_id
                 LEFT JOIN intervencion iv ON iv.diagnostico_hipotesis_id = dh.id
                WHERE d.incidente_id = ?
                  AND (dh.estado = 'DESCARTADA' OR iv.resultado = 'NO_SOLUCIONADO')''', (incidente_id,))
        return [f['hipotesis_codigo'] for f in filas]


class IntervencionDAOSQL(IntervencionDAO):
    def __init__(self, conexion):
        self._cx = conexion

    def registrar(self, diagnostico_hipotesis_id, administrador_id, accion, resultado, tiempo_min, observaciones, fecha):
        return self._cx.ejecutar(
            '''INSERT INTO intervencion (diagnostico_hipotesis_id, administrador_id, accion_aplicada, resultado,
                                         tiempo_min, observaciones, registrado_en)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (diagnostico_hipotesis_id, administrador_id, accion, resultado, tiempo_min, observaciones, fecha))

    def de_incidente(self, incidente_id):
        return [IntervencionDTO.desde_fila(f) for f in self._cx.consultar(
            '''SELECT iv.*, u.nombre AS administrador, dh.hipotesis_codigo, dh.hipotesis_nombre, d.ronda
                 FROM intervencion iv
                 JOIN diagnostico_hipotesis dh ON dh.id = iv.diagnostico_hipotesis_id
                 JOIN diagnostico d ON d.id = dh.diagnostico_id
                 JOIN usuario u ON u.id = iv.administrador_id
                WHERE d.incidente_id = ? ORDER BY iv.id''', (incidente_id,))]


class EscalamientoDAOSQL(EscalamientoDAO):
    def __init__(self, conexion):
        self._cx = conexion

    def registrar(self, incidente_id, motivo, destino, escalado_por, fecha):
        return self._cx.ejecutar(
            'INSERT INTO escalamiento (incidente_id, motivo, destino, escalado_por, escalado_en) VALUES (?, ?, ?, ?, ?)',
            (incidente_id, motivo, destino, escalado_por, fecha))

    def de_incidente(self, incidente_id):
        return [EscalamientoDTO.desde_fila(f) for f in self._cx.consultar(
            '''SELECT e.*, u.nombre AS administrador FROM escalamiento e JOIN usuario u ON u.id = e.escalado_por
                WHERE e.incidente_id = ? ORDER BY e.id''', (incidente_id,))]


class AuditoriaDAOSQL(AuditoriaDAO):
    def __init__(self, conexion):
        self._cx = conexion

    def registrar(self, entidad, codigo, version, accion, usuario_id, detalle, fecha):
        self._cx.ejecutar(
            '''INSERT INTO auditoria_conocimiento (entidad, codigo, version, accion, usuario_id, detalle, fecha)
               VALUES (?, ?, ?, ?, ?, ?, ?)''', (entidad, codigo, version, accion, usuario_id, detalle, fecha))

    def listar(self, codigo=None, limite=100):
        where, p = ('WHERE a.codigo = ?', [codigo]) if codigo else ('', [])
        return [AuditoriaDTO.desde_fila(f) for f in self._cx.consultar(
            f'''SELECT a.*, u.nombre AS usuario FROM auditoria_conocimiento a LEFT JOIN usuario u ON u.id = a.usuario_id
                 {where} ORDER BY a.id DESC LIMIT ?''', p + [limite])]


# =====================================================================  indicadores
class IndicadoresDAOSQL(IndicadoresDAO):
    def __init__(self, conexion):
        self._cx = conexion

    def resumen(self, desde=None, hasta=None):
        cond, p = [], []
        if desde:
            cond.append('i.fecha_apertura >= ?'); p.append(f'{desde} 00:00:00')
        if hasta:
            cond.append('i.fecha_apertura <= ?'); p.append(f'{hasta} 23:59:59')
        where = f" WHERE {' AND '.join(cond)}" if cond else ''
        y = f" AND {' AND '.join(cond)}" if cond else ''
        cx = self._cx
        por_estado = cx.consultar(f'SELECT i.estado, COUNT(*) AS n FROM incidente i{where} GROUP BY i.estado', p)
        por_categoria = cx.consultar(
            f'''SELECT COALESCE(i.categoria_codigo, '-') AS categoria, COUNT(*) AS n FROM incidente i{where}
                 GROUP BY COALESCE(i.categoria_codigo, '-') ORDER BY categoria''', p)
        cerrados = cx.consultar(
            f"SELECT i.id, i.fecha_apertura, i.fecha_cierre FROM incidente i WHERE i.estado = 'CERRADO'{y}", p)
        primera = cx.uno(
            f'''SELECT COUNT(DISTINCT i.id) AS n FROM incidente i
                  JOIN diagnostico d ON d.incidente_id = i.id AND d.ronda = 1
                  JOIN diagnostico_hipotesis dh ON dh.diagnostico_id = d.id
                  JOIN intervencion iv ON iv.diagnostico_hipotesis_id = dh.id AND iv.resultado = 'SOLUCIONADO'
                 WHERE i.estado = 'CERRADO'{y}''', p)['n']
        escalamientos = cx.uno(
            f'SELECT COUNT(*) AS n FROM escalamiento e JOIN incidente i ON i.id = e.incidente_id{where}', p)['n']
        hipotesis = cx.consultar(
            f'''SELECT dh.hipotesis_codigo, dh.hipotesis_nombre, COUNT(*) AS confirmadas,
                       SUM(CASE WHEN iv.resultado = 'SOLUCIONADO' THEN 1 ELSE 0 END) AS solucionadas
                  FROM diagnostico_hipotesis dh
                  JOIN diagnostico d ON d.id = dh.diagnostico_id
                  JOIN incidente i ON i.id = d.incidente_id
                  LEFT JOIN intervencion iv ON iv.diagnostico_hipotesis_id = dh.id
                 WHERE dh.estado = 'CONFIRMADA'{y}
                 GROUP BY dh.hipotesis_codigo, dh.hipotesis_nombre
                 ORDER BY confirmadas DESC, dh.hipotesis_codigo LIMIT 10''', p)
        equipos = cx.consultar(
            f'''SELECT e.inventario, t.nombre AS tipo, COUNT(*) AS incidentes
                  FROM incidente i JOIN equipo e ON e.id = i.equipo_id JOIN tipo_equipo t ON t.id = e.tipo_equipo_id
                  {where} GROUP BY e.inventario, t.nombre ORDER BY incidentes DESC, e.inventario LIMIT 10''', p)
        tiempos = cx.uno(
            f'''SELECT AVG(iv.tiempo_min) AS minutos FROM intervencion iv
                  JOIN diagnostico_hipotesis dh ON dh.id = iv.diagnostico_hipotesis_id
                  JOIN diagnostico d ON d.id = dh.diagnostico_id JOIN incidente i ON i.id = d.incidente_id
                 WHERE iv.tiempo_min IS NOT NULL{y}''', p)['minutos']
        return {'por_estado': por_estado, 'por_categoria': por_categoria, 'cerrados': cerrados,
                'resueltos_primera_ronda': primera, 'escalamientos': escalamientos,
                'hipotesis_confirmadas': hipotesis, 'equipos': equipos, 'minutos_intervencion': tiempos}
