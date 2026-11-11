"""Modelo relacional de SEDATI obtenido por ingeniería inversa del servidor MySQL 8.

    python diseno/generar_mer.py --host 127.0.0.1 --puerto 3306 --usuario root --contrasena ...

Lee el catálogo del SGBD (information_schema): tablas, columnas, tipos, nulos, llaves primarias,
llaves únicas y llaves foráneas de sedati_kb y sedati_trx. No se escribe ninguna tabla a mano: el
diagrama refleja lo que realmente está creado en el servidor. Escribe en diseno/:

    mr_sedati_kb.dot   modelo relacional de la base de conocimiento (3 tablas)
    mer_sedati.dot     modelo entidad-relación único del proyecto (sedati_kb + sedati_trx)
                       con las referencias lógicas por código entre las dos bases (líneas punteadas)
"""
import argparse
from collections import OrderedDict
from pathlib import Path

DISENO = Path(__file__).resolve().parent

# Referencias por código entre bases (no son llaves foráneas: MySQL no las valida entre bases).
REFERENCIAS_LOGICAS = [
    ('sedati_trx', 'incidente', 'categoria_codigo', 'sedati_kb', 'granulo', 'categoria_codigo'),
    ('sedati_trx', 'incidente_evidencia', 'evidencia_codigo', 'sedati_kb', 'evidencia', 'codigo'),
    ('sedati_trx', 'diagnostico_hipotesis', 'hipotesis_codigo', 'sedati_kb', 'hipotesis', 'codigo'),
    ('sedati_trx', 'diagnostico_hipotesis', 'granulo_codigo', 'sedati_kb', 'granulo', 'regla'),
    ('sedati_trx', 'auditoria_conocimiento', 'codigo', 'sedati_kb', 'granulo', 'regla'),
]
COLOR = {'sedati_kb': ('#8E6CEF', '#F3EFFD'), 'sedati_trx': ('#1F6FEB', '#E7F0FE')}


def leer(cx, bases):
    tablas = OrderedDict()
    with cx.cursor() as cur:
        marcas = ', '.join(['%s'] * len(bases))
        cur.execute(f'''SELECT c.table_schema, c.table_name, c.column_name, c.column_type, c.is_nullable, c.column_key
                          FROM information_schema.columns c
                          JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name
                         WHERE c.table_schema IN ({marcas}) AND t.table_type = 'BASE TABLE'
                         ORDER BY c.table_schema, c.table_name, c.ordinal_position''', bases)
        for esquema, tabla, col, tipo, nulo, clave in cur.fetchall():
            tablas.setdefault((esquema, tabla), []).append({'col': col, 'tipo': tipo, 'nulo': nulo == 'YES',
                                                             'pk': clave == 'PRI', 'uk': clave == 'UNI', 'fk': False})
        cur.execute(f'''SELECT table_schema, table_name, column_name, referenced_table_schema, referenced_table_name,
                               referenced_column_name
                          FROM information_schema.key_column_usage
                         WHERE table_schema IN ({marcas}) AND referenced_table_name IS NOT NULL''', bases)
        fks = cur.fetchall()
        cur.execute(f'''SELECT s.table_schema, s.table_name, s.index_name, s.column_name
                          FROM information_schema.statistics s
                         WHERE s.table_schema IN ({marcas}) AND s.non_unique = 0 AND s.index_name <> 'PRIMARY' ''', bases)
        unicas = cur.fetchall()
    for esquema, tabla, col, *_ in fks:
        for c in tablas[(esquema, tabla)]:
            if c['col'] == col:
                c['fk'] = True
    for esquema, tabla, _, col in unicas:
        for c in tablas[(esquema, tabla)]:
            if c['col'] == col:
                c['uk'] = True
    return tablas, fks


