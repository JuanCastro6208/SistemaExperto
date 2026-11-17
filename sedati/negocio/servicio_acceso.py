"""Acceso de usuarios: crear cuenta, iniciar sesión y validar la sesión en cada petición.

Hay un solo tipo de cuenta (usuario): no hay roles ni administración de cuentas. Cada persona crea
la suya con su nombre, su correo y una contraseña, y los diagnósticos que guarda quedan a su nombre.
"""
import re
from dataclasses import dataclass
from datetime import timedelta

from . import seguridad
from .errores import Conflicto, ErrorNegocio, NoAutenticado

_CORREO = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_GENERICO = 'Correo o contraseña incorrectos.'


def _texto(fecha):
    return fecha.strftime('%Y-%m-%d %H:%M:%S')


@dataclass
class UsuarioActual:
    """Quién hace la petición (lo arma el servicio a partir del token)."""
    id: int
    nombre: str
    correo: str

    def como_dict(self):
        return {'id': self.id, 'nombre': self.nombre, 'correo': self.correo}


class ServicioAcceso:
    def __init__(self, dao_usuarios, firmador, reloj):
        self._usuarios = dao_usuarios
        self._firmador = firmador
        self._reloj = reloj

    @staticmethod
    def _actual(u):
        return UsuarioActual(u.id, u.nombre, u.correo)

    def _sesion(self, u):
        token, exp = self._firmador.emitir(u.id)
        return token, exp, self._actual(u)

    # ------------------------------------------------------------ crear cuenta
    def registrar(self, nombre, correo, contrasena):
        """Crea la cuenta y deja la sesión iniciada. Devuelve (token, vencimiento, UsuarioActual)."""
        nombre = ' '.join(str(nombre or '').split())
        correo = str(correo or '').strip().lower()
        contrasena = contrasena if isinstance(contrasena, str) else ''
        if len(nombre) < 2 or len(nombre) > 80:
            raise ErrorNegocio('Escriba su nombre (entre 2 y 80 caracteres).')
        if not _CORREO.match(correo) or len(correo) > 120:
            raise ErrorNegocio('El correo no tiene un formato válido.')
        motivo = seguridad.validar_politica(contrasena)
        if motivo:
            raise ErrorNegocio(motivo)
        if self._usuarios.por_correo(correo):
            raise Conflicto('Ya existe una cuenta con ese correo. Inicie sesión.')
        nuevo = self._usuarios.crear(nombre, correo, seguridad.hash_contrasena(contrasena), _texto(self._reloj()))
        return self._sesion(self._usuarios.por_id(nuevo))

    # ------------------------------------------------------------ iniciar sesión
    def ingresar(self, correo, contrasena):
        """Devuelve (token, vencimiento, UsuarioActual). El mensaje de error no revela qué falló.
        A los INTENTOS_MAXIMOS fallos seguidos la cuenta se bloquea MINUTOS_BLOQUEO minutos."""
        correo = str(correo or '').strip().lower()
        contrasena = contrasena if isinstance(contrasena, str) else ''
        if not correo or not contrasena:
            raise NoAutenticado('Escriba su correo y su contraseña.')
        ahora = self._reloj()
        u = self._usuarios.por_correo(correo)
        if u is None:
            seguridad.verificar_contrasena(contrasena, seguridad.hash_contrasena('x'))   # mismo tiempo de respuesta
            raise NoAutenticado(_GENERICO)
        if u.bloqueado_hasta and u.bloqueado_hasta > _texto(ahora):
            raise NoAutenticado('La cuenta está bloqueada por intentos fallidos. '
                                f'Intente de nuevo después de las {u.bloqueado_hasta[11:16]}.')
        if not seguridad.verificar_contrasena(contrasena, u.contrasena_hash):
            intentos = (u.intentos_fallidos or 0) + 1
            hasta = None
            if intentos >= seguridad.INTENTOS_MAXIMOS:
                hasta = _texto(ahora + timedelta(minutes=seguridad.MINUTOS_BLOQUEO))
                intentos = 0
            self._usuarios.registrar_fallo(u.id, intentos, hasta)
            if hasta:
                raise NoAutenticado(f'{seguridad.INTENTOS_MAXIMOS} intentos fallidos: la cuenta quedó bloqueada '
                                    f'durante {seguridad.MINUTOS_BLOQUEO} minutos.')
            raise NoAutenticado(_GENERICO)
        self._usuarios.registrar_ingreso(u.id, _texto(ahora))
        return self._sesion(u)

    # ------------------------------------------------------------ sesión en cada petición
    def autenticar(self, token):
        """UsuarioActual del token (auténtico, vigente y de una cuenta que existe) o NoAutenticado."""
        datos = self._firmador.leer(token) if token else None
        if not datos:
            raise NoAutenticado('Inicie sesión para continuar (la sesión no es válida o venció por inactividad).')
        u = self._usuarios.por_id(datos.get('uid'))
        if u is None:
            raise NoAutenticado('La cuenta ya no existe.')
        return self._actual(u)

    def renovar(self, usuario):
        return self._firmador.emitir(usuario.id)
