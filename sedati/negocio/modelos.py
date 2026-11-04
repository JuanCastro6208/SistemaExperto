"""Objetos del dominio con los que razona el motor de inferencia."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Hipotesis:
    id: int
    codigo: str
    nombre: str
    dominio: str
    probabilidad_previa: float
    reglas: int = 1       # reglas activas que concluyen esta hipótesis

    @property
    def previa_por_regla(self):
        """Parte de la probabilidad previa que corresponde a cada una de sus reglas."""
        return self.probabilidad_previa / max(self.reglas, 1)


@dataclass(frozen=True)
class Evidencia:
    id: int
    codigo: str
    tipo: str            # SINTOMA | PRUEBA
    enunciado: str
    pregunta: str
    variable: str | None  # observación de la que forma parte (None si es independiente)
    polaridad: int        # +1 la afirma, -1 la niega

    @property
    def es_sintoma(self):
        return self.tipo == 'SINTOMA'


@dataclass(frozen=True)
class Condicion:
    orden: int
    conector: str        # If | And
    peso: float
    evidencia: Evidencia


@dataclass
class Granulo:
    """Una regla If / And / Then del experto (todas sus filas de la tabla granulo)."""
    regla: str
    hipotesis_id: int
    factor_certeza: float        # 0..1
    conclusion: str
    accion: str
    riesgo_perdida_datos: bool
    categoria_codigo: str
    categoria_nombre: str
    rama_codigo: str
    rama_nombre: str
    procesos: str
    version: int
    condiciones: list = field(default_factory=list)

    def texto(self):
        partes = [f'{c.conector} {c.evidencia.enunciado}' for c in self.condiciones]
        return ' '.join(partes) + f' Then {self.conclusion}'

    def contiene(self, evidencia_id):
        return any(c.evidencia.id == evidencia_id for c in self.condiciones)


@dataclass(frozen=True)
class OpcionRespuesta:
    codigo: str
    etiqueta: str
    valor: float          # -1..1
    color: str


@dataclass
class Respuesta:
    evidencia: Evidencia
    valor: float
    escala_codigo: str
    origen: str           # SINTOMA_INICIAL | PREGUNTA
    orden: int


@dataclass(frozen=True)
class ValorEvidencia:
    """Valor de una evidencia en la memoria de trabajo: respondido o deducido de otra."""
    valor: float
    deducido: bool
    origen: Evidencia     # evidencia que respondió el usuario


@dataclass
class EstadoCondicion:
    condicion: Condicion
    valor: ValorEvidencia | None


@dataclass
class EvaluacionGranulo:
    granulo: Granulo
    grado: float          # grado de cumplimiento de las condiciones And, con signo, -1..1
    certeza: float        # aporte del gránulo a su hipótesis, -1..1
    estados: list         # EstadoCondicion por cada condición
    aplicabilidad: float = 1.0   # qué tanto aplica la regla según su síntoma de entrada (0..1)

    @property
    def valor_entrada(self):
        """Valor del síntoma de entrada de la regla (su condición If), o None si se desconoce."""
        v = self.estados[0].valor if self.estados else None
        return v.valor if v else None

    @property
    def cumplidas(self):
        return sum(1 for e in self.estados if e.valor and e.valor.valor > 0)

    @property
    def negadas(self):
        return sum(1 for e in self.estados if e.valor and e.valor.valor < 0)

    @property
    def total(self):
        return len(self.estados)


@dataclass
class ResultadoHipotesis:
    hipotesis: Hipotesis
    probabilidad: float
    certeza: float
    evaluaciones: list    # EvaluacionGranulo, de mayor a menor aporte
    posicion: int = 0
    previa_contextual: float = 0.0   # previa normalizada sobre el diferencial según los síntomas

    @property
    def principal(self):
        return self.evaluaciones[0] if self.evaluaciones else None


@dataclass
class Pregunta:
    evidencia: Evidencia
    numero: int
    ganancia: float               # bits de incertidumbre que se espera reducir
    probabilidad_si: float        # probabilidad predictiva de que la respuesta sea afirmativa
    reglas: list                  # reglas del diferencial que usan esta observación
    lider_si: tuple | None = None  # (hipótesis, probabilidad) si la respuesta fuera «Sí»
    lider_no: tuple | None = None  # (hipótesis, probabilidad) si la respuesta fuera «No»


@dataclass
class PasoInferencia:
    """Fotografía del razonamiento después de cada respuesta (para la gráfica de evolución)."""
    numero: int
    descripcion: str
    probabilidades: dict          # hipotesis_id -> probabilidad
