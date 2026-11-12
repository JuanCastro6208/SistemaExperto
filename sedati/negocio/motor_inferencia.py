"""Motor de inferencia de SEDATI.

No contiene reglas del dominio ni árboles de condicionales: todo el conocimiento está en la
base (tabla granulo). El motor trabaja con encadenamiento hacia adelante sobre una memoria de
trabajo que se llena con consultas sucesivas y granulares:

    1. Con los síntomas iniciales consulta los gránulos que los contienen.
    2. Con las categorías de esos gránulos consulta el resto de su categoría: es el
       diagnóstico diferencial (las hipótesis que compiten).
    3. Trae solo las condiciones de las reglas nuevas y las evidencias equivalentes u opuestas.
    4. Cada respuesta afirmativa vuelve a consultar los gránulos que contienen esa evidencia,
       lo que puede activar reglas de otras categorías.

Después de cada respuesta evalúa los gránulos (grado de cumplimiento × factor de certeza),
combina los aportes por hipótesis (MYCIN) y calcula el peso probabilístico de cada una.
"""
from contextlib import contextmanager

from . import certeza
from .fabrica import evidencia_desde, granulos_desde, hipotesis_desde
from .memoria_trabajo import MemoriaTrabajo
from .modelos import EstadoCondicion, EvaluacionGranulo, PasoInferencia, ResultadoHipotesis
from .selector_preguntas import SelectorGananciaInformacion


