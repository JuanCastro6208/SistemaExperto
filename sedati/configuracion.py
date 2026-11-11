"""Lectura de config.ini.

Cada valor de las secciones [base_datos], [mysql] y [seguridad] se puede reemplazar con una
variable de entorno. Así se configura el servicio en AWS Lambda sin escribir contraseñas en el código:

    SEDATI_MOTOR_BD          sqlite | mysql
    SEDATI_RUTA_SQLITE_KB    archivo SQLite de la base de conocimiento (en Lambda: /tmp/sedati_kb.db)
    SEDATI_RUTA_SQLITE_TRX   archivo SQLite de la base transaccional   (en Lambda: /tmp/sedati_trx.db)
    SEDATI_MYSQL_HOST, SEDATI_MYSQL_PUERTO, SEDATI_MYSQL_USUARIO, SEDATI_MYSQL_CONTRASENA
    SEDATI_MYSQL_BASE_KB, SEDATI_MYSQL_BASE_TRX
    SEDATI_SECRETO           clave con la que se firman las sesiones (obligatoria en Lambda)
    SEDATI_DATOS_DEMO        si | no: cargar incidentes de demostración al crear la base SQLite
"""
import configparser
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ParametrosMotor:
    beta: float = 5.0
    umbral_probabilidad: float = 0.85
    ganancia_minima: float = 0.01
    max_preguntas: int = 20
    hipotesis_resultado: int = 5
    aplicabilidad_base: float = 0.10

    def como_texto(self):
        return (f'beta={self.beta}; umbral={self.umbral_probabilidad}; ganancia_min={self.ganancia_minima}; '
                f'max_preguntas={self.max_preguntas}; hipotesis={self.hipotesis_resultado}; '
                f'aplicabilidad_base={self.aplicabilidad_base}')


@dataclass(frozen=True)
class Configuracion:
    motor_bd: str
    ruta_sqlite_kb: Path
    ruta_sqlite_trx: Path
    mysql: dict
    motor: ParametrosMotor
    secreto: str = ''
    utc_offset_horas: float = -5.0
    datos_demostracion: bool = False

    def ahora(self):
        """Fecha y hora local (Colombia no tiene horario de verano: UTC-5)."""
        return datetime.now(timezone(timedelta(hours=self.utc_offset_horas))).replace(tzinfo=None, microsecond=0)


def _valor(seccion, clave, variable, defecto):
    """Valor de la variable de entorno si existe; si no, el de config.ini; si no, el por defecto."""
    return os.environ.get(variable) or seccion.get(clave, defecto)


def _ruta(texto):
    ruta = Path(texto)
    return ruta if ruta.is_absolute() else RAIZ / ruta


def _secreto_local(ruta_trx):
    """Sin secreto configurado (uso local con SQLite) se genera uno y se guarda junto a la base."""
    archivo = Path(ruta_trx).with_name('.secreto_sesiones')
    try:
        if archivo.exists():
            return archivo.read_text(encoding='utf-8').strip()
        archivo.parent.mkdir(parents=True, exist_ok=True)
        clave = secrets.token_hex(32)
        archivo.write_text(clave, encoding='utf-8')
        return clave
    except OSError:
        return secrets.token_hex(32)


def cargar_configuracion(ruta=None):
    ruta = Path(ruta) if ruta else RAIZ / 'config.ini'
    cp = configparser.ConfigParser()
    cp.read(ruta, encoding='utf-8')
    bd = cp['base_datos'] if cp.has_section('base_datos') else {}
    my = cp['mysql'] if cp.has_section('mysql') else {}
    mo = cp['motor'] if cp.has_section('motor') else {}
    se = cp['seguridad'] if cp.has_section('seguridad') else {}
    ruta_trx = _ruta(_valor(bd, 'ruta_sqlite_trx', 'SEDATI_RUTA_SQLITE_TRX', 'bd/sedati_trx.db'))
    motor_bd = _valor(bd, 'motor', 'SEDATI_MOTOR_BD', 'sqlite').strip().lower()
    secreto = _valor(se, 'secreto', 'SEDATI_SECRETO', '').strip()
    if not secreto:
        secreto = _secreto_local(ruta_trx)
    return Configuracion(
        motor_bd=motor_bd,
        ruta_sqlite_kb=_ruta(_valor(bd, 'ruta_sqlite_kb', 'SEDATI_RUTA_SQLITE_KB', 'bd/sedati_kb.db')),
        ruta_sqlite_trx=ruta_trx,
        mysql={
            'host': _valor(my, 'host', 'SEDATI_MYSQL_HOST', 'localhost'),
            'port': int(_valor(my, 'puerto', 'SEDATI_MYSQL_PUERTO', '3306')),
            'user': _valor(my, 'usuario', 'SEDATI_MYSQL_USUARIO', 'root'),
            'password': _valor(my, 'contrasena', 'SEDATI_MYSQL_CONTRASENA', ''),
            'base_kb': _valor(my, 'base_kb', 'SEDATI_MYSQL_BASE_KB', 'sedati_kb'),
            'base_trx': _valor(my, 'base_trx', 'SEDATI_MYSQL_BASE_TRX', 'sedati_trx'),
        },
        motor=ParametrosMotor(
            beta=float(mo.get('beta', 5.0)),
            umbral_probabilidad=float(mo.get('umbral_probabilidad', 0.85)),
            ganancia_minima=float(mo.get('ganancia_minima', 0.01)),
            max_preguntas=int(mo.get('max_preguntas', 20)),
            hipotesis_resultado=int(mo.get('hipotesis_resultado', 5)),
            aplicabilidad_base=float(mo.get('aplicabilidad_base', 0.10)),
        ),
        secreto=secreto,
        utc_offset_horas=float(_valor(se, 'utc_offset_horas', 'SEDATI_UTC_OFFSET', '-5')),
        datos_demostracion=_valor(bd, 'datos_demostracion', 'SEDATI_DATOS_DEMO', 'si').strip().lower()
        in ('si', 'sí', '1', 'true', 'yes'),
    )
