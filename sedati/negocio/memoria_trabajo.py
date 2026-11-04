"""Memoria de trabajo del motor: hechos conocidos y conocimiento ya traído de la base."""
from .modelos import Evidencia, Granulo, Hipotesis, Respuesta, ValorEvidencia


class MemoriaTrabajo:
    def __init__(self):
        self.respuestas: dict[int, Respuesta] = {}       # evidencia_id -> respuesta del usuario
        self.granulos: dict[str, Granulo] = {}           # regla -> gránulo (solo los consultados)
        self.hipotesis: dict[int, Hipotesis] = {}        # hipótesis del diagnóstico diferencial
        self.evidencias: dict[int, Evidencia] = {}       # evidencias conocidas
        self.grupos: dict[str, list[Evidencia]] = {}     # variable -> evidencias que la describen
        self._orden = 0

    # ------------------------------------------------------------ hechos
    def registrar(self, evidencia, valor, escala_codigo, origen):
        """Guarda o actualiza la respuesta del usuario sobre una evidencia."""
        self.evidencias[evidencia.id] = evidencia
        previa = self.respuestas.get(evidencia.id)
        if previa:
            previa.valor, previa.escala_codigo = valor, escala_codigo
            return previa
        self._orden += 1
        r = Respuesta(evidencia, valor, escala_codigo, origen, self._orden)
        self.respuestas[evidencia.id] = r
        return r

    def respuestas_en_orden(self):
        return sorted(self.respuestas.values(), key=lambda r: r.orden)

    def valor(self, evidencia, supuesto=None):
        """Valor de una evidencia: respondido directamente o deducido de su variable.

        supuesto = (evidencia, valor) permite evaluar una respuesta hipotética sin registrarla
        (lo usa el selector de preguntas para estimar la ganancia de información).
        """
        if supuesto is not None:
            ev_s, v_s = supuesto
            if ev_s.id == evidencia.id:
                return ValorEvidencia(v_s, False, ev_s)
            if evidencia.variable and evidencia.variable == ev_s.variable:
                return ValorEvidencia(v_s * ev_s.polaridad * evidencia.polaridad, True, ev_s)
        r = self.respuestas.get(evidencia.id)
        if r:
            return ValorEvidencia(r.valor, False, r.evidencia)
        if evidencia.variable:
            # la respuesta más reciente sobre la misma observación
            relacionadas = [self.respuestas[e.id] for e in self.grupos.get(evidencia.variable, [])
                            if e.id in self.respuestas]
            if relacionadas:
                r = max(relacionadas, key=lambda x: x.orden)
                return ValorEvidencia(r.valor * r.evidencia.polaridad * evidencia.polaridad, True, r.evidencia)
        return None

    def ya_preguntada(self, evidencia):
        """True si la evidencia, o la observación que describe, ya fue respondida."""
        if evidencia.id in self.respuestas:
            return True
        if evidencia.variable:
            return any(e.id in self.respuestas for e in self.grupos.get(evidencia.variable, []))
        return False

    def representante(self, evidencia):
        """Evidencia con la que se pregunta por una observación: la redactada en positivo."""
        if not evidencia.variable:
            return evidencia
        miembros = self.grupos.get(evidencia.variable, [evidencia])
        positivas = sorted((e for e in miembros if e.polaridad > 0), key=lambda e: e.id)
        return positivas[0] if positivas else evidencia

    # ------------------------------------------------------------ conocimiento consultado
    def agregar_granulo(self, granulo):
        self.granulos[granulo.regla] = granulo
        for c in granulo.condiciones:
            self.evidencias[c.evidencia.id] = c.evidencia

    def agregar_grupo(self, evidencia):
        miembros = self.grupos.setdefault(evidencia.variable, [])
        if all(e.id != evidencia.id for e in miembros):
            miembros.append(evidencia)
        self.evidencias[evidencia.id] = evidencia

    def granulos_de(self, hipotesis_id):
        return [g for g in self.granulos.values() if g.hipotesis_id == hipotesis_id]

    def categorias(self):
        return sorted({g.categoria_codigo for g in self.granulos.values()})
