"""Capa de servicio: publica el sistema experto como API REST (AWS Lambda o servidor local).

Usa solo la capa de negocio; no conoce SQL ni la interfaz.
"""
from .api import ApiSEDATI, ErrorPeticion

__all__ = ['ApiSEDATI', 'ErrorPeticion']
