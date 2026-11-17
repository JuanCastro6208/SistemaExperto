"""DAO de la base transaccional (sedati_trx) sobre SQL. Funcionan igual con MySQL 8 y con SQLite."""
from ..dto import DiagnosticoDTO, HipotesisPropuestaDTO, RespuestaDTO, UsuarioDTO
from .interfaces import CatalogoDAO, DiagnosticoDAO, UsuarioDAO


# =====================================================================  catálogos
class CatalogoDAOSQL(CatalogoDAO):
    def __init__(self, conexion):
        self._cx = conexion

    def escala_respuestas(self):
        return self._cx.consultar('SELECT codigo, etiqueta, valor, orden, color FROM escala_respuesta ORDER BY orden')


# =====================================================================  usuarios
class UsuarioDAOSQL(UsuarioDAO):
    _COLUMNAS = 'id, nombre, correo, contrasena_hash, intentos_fallidos, bloqueado_hasta, ultimo_ingreso, creado_en'

    def __init__(self, conexion):
        self._cx = conexion

    def crear(self, nombre, correo, contrasena_hash, fecha):
        return self._cx.ejecutar('INSERT INTO usuario (nombre, correo, contrasena_hash, creado_en) VALUES (?, ?, ?, ?)',
                                 (nombre, correo.lower(), contrasena_hash, fecha))

    def por_id(self, usuario_id):
        return UsuarioDTO.desde_fila(self._cx.uno(f'SELECT {self._COLUMNAS} FROM usuario WHERE id = ?', (usuario_id,)))

    def por_correo(self, correo):
        return UsuarioDTO.desde_fila(self._cx.uno(f'SELECT {self._COLUMNAS} FROM usuario WHERE correo = ?',
                                                  ((correo or '').lower(),)))

    def registrar_fallo(self, usuario_id, intentos, bloqueado_hasta):
        self._cx.ejecutar('UPDATE usuario SET intentos_fallidos = ?, bloqueado_hasta = ? WHERE id = ?',
                          (intentos, bloqueado_hasta, usuario_id))

    def registrar_ingreso(self, usuario_id, fecha):
        self._cx.ejecutar('UPDATE usuario SET intentos_fallidos = 0, bloqueado_hasta = NULL, ultimo_ingreso = ? '
                          'WHERE id = ?', (fecha, usuario_id))


# =====================================================================  diagnósticos
class DiagnosticoDAOSQL(DiagnosticoDAO):
    def __init__(self, conexion):
        self._cx = conexion

    def crear(self, nombre_usuario, categoria_codigo, parametros, datos, fecha, usuario_id=None):
        return self._cx.ejecutar(
            '''INSERT INTO diagnostico (usuario_id, nombre_usuario, categoria_codigo, estado, parametros, equipo_texto,
                                        ubicacion_texto, descripcion, fecha_inicio)
               VALUES (?, ?, ?, 'EN_CURSO', ?, ?, ?, ?, ?)''',
            (usuario_id, nombre_usuario, categoria_codigo or None, parametros, (datos.get('equipo') or None),
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
                                                          probabilidad, certeza)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (diagnostico_id, p['posicion'], p['hipotesis_codigo'], p['hipotesis_nombre'], p['granulo_codigo'],
                     p['granulo_version'], p['conclusion'], p['accion'], round(p['probabilidad'], 5),
                     round(max(-1.0, min(1.0, p['certeza'])), 4)))
            self._cx.ejecutar("UPDATE diagnostico SET estado = 'FINALIZADO', fecha_fin = ?, total_preguntas = ? WHERE id = ?",
                              (fecha, total_preguntas, diagnostico_id))

    def cancelar(self, diagnostico_id, fecha):
        self._cx.ejecutar("UPDATE diagnostico SET estado = 'CANCELADO', fecha_fin = ? WHERE id = ? AND estado = 'EN_CURSO'",
                          (fecha, diagnostico_id))

    _SQL = '''SELECT d.*, dh.hipotesis_codigo, dh.hipotesis_nombre, dh.probabilidad
                FROM diagnostico d
                LEFT JOIN diagnostico_hipotesis dh ON dh.diagnostico_id = d.id AND dh.posicion = 1'''

    def por_id(self, diagnostico_id):
        return DiagnosticoDTO.desde_fila(self._cx.uno(f'{self._SQL} WHERE d.id = ?', (diagnostico_id,)))

    def respuestas(self, diagnostico_id):
        return [RespuestaDTO.desde_fila(f) for f in self._cx.consultar(
            '''SELECT orden, evidencia_codigo, escala_codigo, valor, origen FROM incidente_evidencia
                WHERE diagnostico_id = ? ORDER BY orden''', (diagnostico_id,))]

    def hipotesis(self, diagnostico_id):
        return [HipotesisPropuestaDTO.desde_fila(f) for f in self._cx.consultar(
            'SELECT * FROM diagnostico_hipotesis WHERE diagnostico_id = ? ORDER BY posicion', (diagnostico_id,))]

    def listar(self, limite=200, nombre_usuario=None, usuario_id=None):
        filtro, parametros = "WHERE d.estado <> 'CANCELADO'", []
        if usuario_id is not None:
            filtro += ' AND d.usuario_id = ?'
            parametros.append(usuario_id)
        if nombre_usuario:
            filtro += ' AND LOWER(d.nombre_usuario) = LOWER(?)'
            parametros.append(nombre_usuario)
        return [DiagnosticoDTO.desde_fila(f) for f in self._cx.consultar(
            f'{self._SQL} {filtro} ORDER BY d.id DESC LIMIT ?', (*parametros, limite))]
