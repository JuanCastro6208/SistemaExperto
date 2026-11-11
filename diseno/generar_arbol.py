"""Genera el árbol de decisión de SEDATI a partir de la base de conocimiento (Graphviz).

    python diseno/generar_arbol.py            # escribe diseno/arbol/*.dot
    (para dibujarlos: dot -Tpng -Gdpi=150 archivo.dot -o archivo.png)

El árbol no se dibuja a mano: se arma con las mismas 88 reglas que usa el motor, así figura y base
de conocimiento siempre coinciden. Cada camino raíz → hoja es una regla: los nodos internos son las
condiciones (If / And) y la hoja es la conclusión (Then) con su código de regla y su factor de certeza.

    arbol_general.dot    raíz → 7 categorías → 22 ramas, con las fallas (hojas) de cada rama
    rama_A1.dot ...      una figura por rama, con todas sus reglas
"""
import sqlite3
import textwrap
from collections import OrderedDict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = Path(__file__).resolve().parent / 'arbol'

COLORES = {'A': '#E8F0FE', 'B': '#E6F4EA', 'C': '#FEF7E0', 'D': '#FCE8E6', 'E': '#F3E8FD', 'F': '#E0F7FA',
           'G': '#FFF0E0'}
BORDES = {'A': '#1F6FEB', 'B': '#1E8E5A', 'C': '#B7791F', 'D': '#C9473D', 'E': '#8E6CEF', 'F': '#0F8B8D',
          'G': '#D9822B'}


def cargar():
    cx = sqlite3.connect(':memory:')
    for s in ('sqlite/01_kb_esquema.sql', '02_kb_datos.sql'):
        cx.executescript((RAIZ / 'bd' / s).read_text(encoding='utf-8'))
    cx.row_factory = sqlite3.Row
    filas = cx.execute('''SELECT g.regla, g.orden, g.conector, g.categoria_codigo, g.categoria_nombre, g.rama_codigo,
                                 g.rama_nombre, g.procesos, g.conclusion, g.factor_certeza, e.codigo AS ev, e.enunciado,
                                 h.codigo AS hip, h.nombre AS hipotesis
                            FROM granulo g JOIN evidencia e ON e.id = g.evidencia_id JOIN hipotesis h ON h.id = g.hipotesis_id
                           WHERE g.activo = 1 ORDER BY g.rama_codigo, CAST(SUBSTR(g.regla, 3) AS INTEGER), g.orden''').fetchall()
    ramas = OrderedDict()
    for f in filas:
        r = ramas.setdefault(f['rama_codigo'], {'codigo': f['rama_codigo'], 'nombre': f['rama_nombre'],
                                               'categoria': f['categoria_codigo'], 'categoria_nombre': f['categoria_nombre'],
                                               'procesos': f['procesos'], 'reglas': OrderedDict()})
        regla = r['reglas'].setdefault(f['regla'], {'regla': f['regla'], 'conclusion': f['conclusion'],
                                                    'fc': f['factor_certeza'], 'hip': f['hip'], 'condiciones': []})
        regla['condiciones'].append((f['ev'], f['enunciado']))
    return ramas


def _texto(t, ancho=26):
    return '\\n'.join(textwrap.wrap(t, ancho)).replace('"', '\\"')


def _encabezado(nombre, rankdir='LR'):
    return [f'digraph "{nombre}" {{',
            f'  graph [rankdir={rankdir}, splines=true, nodesep=0.22, ranksep=0.55, fontname="DejaVu Sans", bgcolor="white", pad=0.2];',
            '  node [shape=box, style="rounded,filled", fillcolor="#FFFFFF", color="#5B6676", fontname="DejaVu Sans", fontsize=10, margin="0.10,0.05"];',
            '  edge [color="#8A94A6", fontname="DejaVu Sans", fontsize=8, fontcolor="#5B6676", arrowsize=0.6];']


