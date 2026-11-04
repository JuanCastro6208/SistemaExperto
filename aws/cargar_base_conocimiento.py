"""Carga la base de conocimiento de SEDATI en Amazon RDS for MySQL (o en cualquier MySQL 8).

    python aws/cargar_base_conocimiento.py --host sedati-bd.xxxxxxxx.us-east-1.rds.amazonaws.com --usuario admin

Ejecuta, en orden, los mismos scripts que se usan en MySQL Workbench:
    bd/mysql/01_esquema.sql        crea la base «sedati» y sus 7 tablas
    bd/02_datos_conocimiento.sql   hipotesis, evidencia y granulo (la base de conocimiento)
    bd/03_datos_operacion.sql      escala de respuestas

Con --usuario-servicio crea además el usuario de MySQL que usará la función Lambda, con permisos
mínimos: solo lectura sobre la base de conocimiento y escritura sobre el registro de consultas.

ATENCIÓN: 01_esquema.sql borra y vuelve a crear las tablas (se pierde el historial de consultas).
"""
import argparse
import getpass
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = [RAIZ / 'bd' / 'mysql' / '01_esquema.sql',
           RAIZ / 'bd' / '02_datos_conocimiento.sql',
           RAIZ / 'bd' / '03_datos_operacion.sql']


def ejecutar_script(cx, ruta):
    with cx.cursor() as cur:
        cur.execute(ruta.read_text(encoding='utf-8'))
        while cur.nextset():      # consume el resultado de cada sentencia del script
            pass
    print(f'  ✔ {ruta.relative_to(RAIZ).as_posix()}')


def crear_usuario_servicio(cx, usuario, contrasena):
    if not re.fullmatch(r'[A-Za-z0-9_]{1,32}', usuario):
        raise SystemExit('El nombre del usuario de servicio solo puede tener letras, números y «_».')
    sentencias = [
        # con parámetros, PyMySQL usa «%» como marcador: el comodín de host se escribe «%%»
        f"CREATE USER IF NOT EXISTS '{usuario}'@'%%' IDENTIFIED BY %s",
        f"ALTER USER '{usuario}'@'%%' IDENTIFIED BY %s",
        f"GRANT SELECT ON sedati.hipotesis TO '{usuario}'@'%'",
        f"GRANT SELECT ON sedati.evidencia TO '{usuario}'@'%'",
        f"GRANT SELECT ON sedati.granulo TO '{usuario}'@'%'",
        f"GRANT SELECT ON sedati.escala_respuesta TO '{usuario}'@'%'",
        f"GRANT SELECT, INSERT, UPDATE ON sedati.consulta TO '{usuario}'@'%'",
        f"GRANT SELECT, INSERT, UPDATE ON sedati.consulta_respuesta TO '{usuario}'@'%'",
        f"GRANT SELECT, INSERT, UPDATE ON sedati.consulta_hipotesis TO '{usuario}'@'%'",
    ]
    with cx.cursor() as cur:
        for s in sentencias:
            cur.execute(s, (contrasena,) if '%s' in s else None)
    print(f"  ✔ usuario de servicio '{usuario}' (lectura de la BC, escritura del historial)")


def main():
    p = argparse.ArgumentParser(description='Carga la base de conocimiento de SEDATI en MySQL / Amazon RDS.')
    p.add_argument('--host', required=True, help='Punto de enlace de la instancia RDS')
    p.add_argument('--puerto', type=int, default=3306)
    p.add_argument('--usuario', default='admin', help='Usuario maestro de RDS')
    p.add_argument('--contrasena', help='Si no se indica, se pide por teclado')
    p.add_argument('--usuario-servicio', metavar='NOMBRE', help='Crea este usuario para la función Lambda')
    p.add_argument('--contrasena-servicio', help='Contraseña del usuario de servicio (si no, se pide por teclado)')
    p.add_argument('--si', action='store_true', help='No pedir confirmación')
    a = p.parse_args()

    import pymysql
    from pymysql.constants import CLIENT

    contrasena = a.contrasena or getpass.getpass(f'Contraseña de {a.usuario}@{a.host}: ')
    if not a.si:
        r = input('Se borrarán y crearán de nuevo las tablas de la base «sedati». ¿Continuar? [s/N] ')
        if r.strip().lower() not in ('s', 'si', 'sí'):
            print('Cancelado.')
            return 1

    print(f'Conectando con {a.host}:{a.puerto}…')
    cx = pymysql.connect(host=a.host, port=a.puerto, user=a.usuario, password=contrasena, charset='utf8mb4',
                         autocommit=True, client_flag=CLIENT.MULTI_STATEMENTS, connect_timeout=15)
    try:
        for script in SCRIPTS:
            ejecutar_script(cx, script)
        if a.usuario_servicio:
            clave = a.contrasena_servicio or getpass.getpass(
                f"Contraseña para el usuario de servicio '{a.usuario_servicio}': ")
            crear_usuario_servicio(cx, a.usuario_servicio, clave)
        with cx.cursor() as cur:
            cur.execute('''SELECT (SELECT COUNT(*) FROM sedati.hipotesis) AS hipotesis,
                                  (SELECT COUNT(*) FROM sedati.evidencia) AS evidencias,
                                  (SELECT COUNT(DISTINCT regla) FROM sedati.granulo) AS reglas,
                                  (SELECT COUNT(*) FROM sedati.granulo) AS filas_granulo''')
            h, e, r, g = cur.fetchone()
        print(f'Base de conocimiento cargada: {h} hipótesis, {e} evidencias, {r} reglas ({g} filas en granulo).')
    finally:
        cx.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
