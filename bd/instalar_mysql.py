"""Instala las dos bases de SEDATI (sedati_kb y sedati_trx) en un servidor MySQL 8.

    python bd/instalar_mysql.py --host localhost --usuario root
    python bd/instalar_mysql.py --host <punto de enlace de RDS> --usuario admin --usuario-servicio sedati_app

Ejecuta, en orden, los mismos scripts que se abren en MySQL Workbench:
    bd/mysql/01_kb_esquema.sql                        base de conocimiento: hipotesis, evidencia, granulo
    bd/02_kb_datos.sql                                conocimiento del experto (38 hipótesis, 88 reglas)
    bd/mysql/03_trx_esquema.sql                       base transaccional (18 tablas y sus disparadores)
    bd/04_trx_datos.sql                               catálogos, matriz de permisos y cuentas de demostración
    bd/mysql/05_roles_permisos.sql                    roles de MySQL equivalentes a los del sistema
    bd/mysql/06_consultas_granulos_por_hipotesis.sql  vistas y procedimientos de consulta de la BC

Con --demo carga además incidentes de demostración usando la propia capa de negocio.
Con --usuario-servicio crea el usuario de MySQL de la aplicación con el rol sedati_aplicacion.

ATENCIÓN: los scripts de esquema borran y vuelven a crear las tablas.
"""
import argparse
import getpass
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SCRIPTS = [RAIZ / 'bd' / 'mysql' / '01_kb_esquema.sql',
           RAIZ / 'bd' / '02_kb_datos.sql',
           RAIZ / 'bd' / 'mysql' / '03_trx_esquema.sql',
           RAIZ / 'bd' / '04_trx_datos.sql',
           RAIZ / 'bd' / 'mysql' / '05_roles_permisos.sql',
           RAIZ / 'bd' / 'mysql' / '06_consultas_granulos_por_hipotesis.sql']
USO_BASE = {'02_kb_datos.sql': 'sedati_kb', '04_trx_datos.sql': 'sedati_trx'}


def sentencias(texto):
    """Divide un script en sentencias respetando DELIMITER (que es del cliente, no del servidor)."""
    delimitador, actual, salida = ';', [], []
    for linea in texto.splitlines():
        m = re.match(r'^\s*DELIMITER\s+(\S+)\s*$', linea, re.IGNORECASE)
        if m:
            delimitador = m.group(1)
            continue
        actual.append(linea)
        if linea.rstrip().endswith(delimitador):
            sentencia = '\n'.join(actual).rstrip()
            sentencia = sentencia[: -len(delimitador)].strip()
            if sentencia and not all(l.strip().startswith('--') or not l.strip() for l in sentencia.splitlines()):
                salida.append(sentencia)
            actual = []
    resto = '\n'.join(actual).strip()
    if resto and not all(l.strip().startswith('--') or not l.strip() for l in resto.splitlines()):
        salida.append(resto)
    return salida


def ejecutar_script(cx, ruta, mostrar=True):
    base = USO_BASE.get(ruta.name)
    with cx.cursor() as cur:
        if base:
            cur.execute(f'USE {base}')
        for s in sentencias(ruta.read_text(encoding='utf-8')):
            try:
                cur.execute(s)
            except Exception as e:  # noqa: BLE001
                # En Amazon RDS la cuenta maestra puede no tener ROLE_ADMIN para dar un rol a otro rol (error 1227).
                if ruta.name == '05_roles_permisos.sql' and getattr(e, 'args', [0])[0] == 1227:
                    print(f'  ! sin permiso para: {s.splitlines()[0][:70]} (se otorgará directo al usuario de servicio)')
                    continue
                raise
            while cur.nextset():
                pass
    if mostrar:
        print(f'  ✔ {ruta.relative_to(RAIZ).as_posix()}')


