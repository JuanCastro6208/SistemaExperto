"""Capa de lógica de negocio: motor de inferencia, explicación y servicios.

No contiene SQL ni elementos de interfaz; recibe los repositorios de la capa de datos.
"""
from .motor_inferencia import MotorInferencia
from .selector_preguntas import SelectorGananciaInformacion
from .servicios import ServicioConocimiento, ServicioDiagnostico, SesionDiagnostico

__all__ = ['MotorInferencia', 'SelectorGananciaInformacion', 'ServicioDiagnostico',
           'ServicioConocimiento', 'SesionDiagnostico']
