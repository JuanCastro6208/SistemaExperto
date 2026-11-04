"""Cálculo de certeza y de peso probabilístico.

1. Grado de cumplimiento de un gránulo (con signo), sobre sus condiciones And:
       grado(g) = Σ peso_i · v_i / Σ peso_i
   donde v_i ∈ [-1, 1] es el valor de la evidencia de la condición i según la respuesta del
   usuario (0 si no se conoce). El síntoma de entrada (la condición If) no entra aquí: decide
   si la regla aplica (punto 4), para no contar dos veces el mismo síntoma. Con todas las
   condiciones confirmadas «Sí, con certeza», el aporte es el factor de certeza del experto.

2. Aporte del gránulo a su hipótesis (la regla «dispara» en la medida en que aplica):
       FC(g) = a(g) · grado(g) · factor_certeza(g)          (a(g) se define en el punto 4)

3. Factor de certeza de la hipótesis. Sus gránulos son caminos alternativos para llegar a
   ella, así que los aportes positivos se refuerzan con la combinación de MYCIN
       a, b ≥ 0:   a + b(1 − a)
   y la hipótesis solo queda en contra cuando ningún camino la apoya (se toma el aporte
   menos negativo): negar una regla no descarta las otras reglas de la misma hipótesis.

4. Probabilidad previa contextual: cada regla recibe una parte de la previa de su hipótesis
   (π(g) = previa(h) / reglas(h)) y pesa según su síntoma de entrada (la condición If):
       previa_ctx(h) = Σ_g π(g) · a(g)
       a(g) = a0 + (1 − a0)·v   si v ≥ 0     (v = valor del síntoma de entrada)
       a(g) = a0 · (1 + v)      si v < 0
   Así una hipótesis no gana peso por reglas de otros síntomas que el usuario no reportó.

5. Peso probabilístico (modelo log-lineal sobre el diagnóstico diferencial):
       P(h) = previa_ctx(h) · e^(β·FC(h)) / Σ_j previa_ctx(j) · e^(β·FC(j))
"""
import math

APLICABILIDAD_MINIMA = 0.005


def combinar(a, b):
    """Combinación paralela de dos factores de certeza (MYCIN)."""
    if a >= 0 and b >= 0:
        return a + b * (1 - a)
    if a < 0 and b < 0:
        return a + b * (1 + a)
    denominador = 1 - min(abs(a), abs(b))
    return 0.0 if denominador == 0 else (a + b) / denominador


def combinar_todas(valores):
    total = 0.0
    for v in valores:
        total = combinar(total, v)
    return total


def certeza_hipotesis(aportes):
    """FC de una hipótesis a partir de los aportes de sus gránulos (caminos alternativos)."""
    aportes = list(aportes)
    if not aportes:
        return 0.0
    positivos = [a for a in aportes if a > 0]
    if positivos:
        return combinar_todas(positivos)
    return max(aportes)


def grado_cumplimiento(pesos_y_valores):
    """pesos_y_valores: iterable de (peso, valor o None)."""
    suma_pesos = 0.0
    suma = 0.0
    for peso, valor in pesos_y_valores:
        suma_pesos += peso
        suma += peso * (valor or 0.0)
    return 0.0 if suma_pesos == 0 else suma / suma_pesos


def aplicabilidad(valor_entrada, base):
    """Qué tanto aplica una regla según el valor (-1..1, None si se desconoce) de su síntoma de entrada."""
    v = valor_entrada or 0.0
    a = base + (1 - base) * v if v >= 0 else base * (1 + v)
    return max(a, APLICABILIDAD_MINIMA)


def distribucion(previas, certezas, beta):
    """previas, certezas: dict hipotesis_id -> valor. Devuelve dict hipotesis_id -> probabilidad."""
    if not previas:
        return {}
    logits = {h: math.log(previas[h]) + beta * certezas.get(h, 0.0) for h in previas}
    maximo = max(logits.values())
    pesos = {h: math.exp(v - maximo) for h, v in logits.items()}
    total = sum(pesos.values())
    return {h: p / total for h, p in pesos.items()}


def entropia(probabilidades):
    """Entropía de Shannon en bits."""
    return -sum(p * math.log2(p) for p in probabilidades if p > 0)
