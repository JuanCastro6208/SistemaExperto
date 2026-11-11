"""Capa de acceso a datos: es la única que conoce SQL y el motor de base de datos."""
from .conexion import (ConexionBD, ConexionMySQL, ConexionSQLite, ErrorIntegridad, conexiones_temporales,
                       crear_conexiones)
from .dao import ConocimientoDAOSQL, FabricaDAO

__all__ = ['ConexionBD', 'ConexionSQLite', 'ConexionMySQL', 'ErrorIntegridad', 'crear_conexiones',
           'conexiones_temporales', 'FabricaDAO', 'ConocimientoDAOSQL']
