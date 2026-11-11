"""Interfaces de los objetos de acceso a datos (patrón DAO).

La capa de negocio solo conoce estas interfaces. Las implementaciones (*DAOSQL) están en
sql_conocimiento.py y sql_transaccional.py, y las entrega la FabricaDAO según el motor de base de
datos configurado. Cambiar de motor no obliga a tocar la lógica de negocio.
"""
from abc import ABC, abstractmethod


# =====================================================================  base de conocimiento (sedati_kb)
class ConocimientoDAO(ABC):
    """Lectura granular de la base de conocimiento que hace el motor de inferencia."""

    @abstractmethod
    def suscribir(self, observador): ...

    @abstractmethod
    def desuscribir(self, observador): ...

    @abstractmethod
    def reglas_que_contienen(self, evidencia_ids): ...

    @abstractmethod
    def reglas_de_categorias(self, categorias): ...

    @abstractmethod
    def condiciones_de_reglas(self, reglas): ...

    @abstractmethod
    def hipotesis_por_ids(self, ids): ...

    @abstractmethod
    def evidencias_de_variables(self, variables): ...

    @abstractmethod
    def evidencias_por_ids(self, ids): ...

    @abstractmethod
    def evidencias_por_codigos(self, codigos): ...

    @abstractmethod
    def hipotesis_por_codigos(self, codigos): ...

    @abstractmethod
    def reglas_de_hipotesis_mas_probables(self, excluir, limite): ...

    @abstractmethod
    def categorias(self): ...

    @abstractmethod
    def sintomas_por_categoria(self, categoria): ...

    @abstractmethod
    def resumen_hipotesis(self, incluir_inactivas=False): ...

    @abstractmethod
    def condiciones_de_hipotesis(self, hipotesis_id, incluir_inactivos=False): ...

    @abstractmethod
    def listar_evidencias(self, incluir_inactivas=False): ...

    @abstractmethod
    def estadisticas(self): ...


class AdministracionConocimientoDAO(ABC):
    """Altas, cambios y desactivación del conocimiento (RF-03). Nada se elimina."""

    @abstractmethod
    def siguiente_codigo(self, entidad): ...

    @abstractmethod
    def hipotesis(self, hipotesis_id): ...

    @abstractmethod
    def crear_hipotesis(self, codigo, nombre, dominio, probabilidad_previa): ...

    @abstractmethod
    def cambiar_estado_hipotesis(self, hipotesis_id, activo): ...

    @abstractmethod
    def evidencia(self, evidencia_id): ...

    @abstractmethod
    def crear_evidencia(self, codigo, tipo, enunciado, pregunta, variable, polaridad): ...

    @abstractmethod
    def cambiar_estado_evidencia(self, evidencia_id, activo): ...

    @abstractmethod
    def filas_granulo(self, regla): ...

    @abstractmethod
    def crear_granulo(self, regla, hipotesis_id, condiciones, datos, ahora): ...

    @abstractmethod
    def modificar_granulo(self, regla, cambios, ahora): ...

    @abstractmethod
    def cambiar_estado_granulo(self, regla, activo, ahora): ...

    @abstractmethod
    def ramas(self): ...


# =====================================================================  base transaccional (sedati_trx)
class CatalogoDAO(ABC):
    """Roles, módulos, matriz de permisos, dependencias, tipos de equipo y escala de respuestas."""

    @abstractmethod
    def roles(self): ...

    @abstractmethod
    def permisos_de_rol(self, rol_codigo): ...

    @abstractmethod
    def matriz_permisos(self): ...

    @abstractmethod
    def dependencias(self): ...

    @abstractmethod
    def tipos_equipo(self): ...

    @abstractmethod
    def escala_respuestas(self): ...


class UsuarioDAO(ABC):
    @abstractmethod
    def por_id(self, usuario_id): ...

    @abstractmethod
    def por_correo(self, correo): ...

    @abstractmethod
    def listar(self, rol_codigo=None, solo_activos=False): ...

    @abstractmethod
    def existe(self, documento=None, correo=None, excepto_id=None): ...

    @abstractmethod
    def crear(self, rol_id, dependencia_id, documento, nombre, correo, contrasena_hash, creado_en): ...

    @abstractmethod
    def actualizar(self, usuario_id, rol_id, dependencia_id, nombre, correo): ...

    @abstractmethod
    def cambiar_estado(self, usuario_id, activo): ...

    @abstractmethod
    def cambiar_contrasena(self, usuario_id, contrasena_hash, debe_cambiar): ...

    @abstractmethod
    def registrar_fallo(self, usuario_id, intentos, bloqueado_hasta): ...

    @abstractmethod
    def registrar_ingreso(self, usuario_id, fecha): ...

    @abstractmethod
    def desbloquear(self, usuario_id): ...


