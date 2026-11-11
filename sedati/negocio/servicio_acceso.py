"""RF-01. Gestión de usuarios, roles y acceso."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import seguridad
from .errores import Conflicto, ErrorNegocio, NoAutenticado, NoEncontrado, SinPermiso

_CORREO = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
ROLES = ('ADMINISTRADOR', 'SOLICITANTE')


def _texto(fecha):
    return fecha.strftime('%Y-%m-%d %H:%M:%S')


@dataclass
class UsuarioActual:
    """Quién hace la petición y qué puede hacer (lo arma el servicio a partir del token)."""
    id: int
    nombre: str
    correo: str
    rol: str
    permisos: dict = field(default_factory=dict)
    debe_cambiar_contrasena: bool = False

    @property
    def es_administrador(self):
        return self.rol == 'ADMINISTRADOR'

    def puede(self, modulo, accion='consultar'):
        return bool(self.permisos.get(modulo, {}).get(accion))

    def exigir(self, modulo, accion='consultar'):
        """Validación en el servidor: ocultar una opción del menú no es la única barrera (RF-01)."""
        if not self.puede(modulo, accion):
            raise SinPermiso('Su rol no tiene permiso para esta operación.')

    def como_dict(self):
        return {'id': self.id, 'nombre': self.nombre, 'correo': self.correo, 'rol': self.rol,
                'permisos': self.permisos, 'debe_cambiar_contrasena': self.debe_cambiar_contrasena}


class ServicioAcceso:
    def __init__(self, dao_usuarios, dao_bitacora, dao_catalogo, firmador, reloj):
        self._usuarios = dao_usuarios
        self._bitacora = dao_bitacora
        self._catalogo = dao_catalogo
        self._firmador = firmador
        self._reloj = reloj
        self._permisos = {}

    def _permisos_de(self, rol):
        if rol not in self._permisos:
            self._permisos[rol] = self._catalogo.permisos_de_rol(rol)
        return self._permisos[rol]

    def _actual(self, u):
        return UsuarioActual(u.id, u.nombre, u.correo, u.rol_codigo, self._permisos_de(u.rol_codigo),
                             bool(u.debe_cambiar_contrasena))

    # ------------------------------------------------------------ ingreso
    def ingresar(self, correo, contrasena, ip=None):
        """Devuelve (token, vencimiento, UsuarioActual). El mensaje de error nunca revela qué falló."""
        correo = (correo or '').strip()
        ahora = self._reloj()
        generico = 'Usuario o contraseña incorrectos, o la cuenta no está disponible.'
        if not correo or not contrasena:
            raise NoAutenticado('Escriba su correo y su contraseña.')
        u = self._usuarios.por_correo(correo)
        if u is None:
            seguridad.verificar_contrasena(contrasena, seguridad.hash_contrasena('x'))   # mismo tiempo de respuesta
            self._bitacora.registrar(None, correo, False, 'CREDENCIALES', ip, _texto(ahora))
            raise NoAutenticado(generico)
        if not u.activo:
            self._bitacora.registrar(u.id, correo, False, 'INACTIVA', ip, _texto(ahora))
            raise NoAutenticado(generico)
        if u.bloqueado_hasta and u.bloqueado_hasta > _texto(ahora):
            self._bitacora.registrar(u.id, correo, False, 'BLOQUEADA', ip, _texto(ahora))
            raise NoAutenticado('La cuenta está bloqueada temporalmente por intentos fallidos. '
                                f'Intente después de las {u.bloqueado_hasta[11:16]} o pida al administrador que la desbloquee.')
        if not seguridad.verificar_contrasena(contrasena, u.contrasena_hash):
            intentos = (u.intentos_fallidos or 0) + 1
            hasta = None
            if intentos >= seguridad.INTENTOS_MAXIMOS:
                hasta = _texto(ahora + timedelta(minutes=seguridad.MINUTOS_BLOQUEO))
                intentos = 0
            self._usuarios.registrar_fallo(u.id, intentos, hasta)
            self._bitacora.registrar(u.id, correo, False, 'CREDENCIALES', ip, _texto(ahora))
            if hasta:
                raise NoAutenticado('Cinco intentos fallidos: la cuenta quedó bloqueada durante quince minutos.')
            raise NoAutenticado(generico)
        self._usuarios.registrar_ingreso(u.id, _texto(ahora))
        self._bitacora.registrar(u.id, correo, True, 'OK', ip, _texto(ahora))
        token, exp = self._firmador.emitir(u.id, u.rol_codigo)
        return token, exp, self._actual(u)

    def autenticar(self, token):
        """UsuarioActual del token (vigente y de una cuenta activa) o NoAutenticado."""
        datos = self._firmador.leer(token) if token else None
        if not datos:
            raise NoAutenticado('La sesión no es válida o venció por inactividad. Ingrese de nuevo.')
        u = self._usuarios.por_id(datos['uid'])
        if u is None or not u.activo:
            raise NoAutenticado('La cuenta ya no está activa.')
        return self._actual(u)

    def renovar(self, usuario):
        return self._firmador.emitir(usuario.id, usuario.rol)

    def cambiar_contrasena(self, usuario, actual, nueva):
        u = self._usuarios.por_id(usuario.id)
        if not seguridad.verificar_contrasena(actual or '', u.contrasena_hash):
            raise ErrorNegocio('La contraseña actual no es correcta.')
        motivo = seguridad.validar_politica(nueva or '')
        if motivo:
            raise ErrorNegocio(motivo)
        if actual == nueva:
            raise ErrorNegocio('La nueva contraseña debe ser distinta de la actual.')
        self._usuarios.cambiar_contrasena(u.id, seguridad.hash_contrasena(nueva), False)

    def bitacora(self, usuario, limite=50):
        usuario.exigir('USUARIOS')
        return self._bitacora.recientes(limite)


class ServicioUsuarios:
    """Administración de cuentas: crear, consultar, modificar, desactivar y desbloquear. Nadie se elimina."""

    def __init__(self, dao_usuarios, dao_catalogo, reloj):
        self._usuarios = dao_usuarios
        self._catalogo = dao_catalogo
        self._reloj = reloj

    def _rol_id(self, codigo):
        for r in self._catalogo.roles():
            if r['codigo'] == codigo:
                return r['id']
        raise ErrorNegocio('El rol debe ser ADMINISTRADOR o SOLICITANTE.')

    def _validar(self, datos, excepto_id=None):
        documento = (datos.get('documento') or '').strip()
        nombre = (datos.get('nombre') or '').strip()
        correo = (datos.get('correo') or '').strip().lower()
        if not nombre or len(nombre) > 120:
            raise ErrorNegocio('Escriba el nombre completo (máximo 120 caracteres).')
        if not _CORREO.match(correo) or len(correo) > 120:
            raise ErrorNegocio('El correo no tiene un formato válido.')
        if excepto_id is None and (not documento or not re.fullmatch(r'[A-Za-z0-9-]{4,20}', documento)):
            raise ErrorNegocio('El documento debe tener entre 4 y 20 letras o números.')
        if self._usuarios.existe(documento if excepto_id is None else None, correo, excepto_id):
            raise Conflicto('Ya existe una cuenta con ese documento o ese correo.')
        dependencia = datos.get('dependencia_id') or None
        return documento, nombre, correo, (int(dependencia) if dependencia else None), self._rol_id(datos.get('rol'))

    def listar(self, usuario):
        usuario.exigir('USUARIOS')
        return self._usuarios.listar()

    def administradores(self):
        return self._usuarios.listar('ADMINISTRADOR', solo_activos=True)

    def crear(self, usuario, datos):
        """Devuelve (cuenta creada, contraseña temporal). La contraseña solo se muestra esta vez."""
        usuario.exigir('USUARIOS', 'crear')
        documento, nombre, correo, dependencia, rol_id = self._validar(datos)
        temporal = seguridad.contrasena_temporal()
        nuevo = self._usuarios.crear(rol_id, dependencia, documento, nombre, correo,
                                     seguridad.hash_contrasena(temporal), _texto(self._reloj()))
        return self._usuarios.por_id(nuevo), temporal

    def _cuenta(self, usuario_id):
        u = self._usuarios.por_id(usuario_id)
        if u is None:
            raise NoEncontrado(f'No existe la cuenta {usuario_id}.')
        return u

    def modificar(self, usuario, usuario_id, datos):
        """El cambio de rol rige desde la siguiente petición del usuario (los permisos se leen en cada una)."""
        usuario.exigir('USUARIOS', 'modificar')
        self._cuenta(usuario_id)
        _, nombre, correo, dependencia, rol_id = self._validar(datos, excepto_id=usuario_id)
        if usuario_id == usuario.id and datos.get('rol') != usuario.rol:
            raise ErrorNegocio('No puede cambiar su propio rol.')
        self._usuarios.actualizar(usuario_id, rol_id, dependencia, nombre, correo)
        return self._usuarios.por_id(usuario_id)

    def cambiar_estado(self, usuario, usuario_id, activo):
        usuario.exigir('USUARIOS', 'modificar')
        self._cuenta(usuario_id)
        if usuario_id == usuario.id and not activo:
            raise ErrorNegocio('No puede desactivar su propia cuenta.')
        self._usuarios.cambiar_estado(usuario_id, activo)
        return self._usuarios.por_id(usuario_id)

    def desbloquear(self, usuario, usuario_id, restablecer=False):
        """Libera una cuenta bloqueada; con restablecer=True genera una contraseña temporal nueva."""
        usuario.exigir('USUARIOS', 'modificar')
        self._cuenta(usuario_id)
        self._usuarios.desbloquear(usuario_id)
        temporal = None
        if restablecer:
            temporal = seguridad.contrasena_temporal()
            self._usuarios.cambiar_contrasena(usuario_id, seguridad.hash_contrasena(temporal), True)
        return self._usuarios.por_id(usuario_id), temporal

    def catalogos(self):
        return {'roles': self._catalogo.roles(), 'dependencias': self._catalogo.dependencias(),
                'tipos_equipo': self._catalogo.tipos_equipo(), 'permisos': self._catalogo.matriz_permisos()}


def esta_bloqueada(u, ahora):
    return bool(u.bloqueado_hasta and u.bloqueado_hasta > (ahora.strftime('%Y-%m-%d %H:%M:%S')
                                                         if isinstance(ahora, datetime) else ahora))
