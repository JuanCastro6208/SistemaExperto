"""Errores de la capa de negocio. El servicio web los convierte en respuestas HTTP."""


class ErrorNegocio(Exception):
    """La operación no se puede hacer: datos inválidos o una regla del proceso lo impide (HTTP 400)."""
    estado = 400

    def __init__(self, mensaje, estado=None):
        super().__init__(mensaje)
        if estado:
            self.estado = estado


class NoEncontrado(ErrorNegocio):
    estado = 404


class NoAutenticado(ErrorNegocio):
    estado = 401


class SinPermiso(ErrorNegocio):
    estado = 403


class Conflicto(ErrorNegocio):
    """Choca con el estado actual de los datos (cita solapada, incidente cerrado, duplicado)."""
    estado = 409