def crear_usuario_servicio(cx, usuario, contrasena):
    if not re.fullmatch(r'[A-Za-z0-9_]{1,32}', usuario):
        raise SystemExit('El nombre del usuario de servicio solo puede tener letras, números y «_».')
    with cx.cursor() as cur:
        cur.execute(f"CREATE USER IF NOT EXISTS '{usuario}'@'%%' IDENTIFIED BY %s", (contrasena,))
        cur.execute(f"ALTER USER '{usuario}'@'%%' IDENTIFIED BY %s", (contrasena,))
        try:
            cur.execute(f"GRANT sedati_aplicacion TO '{usuario}'@'%'")
            cur.execute(f"SET DEFAULT ROLE sedati_aplicacion TO '{usuario}'@'%'")
            print(f"  ✔ usuario de servicio '{usuario}' con el rol sedati_aplicacion")
        except Exception:  # noqa: BLE001 - p. ej. RDS sin ROLE_ADMIN: los mismos permisos, otorgados directamente
            cur.execute(f"GRANT SELECT, INSERT, UPDATE ON sedati_trx.* TO '{usuario}'@'%'")
            cur.execute(f"GRANT SELECT, INSERT, UPDATE, EXECUTE ON sedati_kb.* TO '{usuario}'@'%'")
            print(f"  ✔ usuario de servicio '{usuario}' con SELECT, INSERT y UPDATE (sin DELETE) en las dos bases")


def conectar(host, puerto, usuario, contrasena, base=None):
    import pymysql
    return pymysql.connect(host=host, port=puerto, user=usuario, password=contrasena, database=base,
                           charset='utf8mb4', autocommit=True, connect_timeout=15)


def cargar_demostracion(host, puerto, usuario, contrasena):
    """Incidentes de demostración creados con la propia capa de negocio (ver sedati/servicio/demostracion.py)."""
    from dataclasses import replace
    from sedati.configuracion import cargar_configuracion
    from sedati.servicio import ApiSEDATI
    from sedati.servicio.demostracion import cargar_demostracion as cargar
    conf = replace(cargar_configuracion(), motor_bd='mysql', datos_demostracion=False,
                   mysql={'host': host, 'port': puerto, 'user': usuario, 'password': contrasena,
                          'base_kb': 'sedati_kb', 'base_trx': 'sedati_trx'})
    api = ApiSEDATI(conf)
    try:
        cargar(api)
    finally:
        api.fabrica.cerrar()
    print('  ✔ incidentes de demostración')


def main():
    p = argparse.ArgumentParser(description='Instala sedati_kb y sedati_trx en MySQL 8 / Amazon RDS.')
    p.add_argument('--host', default='localhost')
    p.add_argument('--puerto', type=int, default=3306)
    p.add_argument('--usuario', default='root')
    p.add_argument('--contrasena', help='Si no se indica, se pide por teclado')
    p.add_argument('--usuario-servicio', metavar='NOMBRE', help='Crea este usuario para la aplicación')
    p.add_argument('--contrasena-servicio')
    p.add_argument('--demo', action='store_true', help='Carga incidentes de demostración')
    p.add_argument('--si', action='store_true', help='No pedir confirmación')
    a = p.parse_args()

    contrasena = a.contrasena if a.contrasena is not None else getpass.getpass(f'Contraseña de {a.usuario}@{a.host}: ')
    if not a.si:
        r = input('Se borrarán y crearán de nuevo las bases sedati_kb y sedati_trx. ¿Continuar? [s/N] ')
        if r.strip().lower() not in ('s', 'si', 'sí'):
            print('Cancelado.')
            return 1
    print(f'Conectando con {a.host}:{a.puerto}…')
    cx = conectar(a.host, a.puerto, a.usuario, contrasena)
    try:
        for script in SCRIPTS:
            ejecutar_script(cx, script)
        if a.usuario_servicio:
            clave = a.contrasena_servicio or getpass.getpass(f"Contraseña para '{a.usuario_servicio}': ")
            crear_usuario_servicio(cx, a.usuario_servicio, clave)
        with cx.cursor() as cur:
            cur.execute('''SELECT (SELECT COUNT(*) FROM sedati_kb.hipotesis), (SELECT COUNT(*) FROM sedati_kb.evidencia),
                                  (SELECT COUNT(DISTINCT regla) FROM sedati_kb.granulo), (SELECT COUNT(*) FROM sedati_kb.granulo),
                                  (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'sedati_trx'
                                      AND table_type = 'BASE TABLE')''')
            h, e, r, g, t = cur.fetchone()
        print(f'sedati_kb: {h} hipótesis, {e} evidencias, {r} reglas ({g} filas en granulo).')
        print(f'sedati_trx: {t} tablas.')
    finally:
        cx.close()
    if a.demo:
        cargar_demostracion(a.host, a.puerto, a.usuario, contrasena)
    return 0


if __name__ == '__main__':
    sys.exit(main())
