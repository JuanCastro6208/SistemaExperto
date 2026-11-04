"""SEDATI - Sistema Experto para el Diagnóstico y Asistencia Técnica de Incidentes.

Arquitectura en tres capas:
    sedati.datos         capa de acceso a datos (conexión y repositorios SQL)
    sedati.negocio       capa de lógica de negocio (motor de inferencia y servicios)
    sedati.presentacion  capa de presentación (interfaz gráfica con CustomTkinter)
"""

__version__ = '1.0.0'
