"""Objetos de transferencia de datos (DTO) de la base transaccional.

Los DAO devuelven estos objetos a la capa de negocio; así ninguna capa superior depende de los
nombres de las columnas ni del motor de base de datos. Cada DTO se arma con desde_fila().
"""
from dataclasses import asdict, dataclass, field, fields
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
class UsuarioDTO(_DTO):
    id: int
    rol_id: int
    documento: str
    nombre: str
    correo: str
    rol_codigo: str = ''
    rol_nombre: str = ''
    dependencia_id: Optional[int] = None
    dependencia: Optional[str] = None
    contrasena_hash: str = field(default='', repr=False)
    debe_cambiar_contrasena: int = 0
    activo: int = 1
    intentos_fallidos: int = 0
    bloqueado_hasta: Optional[str] = None
    ultimo_ingreso: Optional[str] = None
    creado_en: Optional[str] = None

    def como_dict(self):
        datos = asdict(self)
        datos.pop('contrasena_hash')        # el hash nunca sale de la capa de negocio
        return datos


@dataclass
class EquipoDTO(_DTO):
    id: int
    inventario: str
    tipo_equipo_id: int
    ubicacion: str
    tipo_nombre: str = ''
    dependencia_id: Optional[int] = None
    dependencia: Optional[str] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    activo: int = 1


@dataclass
class IncidenteDTO(_DTO):
    id: int
    codigo: str
    solicitante_id: int
    equipo_id: int
    ubicacion: str
    descripcion: str
    estado: str
    fecha_apertura: str
    administrador_id: Optional[int] = None
    categoria_codigo: Optional[str] = None
    fecha_cierre: Optional[str] = None
    solicitante: str = ''
    administrador: Optional[str] = None
    inventario: str = ''
    tipo_equipo: str = ''
    marca: Optional[str] = None
    modelo: Optional[str] = None
    rondas: int = 0
    proxima_cita: Optional[str] = None


@dataclass
class EventoHistorialDTO(_DTO):
    id: int
    incidente_id: int
    estado_nuevo: str
    cambiado_en: str
    estado_anterior: Optional[str] = None
    usuario_id: Optional[int] = None
    usuario: Optional[str] = None


@dataclass
class CitaDTO(_DTO):
    id: int
    incidente_id: int
    administrador_id: int
    inicio: str
    fin: str
    lugar: str
    estado: str
    creado_por: int
    administrador: str = ''
    incidente_codigo: str = ''
    creado_en: Optional[str] = None


@dataclass
class DiagnosticoDTO(_DTO):
    id: int
    ronda: int
    estado: str
    fecha_inicio: str
    incidente_id: Optional[int] = None
    registrado_por: Optional[int] = None
    total_preguntas: int = 0
    parametros: Optional[str] = None
    equipo_texto: Optional[str] = None
    ubicacion_texto: Optional[str] = None
    descripcion: Optional[str] = None
    fecha_fin: Optional[str] = None
    incidente_codigo: Optional[str] = None
    administrador: Optional[str] = None
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
    estado: str
    granulo_codigo: Optional[str] = None
    granulo_version: Optional[int] = None
    conclusion: Optional[str] = None
    accion: Optional[str] = None
    ronda: Optional[int] = None


@dataclass
class IntervencionDTO(_DTO):
    id: int
    diagnostico_hipotesis_id: int
    administrador_id: int
    accion_aplicada: str
    resultado: str
    registrado_en: str
    tiempo_min: Optional[int] = None
    observaciones: Optional[str] = None
    administrador: str = ''
    hipotesis_codigo: str = ''
    hipotesis_nombre: str = ''
    ronda: Optional[int] = None


@dataclass
class EscalamientoDTO(_DTO):
    id: int
    incidente_id: int
    motivo: str
    destino: str
    escalado_por: int
    escalado_en: str
    administrador: str = ''


@dataclass
class AuditoriaDTO(_DTO):
    id: int
    entidad: str
    accion: str
    fecha: str
    codigo: Optional[str] = None
    version: Optional[int] = None
    usuario_id: Optional[int] = None
    usuario: Optional[str] = None
    detalle: Optional[str] = None
