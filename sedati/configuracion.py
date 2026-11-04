"""Lectura de config.ini.

Cada valor de las secciones [base_datos] y [mysql] se puede reemplazar con una variable de
entorno. Así se configura el servicio en AWS Lambda sin escribir contraseñas en el código:

    SEDATI_MOTOR_BD      sqlite | mysql
    SEDATI_RUTA_SQLITE   ruta del archivo SQLite (en Lambda: /tmp/sedati.db)
    SEDATI_MYSQL_HOST, SEDATI_MYSQL_PUERTO, SEDATI_MYSQL_USUARIO, SEDATI_MYSQL_CONTRASENA, SEDATI_MYSQL_BASE
"""
import configparser
import os
from dataclasses import dataclass
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
    ruta_sqlite: Path
    mysql: dict
    motor: ParametrosMotor


def _valor(seccion, clave, variable, defecto):
    """Valor de la variable de entorno si existe; si no, el de config.ini; si no, el por defecto."""
    return os.environ.get(variable) or seccion.get(clave, defecto)


def cargar_configuracion(ruta=None):
    ruta = Path(ruta) if ruta else RAIZ / 'config.ini'
    cp = configparser.ConfigParser()
    cp.read(ruta, encoding='utf-8')
    bd = cp['base_datos'] if cp.has_section('base_datos') else {}
    my = cp['mysql'] if cp.has_section('mysql') else {}
    mo = cp['motor'] if cp.has_section('motor') else {}
    ruta_sqlite = Path(_valor(bd, 'ruta_sqlite', 'SEDATI_RUTA_SQLITE', 'bd/sedati.db'))
    if not ruta_sqlite.is_absolute():
        ruta_sqlite = RAIZ / ruta_sqlite
    return Configuracion(
        motor_bd=_valor(bd, 'motor', 'SEDATI_MOTOR_BD', 'sqlite').strip().lower(),
        ruta_sqlite=ruta_sqlite,
        mysql={
            'host': _valor(my, 'host', 'SEDATI_MYSQL_HOST', 'localhost'),
            'port': int(_valor(my, 'puerto', 'SEDATI_MYSQL_PUERTO', '3306')),
            'user': _valor(my, 'usuario', 'SEDATI_MYSQL_USUARIO', 'root'),
            'password': _valor(my, 'contrasena', 'SEDATI_MYSQL_CONTRASENA', ''),
            'database': _valor(my, 'base', 'SEDATI_MYSQL_BASE', 'sedati'),
        },
        motor=ParametrosMotor(
            beta=float(mo.get('beta', 5.0)),
            umbral_probabilidad=float(mo.get('umbral_probabilidad', 0.85)),
            ganancia_minima=float(mo.get('ganancia_minima', 0.01)),
            max_preguntas=int(mo.get('max_preguntas', 20)),
            hipotesis_resultado=int(mo.get('hipotesis_resultado', 5)),
            aplicabilidad_base=float(mo.get('aplicabilidad_base', 0.10)),
        ),
    )