def rama_dot(r):
    """Trie de las condiciones de las reglas de una rama: caminos comunes se comparten."""
    cat = r['categoria']
    lineas = _encabezado(f"rama_{r['codigo']}")
    lineas.append(f'  raiz [label="{r["codigo"]} · {_texto(r["nombre"], 30)}\\n({r["procesos"]})", shape=box, '
                  f'style="rounded,filled,bold", fillcolor="{COLORES[cat]}", color="{BORDES[cat]}", fontsize=11];')
    nodos = {}
    contador = 0
    for regla in r['reglas'].values():
        padre = 'raiz'
        camino = ()
        for i, (ev, enunciado) in enumerate(regla['condiciones']):
            camino = camino + (ev,)
            if camino not in nodos:
                contador += 1
                nodo = f'n{contador}'
                nodos[camino] = nodo
                lineas.append(f'  {nodo} [label="{_texto(enunciado)}\\n[{ev}]"];')
                lineas.append(f'  {padre} -> {nodo} [label="{"If" if i == 0 else "And"}"];')
            padre = nodos[camino]
        hoja = f'h_{regla["regla"].replace("-", "")}'
        lineas.append(f'  {hoja} [label="{regla["regla"]} · FC {regla["fc"]:.0f} %\\n{_texto(regla["conclusion"], 30)}", '
                      f'fillcolor="{COLORES[cat]}", color="{BORDES[cat]}", shape=note, style="filled"];')
        lineas.append(f'  {padre} -> {hoja} [label="Then", color="{BORDES[cat]}"];')
    lineas.append('}')
    return '\n'.join(lineas)


def general_dot(ramas):
    lineas = _encabezado('arbol_general')
    total = sum(len(r['reglas']) for r in ramas.values())
    lineas.append(f'  raiz [label="INCIDENTE TECNOLÓGICO\\nREPORTADO\\n({len(ramas)} ramas · {total} fallas)", '
                  'shape=box, style="rounded,filled,bold", fillcolor="#18212D", fontcolor="white", fontsize=12];')
    categorias = OrderedDict()
    for r in ramas.values():
        categorias.setdefault(r['categoria'], (r['categoria_nombre'], []))[1].append(r)
    for cat, (nombre, lista) in categorias.items():
        fallas = sum(len(r['reglas']) for r in lista)
        lineas.append(f'  c{cat} [label="{cat}. {_texto(nombre, 22)}\\n{fallas} fallas", style="rounded,filled,bold", '
                      f'fillcolor="{COLORES[cat]}", color="{BORDES[cat]}", fontsize=11];')
        lineas.append(f'  raiz -> c{cat};')
        for r in lista:
            n = f'r{r["codigo"]}'
            lineas.append(f'  {n} [label="{r["codigo"]} · {_texto(r["nombre"], 28)}\\n{r["procesos"]}", '
                          f'fillcolor="white", color="{BORDES[cat]}"];')
            lineas.append(f'  c{cat} -> {n} [label="If"];')
            hojas = '\\l'.join(_texto(f'{g["regla"]} {g["conclusion"].replace("la falla está en ", "")}', 46).replace('\\n', '\\l    ')
                               for g in r['reglas'].values()) + '\\l'
            lineas.append(f'  f{r["codigo"]} [label="{hojas}", shape=note, style="filled", fillcolor="{COLORES[cat]}", '
                          f'color="{BORDES[cat]}", fontsize=8];')
            lineas.append(f'  {n} -> f{r["codigo"]} [label="Then ({len(r["reglas"])})", color="{BORDES[cat]}"];')
    lineas.append('}')
    return '\n'.join(lineas)


def main():
    ramas = cargar()
    SALIDA.mkdir(exist_ok=True)
    (SALIDA / 'arbol_general.dot').write_text(general_dot(ramas), encoding='utf-8')
    for r in ramas.values():
        (SALIDA / f'rama_{r["codigo"]}.dot').write_text(rama_dot(r), encoding='utf-8')
    total = sum(len(r['reglas']) for r in ramas.values())
    print(f'{len(ramas)} ramas, {total} reglas (hojas) en {SALIDA}')
    for r in ramas.values():
        print(f'  {r["codigo"]:<3} {r["nombre"]:<42} {r["procesos"]:<14} {len(r["reglas"]):>2} reglas')


if __name__ == '__main__':
    main()
