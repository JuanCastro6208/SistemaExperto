"""Objetos de acceso a datos (patrón DAO): interfaces, implementaciones SQL y fábrica."""
from .fabrica import FabricaDAO
from .interfaces import CatalogoDAO, ConocimientoDAO, DiagnosticoDAO
from .sql_conocimiento import ConocimientoDAOSQL
from .sql_transaccional import CatalogoDAOSQL, DiagnosticoDAOSQL

__all__ = ['FabricaDAO', 'ConocimientoDAO', 'CatalogoDAO', 'DiagnosticoDAO', 'ConocimientoDAOSQL',
           'CatalogoDAOSQL', 'DiagnosticoDAOSQL']