class BitacoraAccesoDAO(ABC):
    @abstractmethod
    def registrar(self, usuario_id, correo, exitoso, motivo, ip, fecha): ...

    @abstractmethod
    def recientes(self, limite=50): ...


class EquipoDAO(ABC):
    @abstractmethod
    def por_inventario(self, inventario): ...

    @abstractmethod
    def por_id(self, equipo_id): ...

    @abstractmethod
    def crear(self, inventario, tipo_equipo_id, dependencia_id, marca, modelo, ubicacion): ...

    @abstractmethod
    def listar(self): ...


class IncidenteDAO(ABC):
    @abstractmethod
    def crear(self, solicitante_id, equipo_id, ubicacion, descripcion, fecha): ...

    @abstractmethod
    def por_id(self, incidente_id): ...

    @abstractmethod
    def listar(self, filtros): ...

    @abstractmethod
    def asignar(self, incidente_id, administrador_id, usuario_id, fecha): ...

    @abstractmethod
    def cambiar_estado(self, incidente_id, estado, usuario_id, fecha, categoria_codigo=None): ...

    @abstractmethod
    def historial(self, incidente_id): ...

    @abstractmethod
    def de_equipo(self, equipo_id): ...


class CitaDAO(ABC):
    @abstractmethod
    def crear(self, incidente_id, administrador_id, inicio, fin, lugar, creado_por, fecha): ...

    @abstractmethod
    def por_id(self, cita_id): ...

    @abstractmethod
    def de_incidente(self, incidente_id): ...

    @abstractmethod
    def listar(self, administrador_id=None, solicitante_id=None, desde=None): ...

    @abstractmethod
    def reprogramar(self, cita_id, inicio, fin, lugar): ...

    @abstractmethod
    def cambiar_estado(self, cita_id, estado): ...


class DiagnosticoDAO(ABC):
    """Cada ejecución del motor: diagnostico, incidente_evidencia y diagnostico_hipotesis."""

    @abstractmethod
    def crear(self, incidente_id, registrado_por, parametros, datos, fecha): ...

    @abstractmethod
    def guardar_respuesta(self, diagnostico_id, orden, evidencia_codigo, escala_codigo, valor, origen, fecha): ...

    @abstractmethod
    def finalizar(self, diagnostico_id, total_preguntas, propuestas, fecha): ...

    @abstractmethod
    def cancelar(self, diagnostico_id, fecha): ...

    @abstractmethod
    def por_id(self, diagnostico_id): ...

    @abstractmethod
    def respuestas(self, diagnostico_id): ...

    @abstractmethod
    def hipotesis(self, diagnostico_id): ...

    @abstractmethod
    def de_incidente(self, incidente_id): ...

    @abstractmethod
    def listar(self, limite=200): ...

    @abstractmethod
    def propuesta(self, diagnostico_hipotesis_id): ...

    @abstractmethod
    def decidir(self, diagnostico_hipotesis_id, estado): ...

    @abstractmethod
    def descartadas_de_incidente(self, incidente_id): ...


class IntervencionDAO(ABC):
    @abstractmethod
    def registrar(self, diagnostico_hipotesis_id, administrador_id, accion, resultado, tiempo_min,
                  observaciones, fecha): ...

    @abstractmethod
    def de_incidente(self, incidente_id): ...


class EscalamientoDAO(ABC):
    @abstractmethod
    def registrar(self, incidente_id, motivo, destino, escalado_por, fecha): ...

    @abstractmethod
    def de_incidente(self, incidente_id): ...


class AuditoriaDAO(ABC):
    @abstractmethod
    def registrar(self, entidad, codigo, version, accion, usuario_id, detalle, fecha): ...

    @abstractmethod
    def listar(self, codigo=None, limite=100): ...


class IndicadoresDAO(ABC):
    @abstractmethod
    def resumen(self, desde=None, hasta=None): ...
