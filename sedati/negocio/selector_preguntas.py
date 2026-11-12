"""Estrategia para elegir la siguiente pregunta: máxima ganancia de información.

Para cada observación que aparece en los gránulos del diferencial y todavía no se conoce,
el selector simula las dos respuestas extremas y calcula cuánto bajaría la entropía de la
distribución de probabilidad de las hipótesis:

    ganancia(q) = H(P) − [ P(sí|q) · H(P | q = sí) + P(no|q) · H(P | q = no) ]

P(sí|q) se estima con la base de conocimiento: cada hipótesis cuyos gránulos piden q aporta
0,5 + 0,5 · factor_certeza (o 0,5 − 0,5 · factor si la piden negada); el resto aporta 0,5.
Se pregunta por la observación con mayor ganancia: la que mejor separa las hipótesis.
"""
from . import certeza
from .modelos import Pregunta


def _relacion(pregunta, evidencia):
    """+1 si describen la misma observación en el mismo sentido, -1 si en sentido opuesto, 0 si no."""
    if pregunta.id == evidencia.id:
        return 1
    if pregunta.variable and pregunta.variable == evidencia.variable:
        return pregunta.polaridad * evidencia.polaridad
    return 0


class SelectorGananciaInformacion:
    def candidatas(self, motor):
        """Observaciones pendientes del diferencial, una por variable, redactadas en positivo.

        Se sigue el orden de cada regla: mientras su síntoma de entrada (If) no se conozca solo se
        pregunta por él; sus condiciones And se preguntan cuando el síntoma está confirmado (o el
        usuario no lo sabe). Si el síntoma fue negado, la regla no genera preguntas.
        """
        m = motor.memoria
        candidatas = {}
        for g in m.granulos.values():
            if g.hipotesis_id in motor.descartadas:      # hipótesis excluida del diagnóstico
                continue
            entrada = g.condiciones[0].evidencia
            if not m.ya_preguntada(entrada):
                pendientes = [entrada]
            elif m.valor(entrada).valor >= 0:
                pendientes = [c.evidencia for c in g.condiciones[1:]]
            else:
                pendientes = []
            for e in pendientes:
                if not m.ya_preguntada(e):
                    candidatas.setdefault(e.variable or e.id, m.representante(e))
        return list(candidatas.values())

    def probabilidad_si(self, motor, evidencia, distribucion):
        total = 0.0
        for hid, p in distribucion.items():
            apoyo = None
            for g in motor.memoria.granulos_de(hid):
                for c in g.condiciones:
                    s = _relacion(evidencia, c.evidencia)
                    if s and (apoyo is None or g.factor_certeza > abs(apoyo)):
                        apoyo = s * g.factor_certeza
            total += p * (0.5 if apoyo is None else 0.5 + 0.5 * apoyo)
        return min(max(total, 0.02), 0.98)

    def elegir(self, motor):
        base = motor.probabilidades()
        h_actual = certeza.entropia(base.values())
        mejor, mejor_clave = None, None
        for q in self.candidatas(motor):
            p_si = self.probabilidad_si(motor, q, base)
            dist_si = motor.probabilidades((q, 1.0))
            dist_no = motor.probabilidades((q, -1.0))
            esperada = p_si * certeza.entropia(dist_si.values()) + (1 - p_si) * certeza.entropia(dist_no.values())
            ganancia = h_actual - esperada
            reglas = [g for g in motor.memoria.granulos.values() if g.hipotesis_id not in motor.descartadas
                      and any(_relacion(q, c.evidencia) for c in g.condiciones)]
            relevancia = sum(base.get(g.hipotesis_id, 0) for g in reglas)
            # desempate: más relevancia para las hipótesis probables; luego síntomas antes que pruebas
            clave = (round(ganancia, 6), round(relevancia, 6), q.es_sintoma, -q.id)
            if mejor_clave is None or clave > mejor_clave:
                mejor_clave = clave
                mejor = (q, ganancia, p_si, reglas, dist_si, dist_no)
        if mejor is None:
            return None
        q, ganancia, p_si, reglas, dist_si, dist_no = mejor
        hip = motor.memoria.hipotesis
        lider_si = max(dist_si.items(), key=lambda x: x[1])
        lider_no = max(dist_no.items(), key=lambda x: x[1])
        return Pregunta(evidencia=q, numero=motor.preguntas_respondidas + 1, ganancia=max(ganancia, 0.0),
                        probabilidad_si=p_si, reglas=sorted(reglas, key=lambda g: g.regla),
                        lider_si=(hip[lider_si[0]], lider_si[1]), lider_no=(hip[lider_no[0]], lider_no[1]))