class MotorInferencia:
    def __init__(self, repositorio, parametros, selector=None):
        self._repo = repositorio
        self.parametros = parametros
        self.selector = selector or SelectorGananciaInformacion()
        self.memoria = MemoriaTrabajo()
        self.traza_consultas = []      # (paso, descripción, filas devueltas)
        self.pasos = []                # PasoInferencia, para la evolución de las probabilidades
        self.preguntas_respondidas = 0
        self._paso = 0
        self.descartadas = set()       # id de hipótesis que no se deben proponer

    # ================================================================ consultas a la base
    def _anotar_consulta(self, descripcion, filas):
        self.traza_consultas.append((self._paso, descripcion, filas))

    @contextmanager
    def _trazando(self):
        self._repo.suscribir(self._anotar_consulta)
        try:
            yield
        finally:
            self._repo.desuscribir(self._anotar_consulta)

    def _cargar_grupos(self, evidencias):
        variables = sorted({e.variable for e in evidencias
                            if e.variable and e.variable not in self.memoria.grupos})
        for e in evidencias:
            if e.variable and e.variable in self.memoria.grupos:
                self.memoria.agregar_grupo(e)
        if variables:
            for fila in self._repo.evidencias_de_variables(variables):
                self.memoria.agregar_grupo(evidencia_desde(fila))

    def _cargar_reglas(self, reglas):
        nuevas = [r for r in dict.fromkeys(reglas) if r not in self.memoria.granulos]
        if not nuevas:
            return
        granulos = granulos_desde(self._repo.condiciones_de_reglas(nuevas))
        for g in granulos.values():
            self.memoria.agregar_granulo(g)
        hip_nuevas = sorted({g.hipotesis_id for g in granulos.values()} - set(self.memoria.hipotesis))
        for fila in self._repo.hipotesis_por_ids(hip_nuevas):
            h = hipotesis_desde(fila)
            self.memoria.hipotesis[h.id] = h
        self._cargar_grupos([c.evidencia for g in granulos.values() for c in g.condiciones])

    def _evidencias_que_apoya(self, evidencia, valor):
        """La evidencia y las de su misma observación que quedan con valor positivo."""
        if not evidencia.variable:
            return [evidencia.id]
        return [e.id for e in self.memoria.grupos.get(evidencia.variable, [evidencia])
                if valor * evidencia.polaridad * e.polaridad > 0]

    def _vigentes(self):
        return [h for h in self.memoria.hipotesis if h not in self.descartadas]

    def _asegurar_minimo(self):
        faltan = self.parametros.hipotesis_resultado - len(self._vigentes())
        if faltan > 0:
            excluir = set(self.memoria.hipotesis) | self.descartadas
            self._cargar_reglas(self._repo.reglas_de_hipotesis_mas_probables(excluir, faltan))

    # ================================================================ ciclo de inferencia
    def iniciar(self, sintoma_ids, descartadas=()):
        """Registra los síntomas iniciales y arma el diagnóstico diferencial.

        descartadas: id de hipótesis que no se deben proponer (por ejemplo, causas ya descartadas).
        """
        self.descartadas = set(descartadas)
        self.memoria = MemoriaTrabajo()
        self.traza_consultas, self.pasos = [], []
        self.preguntas_respondidas, self._paso = 0, 0
        with self._trazando():
            evidencias = [evidencia_desde(f) for f in self._repo.evidencias_por_ids(sintoma_ids)]
            self._cargar_grupos(evidencias)
            for e in evidencias:
                self.memoria.registrar(e, 1.0, 'SI', 'SINTOMA_INICIAL')
            apoyadas = [i for e in evidencias for i in self._evidencias_que_apoya(e, 1.0)]
            self._cargar_reglas(self._repo.reglas_que_contienen(apoyadas))
            self._cargar_reglas(self._repo.reglas_de_categorias(self.memoria.categorias()))
            self._asegurar_minimo()
        self._fotografiar('Síntomas iniciales')

    def responder(self, evidencia, opcion, origen='PREGUNTA'):
        """Registra una respuesta (nueva o corregida) y encadena hacia adelante."""
        nueva = evidencia.id not in self.memoria.respuestas
        self._paso += 1
        with self._trazando():
            self._cargar_grupos([evidencia])
            self.memoria.registrar(evidencia, opcion.valor, opcion.codigo, origen)
            if opcion.valor > 0:
                self._cargar_reglas(self._repo.reglas_que_contienen(
                    self._evidencias_que_apoya(evidencia, opcion.valor)))
            self._asegurar_minimo()
        if nueva and origen == 'PREGUNTA':
            self.preguntas_respondidas += 1
        accion = '' if nueva else ' (corregida)'
        self._fotografiar(f'{evidencia.codigo} → {opcion.etiqueta}{accion}')

    # ================================================================ evaluación
    def evaluar_granulo(self, granulo, supuesto=None):
        estados = [EstadoCondicion(c, self.memoria.valor(c.evidencia, supuesto)) for c in granulo.condiciones]
        # El síntoma de entrada (If) decide qué tanto aplica la regla; las condiciones And la confirman.
        if len(estados) > 1:
            discriminantes = estados[1:]
            entrada = estados[0].valor.valor if estados[0].valor else None
            aplica = certeza.aplicabilidad(entrada, self.parametros.aplicabilidad_base)
        else:
            discriminantes, aplica = estados, 1.0
        grado = certeza.grado_cumplimiento(
            (e.condicion.peso, e.valor.valor if e.valor else None) for e in discriminantes)
        return EvaluacionGranulo(granulo, grado, aplica * grado * granulo.factor_certeza, estados, aplica)

    def _calcular(self, supuesto=None):
        """Evalúa todos los gránulos en memoria y devuelve (aportes, FC, previas contextuales, P)."""
        aportes = {h: [] for h in self._vigentes()}
        for g in self.memoria.granulos.values():
            if g.hipotesis_id in aportes:
                aportes[g.hipotesis_id].append(self.evaluar_granulo(g, supuesto))
        cf = {h: certeza.certeza_hipotesis(e.certeza for e in evs) for h, evs in aportes.items()}
        previas = {}
        for h, evs in aportes.items():
            hip = self.memoria.hipotesis[h]
            previas[h] = sum(hip.previa_por_regla * e.aplicabilidad for e in evs) \
                or hip.previa_por_regla * certeza.APLICABILIDAD_MINIMA
        prob = certeza.distribucion(previas, cf, self.parametros.beta)
        return aportes, cf, previas, prob

    def probabilidades(self, supuesto=None):
        """Peso probabilístico de cada hipótesis del diferencial (dict hipotesis_id -> P)."""
        return self._calcular(supuesto)[3]

    def evaluar(self):
        """Todas las hipótesis del diferencial, de la más a la menos probable."""
        aportes, cf, previas, prob = self._calcular()
        resultados = [ResultadoHipotesis(self.memoria.hipotesis[h], prob[h], cf[h],
                                         sorted(aportes[h], key=lambda e: e.certeza, reverse=True),
                                         previa_contextual=previas[h] / sum(previas.values()))
                      for h in aportes]
        resultados.sort(key=lambda r: (r.probabilidad, r.certeza), reverse=True)
        for i, r in enumerate(resultados, 1):
            r.posicion = i
        return resultados

    def resultado(self, n=None):
        """Las n hipótesis más probables (por defecto las que indica la configuración)."""
        return self.evaluar()[:n or self.parametros.hipotesis_resultado]

    # ================================================================ control
    def siguiente_pregunta(self):
        return self.selector.elegir(self)

    def motivo_para_concluir(self, pregunta):
        """Texto con el motivo por el que conviene concluir, o None si vale la pena seguir."""
        p = self.parametros
        lider = self.resultado(1)[0]
        if lider.probabilidad >= p.umbral_probabilidad:
            return (f'La hipótesis «{lider.hipotesis.nombre}» alcanzó un peso de '
                    f'{lider.probabilidad:.0%} (umbral {p.umbral_probabilidad:.0%}).')
        if pregunta is None:
            return 'No quedan observaciones por verificar en el diagnóstico diferencial.'
        if pregunta.ganancia < p.ganancia_minima:
            return ('Ninguna pregunta adicional reduce la incertidumbre de forma apreciable '
                    f'(ganancia máxima {pregunta.ganancia:.3f} bits).')
        if self.preguntas_respondidas >= p.max_preguntas:
            return f'Se alcanzó el máximo de {p.max_preguntas} preguntas.'
        return None

    def _fotografiar(self, descripcion):
        self.pasos.append(PasoInferencia(len(self.pasos), descripcion, self.probabilidades()))
