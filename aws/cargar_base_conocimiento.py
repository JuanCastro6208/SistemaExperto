"""Carga las dos bases de SEDATI (sedati_kb y sedati_trx) en Amazon RDS for MySQL.

Se conserva por compatibilidad con la guía de despliegue: hace lo mismo que bd/instalar_mysql.py.

    python aws/cargar_base_conocimiento.py --host <endpoint-rds> --usuario admin --usuario-servicio sedati_app
"""
import runpy
import sys
from pathlib import Path

if __name__ == '__main__':
    sys.argv[0] = 'bd/instalar_mysql.py'
    runpy.run_path(str(Path(__file__).resolve().parent.parent / 'bd' / 'instalar_mysql.py'), run_name='__main__')