def _nodo(esquema, tabla, columnas, compacto=False):
    borde, fondo = COLOR[esquema]
    filas = []
    for c in columnas:
        if compacto and not (c['pk'] or c['fk'] or c['uk'] or c['col'].endswith('_codigo') or c['col'] in ('codigo', 'regla', 'estado')):
            continue
        marca = ('PK ' if c['pk'] else '') + ('FK ' if c['fk'] else '') + ('UK' if c['uk'] and not c['pk'] else '')
        nombre = f"<B>{c['col']}</B>" if c['pk'] else c['col']
        filas.append(f'<TR><TD ALIGN="LEFT" PORT="{c["col"]}"><FONT POINT-SIZE="9" COLOR="{borde}">{marca.strip() or " "}</FONT></TD>'
                     f'<TD ALIGN="LEFT">{nombre}{"" if not c["nulo"] else " ?"}</TD>'
                     f'<TD ALIGN="LEFT"><FONT COLOR="#5B6676" POINT-SIZE="9">{c["tipo"]}</FONT></TD></TR>')
    ocultas = len(columnas) - len(filas)
    if ocultas:
        filas.append(f'<TR><TD COLSPAN="3" ALIGN="LEFT"><FONT POINT-SIZE="8" COLOR="#8A94A6">… {ocultas} columna(s) más</FONT></TD></TR>')
    return (f'  "{esquema}.{tabla}" [shape=plain, label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="3" '
            f'COLOR="{borde}"><TR><TD COLSPAN="3" BGCOLOR="{fondo}"><B>{tabla}</B></TD></TR>{"".join(filas)}</TABLE>>];')


def _dot(nombre, titulo, tablas, fks, compacto, logicas):
    lineas = [f'digraph "{nombre}" {{',
              f'  graph [rankdir={"TB" if compacto else "LR"}, splines=true, nodesep=0.35, ranksep=0.9, fontname="DejaVu Sans", fontsize=18, '
              f'labelloc=t, label="{titulo}\\n ", pad=0.3, dpi=150];',
              '  node [fontname="DejaVu Sans", fontsize=10];',
              '  edge [color="#2B3A4F", arrowsize=0.8, fontname="DejaVu Sans", fontsize=8];']
    for esquema in dict.fromkeys(e for e, _ in tablas):
        lineas.append(f'  subgraph "cluster_{esquema}" {{ label="{esquema}"; fontsize=14; fontcolor="{COLOR[esquema][0]}"; '
                      f'style="rounded,dashed"; color="{COLOR[esquema][0]}";')
        for (e, t), cols in tablas.items():
            if e == esquema:
                lineas.append('  ' + _nodo(e, t, cols, compacto))
        lineas.append('  }')
    for esquema, tabla, col, resq, rtabla, rcol in fks:
        lineas.append(f'  "{esquema}.{tabla}":"{col}" -> "{resq}.{rtabla}":"{rcol}" '
                      '[arrowhead=teetee, arrowtail=crowodot, dir=both];')
    if logicas:
        for e, t, c, re_, rt, rc in REFERENCIAS_LOGICAS:
            lineas.append(f'  "{e}.{t}":"{c}" -> "{re_}.{rt}":"{rc}" [style=dashed, color="#C9473D", '
                          'arrowhead=open, label="por código", fontcolor="#C9473D"];')
    lineas.append('}')
    return '\n'.join(lineas)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--puerto', type=int, default=3306)
    p.add_argument('--usuario', default='root')
    p.add_argument('--contrasena', default='')
    a = p.parse_args()
    import pymysql
    cx = pymysql.connect(host=a.host, port=a.puerto, user=a.usuario, password=a.contrasena, charset='utf8mb4')
    with cx.cursor() as cur:
        cur.execute('SELECT VERSION()')
        version = cur.fetchone()[0]
    kb, fks_kb = leer(cx, ['sedati_kb'])
    todo, fks = leer(cx, ['sedati_kb', 'sedati_trx'])
    cx.close()
    (DISENO / 'mr_sedati_kb.dot').write_text(_dot(
        'mr_kb', f'Modelo relacional de la base de conocimiento sedati_kb (ingeniería inversa de MySQL {version})',
        kb, fks_kb, False, False), encoding='utf-8')
    (DISENO / 'mer_sedati.dot').write_text(_dot(
        'mer', f'Modelo entidad-relación de SEDATI: sedati_kb + sedati_trx (ingeniería inversa de MySQL {version})',
        todo, fks, True, True), encoding='utf-8')
    print(f'MySQL {version}: {len(kb)} tablas en sedati_kb, {len(todo) - len(kb)} en sedati_trx, {len(fks)} llaves foráneas.')


if __name__ == '__main__':
    main()
