"""Convierte las filas que entrega la capa de datos en objetos del dominio."""
from .modelos import Condicion, Evidencia, Granulo, Hipotesis


def evidencia_desde(fila):
    """Acepta filas de la tabla evidencia (id, codigo) o de condiciones (evidencia_id, evidencia_codigo)."""
    de_condicion = 'evidencia_id' in fila
    return Evidencia(
        id=int(fila['evidencia_id'] if de_condicion else fila['id']),
        codigo=fila['evidencia_codigo'] if de_condicion else fila['codigo'],
        tipo=fila['tipo'],
        enunciado=fila['enunciado'],
        pregunta=fila['pregunta'],
        variable=fila.get('variable'),
        polaridad=int(fila.get('polaridad') or 1),
    )


def hipotesis_desde(fila):
    return Hipotesis(int(fila['id']), fila['codigo'], fila['nombre'], fila['dominio'],
                     float(fila['probabilidad_previa']), int(fila.get('reglas') or 1))


def granulos_desde(filas):
    """Agrupa las filas de granulo (una por condición) en reglas completas."""
    granulos = {}
    for f in filas:
        g = granulos.get(f['regla'])
        if g is None:
            g = Granulo(
                regla=f['regla'], hipotesis_id=int(f['hipotesis_id']),
                factor_certeza=float(f['factor_certeza']) / 100.0,
                conclusion=f['conclusion'], accion=f['accion'],
                riesgo_perdida_datos=bool(f['riesgo_perdida_datos']),
                categoria_codigo=f['categoria_codigo'], categoria_nombre=f['categoria_nombre'],
                rama_codigo=f['rama_codigo'], rama_nombre=f['rama_nombre'], procesos=f['procesos'],
                version=int(f['version']))
            granulos[f['regla']] = g
        g.condiciones.append(Condicion(int(f['orden']), f['conector'], float(f['peso']), evidencia_desde(f)))
    for g in granulos.values():
        g.condiciones.sort(key=lambda c: c.orden)
    return granulos
