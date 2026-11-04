"""Módulo de explicación: responde «¿por qué pregunta esto?» y «¿cómo llegó a esta conclusión?»."""


def _signo(valor):
    if valor is None:
        return '?'
    if valor.valor > 0:
        return '✔'
    if valor.valor < 0:
        return '✖'
    return '·'


def describir_valor(valor):
    if valor is None:
        return 'sin dato'
    texto = f'{valor.valor:+.1f}'
    if valor.deducido:
        texto += f' (deducido de {valor.origen.codigo})'
    return texto


def por_que(motor, pregunta):
    """Líneas de texto que justifican la pregunta actual."""
    prob = motor.probabilidades()
    hip = motor.memoria.hipotesis
    lineas = [f'Observación {pregunta.evidencia.codigo} ({pregunta.evidencia.tipo.lower()}): '
              f'«{pregunta.evidencia.enunciado}».', '',
              f'Aparece en {len(pregunta.reglas)} gránulo(s) del diagnóstico diferencial:']
    for g in pregunta.reglas:
        h = hip[g.hipotesis_id]
        lineas.append(f'  • {g.regla} → {h.nombre} (peso actual {prob.get(h.id, 0):.0%}, FC {g.factor_certeza:.0%})')
    lineas += ['',
               f'Ganancia de información esperada: {pregunta.ganancia:.3f} bits '
               f'(probabilidad estimada de «Sí»: {pregunta.probabilidad_si:.0%}).']
    if pregunta.lider_si:
        lineas.append(f'Si responde «Sí», lideraría {pregunta.lider_si[0].nombre} con {pregunta.lider_si[1]:.0%}.')
    if pregunta.lider_no:
        lineas.append(f'Si responde «No», lideraría {pregunta.lider_no[0].nombre} con {pregunta.lider_no[1]:.0%}.')
    return lineas


def como(resultado, beta):
    """Líneas de texto con el razonamiento que lleva al peso de una hipótesis."""
    h = resultado.hipotesis
    lineas = [f'{h.codigo} · {h.nombre}',
              f'Probabilidad previa: {h.probabilidad_previa:.2%} global, {resultado.previa_contextual:.2%} según '
              f'los síntomas   ·   Factor de certeza combinado: {resultado.certeza:+.3f}   ·   '
              f'Peso probabilístico: {resultado.probabilidad:.2%}', '']
    for ev in resultado.evaluaciones:
        g = ev.granulo
        lineas.append(f'Regla {g.regla} (rama {g.rama_codigo}, FC del experto {g.factor_certeza:.0%}, v{g.version})')
        for est in ev.estados:
            c = est.condicion
            lineas.append(f'   {_signo(est.valor)} {c.conector:<3} {c.evidencia.enunciado}   [{describir_valor(est.valor)}]')
        lineas.append(f'   Then {g.conclusion}')
        lineas.append(f'   aplicabilidad (síntoma de entrada) = {ev.aplicabilidad:.2f}   ·   grado de cumplimiento de '
                      f'las condiciones And = {ev.grado:+.3f}')
        lineas.append(f'   aporte = {ev.aplicabilidad:.2f} × {ev.grado:+.3f} × {g.factor_certeza:.2f} = {ev.certeza:+.3f}')
        lineas.append('')
    lineas.append(f'Los aportes positivos de sus reglas se combinan con la regla de MYCIN (si ninguna la apoya se toma '
                  f'el aporte menos negativo) y el peso se obtiene con '
                  f'P(h) ∝ previa_contextual(h) · e^({beta:g} · FC(h)), normalizado sobre el diagnóstico diferencial.')
    return lineas
