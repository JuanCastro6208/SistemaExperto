"""Conexión a la base de datos (MySQL 8 o SQLite) detrás de una misma interfaz.

Las consultas de los repositorios se escriben una sola vez con el marcador «?»;
la conexión de MySQL lo traduce al marcador «%s» que usa PyMySQL.
"""
import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path

from ..configuracion import RAIZ

SCRIPTS_SQLITE = [RAIZ / 'bd' / 'sqlite' / '01_esquema.sql',
                  RAIZ / 'bd' / '02_datos_conocimiento.sql',
                  RAIZ / 'bd' / '03_datos_operacion.sql']


class ConexionBD(ABC):
    """Interfaz común de acceso a datos."""

    @abstractmethod
    def consultar(self, sql, parametros=()):
        """Ejecuta un SELECT y devuelve una lista de diccionarios."""

    @abstractmethod
    def ejecutar(self, sql, parametros=()):
        """Ejecuta INSERT / UPDATE y devuelve el id generado (si lo hay)."""

    @abstractmethod
    def cerrar(self):
        ...

    def verificar(self):
        """Comprueba que la conexión siga viva (en un servicio web se reutiliza entre peticiones)."""

    @property
    @abstractmethod
    def descripcion(self):
        ...


class ConexionSQLite(ConexionBD):
    def __init__(self, ruta):
        self.ruta = Path(ruta)
        nueva = not self.ruta.exists()
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._cx = sqlite3.connect(self.ruta, check_same_thread=False)
        self._cx.row_factory = sqlite3.Row
        self._cx.execute('PRAGMA foreign_keys = ON')
        if nueva or not self._tiene_conocimiento():
            self.crear_desde_scripts()

    def _tiene_conocimiento(self):
        try:
            return self._cx.execute('SELECT COUNT(*) FROM granulo').fetchone()[0] > 0
        except sqlite3.Error:
            return False

    def crear_desde_scripts(self):
        for script in SCRIPTS_SQLITE:
            self._cx.executescript(script.read_text(encoding='utf-8'))
        self._cx.commit()

    def consultar(self, sql, parametros=()):
        return [dict(f) for f in self._cx.execute(sql, tuple(parametros)).fetchall()]

    def ejecutar(self, sql, parametros=()):
        cur = self._cx.execute(sql, tuple(parametros))
        self._cx.commit()
        return cur.lastrowid

    def cerrar(self):
        self._cx.close()

    @property
    def descripcion(self):
        return f'SQLite · {self.ruta.name}'


class ConexionMySQL(ConexionBD):
    def __init__(self, host, port, user, password, database):
        import pymysql  # dependencia opcional: solo se necesita con motor = mysql
        self._db = database
        self._cx = pymysql.connect(host=host, port=port, user=user, password=password, database=database,
                                   charset='utf8mb4', autocommit=True,
                                   cursorclass=pymysql.cursors.DictCursor)

    def verificar(self):
        # MySQL cierra las conexiones inactivas; Lambda reutiliza la conexión entre invocaciones.
        self._cx.ping(reconnect=True)

    @staticmethod
    def _sql(sql):
        return sql.replace('?', '%s')

    def consultar(self, sql, parametros=()):
        with self._cx.cursor() as cur:
            cur.execute(self._sql(sql), tuple(parametros))
            return [self._normalizar(f) for f in cur.fetchall()]

    @staticmethod
    def _normalizar(fila):
        # PyMySQL entrega DECIMAL como Decimal; la lógica trabaja con float.
        from decimal import Decimal
        return {k: float(v) if isinstance(v, Decimal) else v for k, v in fila.items()}

    def ejecutar(self, sql, parametros=()):
        with self._cx.cursor() as cur:
            cur.execute(self._sql(sql), tuple(parametros))
            return cur.lastrowid

    def cerrar(self):
        self._cx.close()

    @property
    def descripcion(self):
        return f'MySQL · {self._db}'


def crear_conexion(configuracion):
    """Fábrica: devuelve la conexión indicada en config.ini."""
    if configuracion.motor_bd == 'mysql':
        return ConexionMySQL(**configuracion.mysql)
    return ConexionSQLite(configuracion.ruta_sqlite)


@contextmanager
def conexion_temporal(configuracion):
    cx = crear_conexion(configuracion)
    try:
        yield cx
    finally:
        cx.cerrar()
