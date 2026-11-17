"""Capa de lógica de negocio: motor de inferencia, explicación, acceso y servicios.

No contiene SQL ni elementos de interfaz; recibe los DAO de la capa de datos.
"""
from .errores import Conflicto, ErrorNegocio, NoAutenticado, NoEncontrado
from .motor_inferencia import MotorInferencia
from .selector_preguntas import SelectorGananciaInformacion
from .servicio_acceso import ServicioAcceso, UsuarioActual
from .servicios import ServicioConocimiento, ServicioDiagnostico, SesionDiagnostico

__all__ = ['MotorInferencia', 'SelectorGananciaInformacion', 'ServicioDiagnostico', 'ServicioConocimiento',
           'SesionDiagnostico', 'ServicioAcceso', 'UsuarioActual', 'ErrorNegocio', 'NoAutenticado',
           'NoEncontrado', 'Conflicto']
