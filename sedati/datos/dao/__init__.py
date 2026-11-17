"""Objetos de acceso a datos (patrón DAO): interfaces, implementaciones SQL y fábrica."""
from .fabrica import FabricaDAO
from .interfaces import CatalogoDAO, ConocimientoDAO, DiagnosticoDAO, UsuarioDAO
from .sql_conocimiento import ConocimientoDAOSQL
from .sql_transaccional import CatalogoDAOSQL, DiagnosticoDAOSQL, UsuarioDAOSQL

__all__ = ['FabricaDAO', 'ConocimientoDAO', 'CatalogoDAO', 'DiagnosticoDAO', 'UsuarioDAO', 'ConocimientoDAOSQL',
           'CatalogoDAOSQL', 'DiagnosticoDAOSQL', 'UsuarioDAOSQL']
