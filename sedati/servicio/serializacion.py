"""Convierte los objetos del motor de inferencia en diccionarios que se pueden enviar como JSON."""
from datetime import date, datetime
from decimal import Decimal


def _r(valor, decimales=4):
    return None if valor is None else round(float(valor), decimales)


def evidencia(e):
    return {'id': e.id, 'codigo': e.codigo, 'tipo': e.tipo, 'enunciado': e.enunciado, 'pregunta': e.pregunta}


def hipotesis(h):
    return {'id': h.id, 'codigo': h.codigo, 'nombre': h.nombre, 'dominio': h.dominio,
            'probabilidad_previa': _r(h.probabilidad_previa, 5)}


def granulo(g, evaluacion=None):
    """Una regla If / And / Then; si se da su evaluación, incluye el estado de cada condición y su aporte."""
    estados = {e.condicion.orden: e.valor for e in evaluacion.estados} if evaluacion else {}
    condiciones = []
    for c in g.condiciones:
        v = estados.get(c.orden)
        condiciones.append({
            'orden': c.orden, 'conector': c.conector, 'peso': _r(c.peso, 2),
            'evidencia': {'id': c.evidencia.id, 'codigo': c.evidencia.codigo, 'enunciado': c.evidencia.enunciado,
                          'tipo': c.evidencia.tipo},
            'valor': _r(v.valor, 2) if v else None,
            'deducido': bool(v and v.deducido),
            'deducido_de': v.origen.codigo if v and v.deducido else None,
        })
    datos = {
        'regla': g.regla, 'hipotesis_id': g.hipotesis_id, 'factor_certeza': _r(g.factor_certeza, 2),
        'conclusion': g.conclusion, 'accion': g.accion, 'riesgo_perdida_datos': g.riesgo_perdida_datos,
        'categoria_codigo': g.categoria_codigo, 'categoria_nombre': g.categoria_nombre,
        'rama_codigo': g.rama_codigo, 'rama_nombre': g.rama_nombre, 'version': g.version,
        'condiciones': condiciones,
    }
    if evaluacion:
        datos.update({'aplicabilidad': _r(evaluacion.aplicabilidad), 'grado': _r(evaluacion.grado),
                      'aporte': _r(evaluacion.certeza), 'cumplidas': evaluacion.cumplidas,
                      'negadas': evaluacion.negadas, 'total': evaluacion.total})
    return datos


def resultado(r):
    p = r.principal.granulo if r.principal else None
    return {
        'posicion': r.posicion,
        'hipotesis': hipotesis(r.hipotesis),
        'probabilidad': _r(r.probabilidad, 5),
        'certeza': _r(r.certeza),
        'previa_contextual': _r(r.previa_contextual, 5),
        'principal': {'regla': p.regla, 'conclusion': p.conclusion, 'accion': p.accion,
                      'riesgo_perdida_datos': p.riesgo_perdida_datos} if p else None,
        'reglas': [granulo(ev.granulo, ev) for ev in r.evaluaciones],
    }


def pregunta(q, por_que):
    if q is None:
        return None
    return {
        'evidencia': evidencia(q.evidencia), 'numero': q.numero, 'ganancia': _r(q.ganancia),
        'probabilidad_si': _r(q.probabilidad_si),
        'reglas': [g.regla for g in q.reglas],
        'lider_si': {'hipotesis': q.lider_si[0].nombre, 'probabilidad': _r(q.lider_si[1])} if q.lider_si else None,
        'lider_no': {'hipotesis': q.lider_no[0].nombre, 'probabilidad': _r(q.lider_no[1])} if q.lider_no else None,
        'por_que': por_que,
    }


def sesion(s):
    """Estado completo de una consulta: siguiente pregunta, top de hipótesis, evolución y traza."""
    m = s.motor
    top = s.resultado()
    etiquetas = {o.codigo: o.etiqueta for o in s.opciones}
    ids_top = [r.hipotesis.id for r in top]
    return {
        'consulta_id': s.consulta_id,
        'finalizada': s.finalizada,
        'datos': s.datos,
        'pregunta': pregunta(s.pregunta_actual, s.explicar_pregunta()),
        'motivo_conclusion': s.motivo_conclusion,
        'preguntas_respondidas': m.preguntas_respondidas,
        'maximo_preguntas': m.parametros.max_preguntas,
        'respuestas': [{'orden': r.orden, 'evidencia': evidencia(r.evidencia), 'escala': r.escala_codigo,
                        'etiqueta': etiquetas.get(r.escala_codigo, r.escala_codigo), 'valor': _r(r.valor, 2),
                        'origen': r.origen} for r in m.memoria.respuestas_en_orden()],
        'diferencial': len(m.memoria.hipotesis),
        'reglas_en_memoria': len(m.memoria.granulos),
        'top': [resultado(r) for r in top],
        'evolucion': [{'numero': p.numero, 'descripcion': p.descripcion,
                       'probabilidades': {str(h): _r(p.probabilidades.get(h, 0.0)) for h in ids_top}}
                      for p in m.pasos],
        'traza': [{'paso': paso, 'descripcion': desc, 'filas': filas} for paso, desc, filas in m.traza_consultas],
    }


def fila(f):
    """Fila de la base (dict) con fechas y decimales convertidos a tipos JSON."""
    salida = {}
    for k, v in f.items():
        if isinstance(v, (datetime, date)):
            v = v.isoformat(sep=' ') if isinstance(v, datetime) else v.isoformat()
        elif isinstance(v, Decimal):
            v = float(v)
        salida[k] = v
    return salida
