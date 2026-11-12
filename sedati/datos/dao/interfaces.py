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
    def ramas(self): ...

    @abstractmethod
    def resumen_hipotesis(self, incluir_inactivas=False): ...

    @abstractmethod
    def condiciones_de_hipotesis(self, hipotesis_id, incluir_inactivos=False): ...

    @abstractmethod
    def listar_evidencias(self, incluir_inactivas=False): ...

    @abstractmethod
    def estadisticas(self): ...


# =====================================================================  base transaccional (sedati_trx)
class CatalogoDAO(ABC):
    """Escala de respuestas graduadas."""

    @abstractmethod
    def escala_respuestas(self): ...


class DiagnosticoDAO(ABC):
    """Cada ejecución del motor: diagnostico, incidente_evidencia y diagnostico_hipotesis."""

    @abstractmethod
    def crear(self, nombre_usuario, categoria_codigo, parametros, datos, fecha): ...

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
    def listar(self, limite=200, nombre_usuario=None): ...
