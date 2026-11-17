"""Errores de la capa de negocio. El servicio web los convierte en respuestas HTTP."""


class ErrorNegocio(Exception):
    """La operación no se puede hacer: datos inválidos o una regla del proceso lo impide (HTTP 400)."""
    estado = 400

    def __init__(self, mensaje, estado=None):
        super().__init__(mensaje)
        if estado:
            self.estado = estado


class NoAutenticado(ErrorNegocio):
    """Falta la sesión, venció o las credenciales no son correctas (HTTP 401)."""
    estado = 401


class NoEncontrado(ErrorNegocio):
    estado = 404


class Conflicto(ErrorNegocio):
    """El dato ya existe (p. ej. una cuenta con el mismo correo) (HTTP 409)."""
    estado = 409
