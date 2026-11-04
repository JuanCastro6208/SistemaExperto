"""Capa de acceso a datos: es la única que conoce SQL y el motor de base de datos."""
from .conexion import ConexionBD, ConexionMySQL, ConexionSQLite, crear_conexion
from .repositorio_conocimiento import RepositorioConocimiento
from .repositorio_consultas import RepositorioConsultas

__all__ = ['ConexionBD', 'ConexionSQLite', 'ConexionMySQL', 'crear_conexion',
           'RepositorioConocimiento', 'RepositorioConsultas']
