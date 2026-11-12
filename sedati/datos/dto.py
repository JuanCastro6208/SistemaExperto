"""Objetos de transferencia de datos (DTO) de la base transaccional.

Los DAO devuelven estos objetos a la capa de negocio; así ninguna capa superior depende de los
nombres de las columnas ni del motor de base de datos. Cada DTO se arma con desde_fila().
"""
from dataclasses import asdict, dataclass, fields
from typing import Optional


class _DTO:
    @classmethod
    def desde_fila(cls, fila):
        if fila is None:
            return None
        nombres = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in fila.items() if k in nombres})

    def como_dict(self):
        return asdict(self)


@dataclass
class DiagnosticoDTO(_DTO):
    id: int
    nombre_usuario: str
    estado: str
    fecha_inicio: str
    categoria_codigo: Optional[str] = None
    total_preguntas: int = 0
    parametros: Optional[str] = None
    equipo_texto: Optional[str] = None
    ubicacion_texto: Optional[str] = None
    descripcion: Optional[str] = None
    fecha_fin: Optional[str] = None
    hipotesis_codigo: Optional[str] = None
    hipotesis_nombre: Optional[str] = None
    probabilidad: Optional[float] = None


@dataclass
class RespuestaDTO(_DTO):
    orden: int
    evidencia_codigo: str
    escala_codigo: str
    valor: float
    origen: str


@dataclass
class HipotesisPropuestaDTO(_DTO):
    id: int
    diagnostico_id: int
    posicion: int
    hipotesis_codigo: str
    hipotesis_nombre: str
    probabilidad: float
    certeza: float
    granulo_codigo: Optional[str] = None
    granulo_version: Optional[int] = None
    conclusion: Optional[str] = None
    accion: Optional[str] = None
