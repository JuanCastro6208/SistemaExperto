"""Conexiones a las dos bases de SEDATI (sedati_kb y sedati_trx) detrás de una misma interfaz.

Las sentencias de los DAO se escriben una sola vez con el marcador «?»; la conexión de MySQL lo
traduce al marcador «%s» de PyMySQL. Las dos conexiones devuelven las filas como diccionarios,
con los DECIMAL como float y las fechas como texto 'AAAA-MM-DD HH:MM:SS', para que la lógica de
negocio no dependa del motor de base de datos.
"""
import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ..configuracion import RAIZ

SCRIPTS_SQLITE_KB = [RAIZ / 'bd' / 'sqlite' / '01_kb_esquema.sql', RAIZ / 'bd' / '02_kb_datos.sql']
SCRIPTS_SQLITE_TRX = [RAIZ / 'bd' / 'sqlite' / '03_trx_esquema.sql', RAIZ / 'bd' / '04_trx_datos.sql']


class ErrorIntegridad(Exception):
    """La base de datos rechazó la operación (llave única, restricción o disparador)."""


def _normalizar(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, datetime):
        return valor.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, bytes):
        return valor.decode('utf-8')
    return valor


class ConexionBD(ABC):
    """Interfaz común de acceso a una base de datos."""

    @abstractmethod
    def consultar(self, sql, parametros=()):
        """Ejecuta un SELECT y devuelve una lista de diccionarios."""

    @abstractmethod
    def ejecutar(self, sql, parametros=()):
        """Ejecuta INSERT / UPDATE y devuelve el id generado (si lo hay)."""

    @abstractmethod
    def transaccion(self):
        """Administrador de contexto: todo lo que se ejecuta dentro se confirma o se deshace junto."""

    @abstractmethod
    def cerrar(self):
        ...

    def verificar(self):
        """Comprueba que la conexión siga viva (en un servicio web se reutiliza entre peticiones)."""

    def uno(self, sql, parametros=()):
        filas = self.consultar(sql, parametros)
        return filas[0] if filas else None

    @property
    @abstractmethod
    def descripcion(self):
        ...


class ConexionSQLite(ConexionBD):
    def __init__(self, ruta, scripts=(), columna_requerida=None):
        """columna_requerida: (tabla, columna) que debe existir; si el archivo es de una versión anterior
        sin ella, se aparta como <archivo>.anterior y la base se crea de nuevo a partir de los scripts."""
        self.ruta = Path(ruta)
        if columna_requerida and self.ruta.exists():
            self._apartar_si_es_anterior(*columna_requerida)
        nueva = not self.ruta.exists()
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._cx = sqlite3.connect(self.ruta, check_same_thread=False)
        self._cx.row_factory = sqlite3.Row
        self._cx.execute('PRAGMA foreign_keys = ON')
        self._en_transaccion = False
        self.creada = False
        if scripts and (nueva or not self._tiene_tablas()):
            for script in scripts:
                self._cx.executescript(Path(script).read_text(encoding='utf-8'))
            self._cx.commit()
            self.creada = True

    def _apartar_si_es_anterior(self, tabla, columna):
        cx = sqlite3.connect(self.ruta)
        try:
            tablas = {f[0] for f in cx.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            columnas = {f[1] for f in cx.execute(f'PRAGMA table_info({tabla})')} if tabla in tablas else set()
        finally:
            cx.close()
        if tablas and columna not in columnas:
            destino = self.ruta.with_name(self.ruta.name + '.anterior')
            destino.unlink(missing_ok=True)
            self.ruta.rename(destino)

    def _tiene_tablas(self):
        return self._cx.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0] > 0

    def consultar(self, sql, parametros=()):
        return [{k: _normalizar(f[k]) for k in f.keys()} for f in self._cx.execute(sql, tuple(parametros)).fetchall()]

    def ejecutar(self, sql, parametros=()):
        try:
            cur = self._cx.execute(sql, tuple(parametros))
        except sqlite3.IntegrityError as e:
            if not self._en_transaccion:
                self._cx.rollback()
            raise ErrorIntegridad(str(e)) from None
        if not self._en_transaccion:
            self._cx.commit()
        return cur.lastrowid

    @contextmanager
    def transaccion(self):
        if self._en_transaccion:
            yield
            return
        self._en_transaccion = True
        try:
            yield
            self._cx.commit()
        except Exception:
            self._cx.rollback()
            raise
        finally:
            self._en_transaccion = False

    def cerrar(self):
        self._cx.close()

    @property
    def descripcion(self):
        return f'SQLite · {self.ruta.name}'


class ConexionMySQL(ConexionBD):
    def __init__(self, host, port, user, password, database):
        import pymysql  # dependencia opcional: solo se necesita con motor = mysql
        self._pymysql = pymysql
        self._db = database
        self._datos = dict(host=host, port=port, user=user, password=password, database=database,
                           charset='utf8mb4', autocommit=True, connect_timeout=10,
                           cursorclass=pymysql.cursors.DictCursor)
        self._cx = pymysql.connect(**self._datos)
        self._en_transaccion = False
        self.creada = False

    def verificar(self):
        # MySQL cierra las conexiones inactivas; Lambda reutiliza la conexión entre invocaciones.
        try:
            self._cx.ping()
        except self._pymysql.err.Error:
            self._cx = self._pymysql.connect(**self._datos)

    @staticmethod
    def _sql(sql):
        return sql.replace('?', '%s')

    def consultar(self, sql, parametros=()):
        with self._cx.cursor() as cur:
            cur.execute(self._sql(sql), tuple(parametros))
            return [{k: _normalizar(v) for k, v in f.items()} for f in cur.fetchall()]

    def ejecutar(self, sql, parametros=()):
        try:
            with self._cx.cursor() as cur:
                cur.execute(self._sql(sql), tuple(parametros))
                return cur.lastrowid
        except (self._pymysql.err.IntegrityError, self._pymysql.err.OperationalError) as e:
            codigo = e.args[0] if e.args else 0
            # 1644: SIGNAL de un disparador; 3819: CHECK; 1062: duplicado; 1451/1452: llave foránea
            if codigo in (1644, 3819, 1062, 1451, 1452, 1048):
                raise ErrorIntegridad(e.args[1] if len(e.args) > 1 else str(e)) from None
            raise

    @contextmanager
    def transaccion(self):
        if self._en_transaccion:
            yield
            return
        self._en_transaccion = True
        self._cx.begin()
        try:
            yield
            self._cx.commit()
        except Exception:
            self._cx.rollback()
            raise
        finally:
            self._en_transaccion = False

    def cerrar(self):
        self._cx.close()

    @property
    def descripcion(self):
        return f'MySQL · {self._db}'


def crear_conexiones(configuracion):
    """Fábrica: devuelve (conexión a sedati_kb, conexión a sedati_trx) según config.ini."""
    if configuracion.motor_bd == 'mysql':
        m = configuracion.mysql
        datos = {k: m[k] for k in ('host', 'port', 'user', 'password')}
        return (ConexionMySQL(database=m['base_kb'], **datos), ConexionMySQL(database=m['base_trx'], **datos))
    kb = ConexionSQLite(configuracion.ruta_sqlite_kb, SCRIPTS_SQLITE_KB)
    trx = ConexionSQLite(configuracion.ruta_sqlite_trx, SCRIPTS_SQLITE_TRX, ('diagnostico', 'nombre_usuario'))
    return kb, trx


@contextmanager
def conexiones_temporales(configuracion):
    kb, trx = crear_conexiones(configuracion)
    try:
        yield kb, trx
    finally:
        kb.cerrar()
        trx.cerrar()
