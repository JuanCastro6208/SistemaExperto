"""API REST de SEDATI: expone el sistema experto como servicio web.

La misma clase atiende las peticiones en AWS Lambda (lambda_function.py) y en el servidor local
(servidor_web.py).

Inicio de sesión (un solo tipo de cuenta, sin roles):
  · la persona crea su cuenta (POST /api/auth/registro) o inicia sesión (POST /api/auth/ingresar) con su
    correo y su contraseña; el servicio responde un token firmado;
  · el token viaja en la cabecera «Authorization: Bearer <token>»; cada respuesta autenticada trae en
    «_sesion» un token renovado, y si pasan los minutos configurados sin actividad, vence;
  · el diagnóstico y el historial exigen sesión; cada diagnóstico guardado queda ligado a la cuenta y cada
    persona solo ve los suyos. El estado del servicio, el árbol y la base de conocimiento son públicos.

El servicio no guarda estado entre peticiones: en el diagnóstico, el cliente envía en cada llamada los
síntomas iniciales (los que eligió al recorrer el árbol de decisión) y todas las respuestas, y el motor
rehace el razonamiento con consultas granulares a la base de conocimiento.
Las rutas están documentadas en RUTAS (al final del archivo) y en la vista «Servicio» de la web.
"""
import re
import secrets

from ..configuracion import cargar_configuracion
from ..datos import ErrorIntegridad, FabricaDAO, crear_conexiones
from ..negocio import ErrorNegocio, ServicioAcceso, ServicioConocimiento, ServicioDiagnostico
from ..negocio.seguridad import FirmadorSesion
from . import serializacion as ser


class ErrorPeticion(ErrorNegocio):
    """Error en los datos que envió el cliente (respuesta HTTP 400)."""


def _entero(valor, nombre):
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ErrorPeticion(f'«{nombre}» debe ser un número entero.') from None


def _texto(cuerpo, clave, maximo):
    valor = cuerpo.get(clave) or ''
    if not isinstance(valor, str):
        raise ErrorPeticion(f'«{clave}» debe ser texto.')
    return valor.strip()[:maximo]


def _ruta_legible(patron):
    return '/api' + patron.replace(r'(\d+)', '{id}')


def _booleano(valor):
    return valor in (True, 1, '1', 'true', 'si', 'sí')


def _token(cabeceras):
    valor = (cabeceras.get('authorization') or '').strip()
    return valor[7:].strip() if valor.lower().startswith('bearer ') else ''


class ApiSEDATI:
    def __init__(self, configuracion=None):
        self.configuracion = conf = configuracion or cargar_configuracion()
        kb, trx = crear_conexiones(conf)
        self.fabrica = f = FabricaDAO(kb, trx)
        self.diagnostico = ServicioDiagnostico(f.conocimiento(), f.diagnosticos(), f.catalogo(), conf.motor, conf.ahora)
        self.conocimiento = ServicioConocimiento(f.conocimiento())
        # sin secreto configurado (p. ej. en las pruebas) se usa uno aleatorio: las sesiones valen mientras viva el proceso
        firmador = FirmadorSesion(conf.secreto or secrets.token_hex(32), conf.minutos_sesion)
        self.acceso = ServicioAcceso(f.usuarios(), firmador, conf.ahora)
        self._rutas = [(m, re.compile(p), getattr(self, h), publica) for m, p, h, publica, _ in RUTAS]

    # ================================================================ enrutamiento
    def atender(self, metodo, ruta, cuerpo=None, cabeceras=None, consulta=None, ip=None):
        """Devuelve (código HTTP, diccionario JSON) para una petición a la API."""
        indice = ruta.find('/api/')
        ruta = ruta[indice + 4:] if indice >= 0 else ruta
        ruta = '/' + ruta.strip('/')
        cabeceras = {str(k).lower(): v for k, v in (cabeceras or {}).items()}
        coincide_ruta = False
        for m, patron, accion, publica in self._rutas:
            encontrado = patron.fullmatch(ruta)
            if not encontrado:
                continue
            coincide_ruta = True
            if m != metodo:
                continue
            try:
                self.fabrica.verificar()
                peticion = {'cuerpo': cuerpo if isinstance(cuerpo, dict) else {}, 'consulta': consulta or {},
                            'ip': ip, 'usuario': None}
                if not publica:
                    peticion['usuario'] = self.acceso.autenticar(_token(cabeceras))
                datos = accion(peticion, *encontrado.groups())
                if peticion['usuario'] is not None:
                    token, exp = self.acceso.renovar(peticion['usuario'])
                    datos['_sesion'] = {'token': token, 'expira': exp}
                return 200, datos
            except ErrorNegocio as e:
                return e.estado, {'error': str(e)}
            except ErrorIntegridad as e:
                return 409, {'error': str(e)}
            except ValueError as e:
                return 400, {'error': str(e)}
        if coincide_ruta:
            return 405, {'error': f'Método {metodo} no permitido en {ruta}.'}
        return 404, {'error': f'La ruta {ruta} no existe.'}

    # ================================================================ estado del servicio
    def salud(self, p):
        return {'estado': 'ok', 'servicio': 'SEDATI · sistema experto', 'base_datos': self.fabrica.descripcion,
                'estadisticas': ser.fila(self.conocimiento.estadisticas()),
                'rutas': [{'metodo': m, 'ruta': _ruta_legible(r), 'descripcion': d, 'requiere_sesion': not publica}
                          for m, r, _, publica, d in RUTAS]}

    # ================================================================ acceso
    @staticmethod
    def _con_sesion(token, exp, usuario):
        return {'usuario': usuario.como_dict(), '_sesion': {'token': token, 'expira': exp}}

    def registrar(self, p):
        """Crea la cuenta y deja la sesión iniciada."""
        c = p['cuerpo']
        return self._con_sesion(*self.acceso.registrar(c.get('nombre'), c.get('correo'), c.get('contrasena')))

    def ingresar(self, p):
        c = p['cuerpo']
        return self._con_sesion(*self.acceso.ingresar(c.get('correo'), c.get('contrasena')))

    def sesion(self, p):
        """Comprueba que el token siga vigente y devuelve la cuenta (la respuesta trae el token renovado)."""
        return {'usuario': p['usuario'].como_dict()}

    # ================================================================ diagnóstico
    @staticmethod
    def _leer_consulta(cuerpo):
        sintomas = cuerpo.get('sintomas')
        if not isinstance(sintomas, list) or not sintomas:
            raise ErrorPeticion('Envíe al menos un síntoma en «sintomas» (lista de id de evidencia).')
        sintomas = list(dict.fromkeys(_entero(s, 'sintomas') for s in sintomas))
        respuestas = cuerpo.get('respuestas') or []
        if not isinstance(respuestas, list):
            raise ErrorPeticion('«respuestas» debe ser una lista de {evidencia_id, escala}.')
        leidas = []
        for r in respuestas:
            if not isinstance(r, dict) or 'evidencia_id' not in r or 'escala' not in r:
                raise ErrorPeticion('Cada respuesta debe tener «evidencia_id» y «escala».')
            leidas.append((_entero(r['evidencia_id'], 'evidencia_id'), str(r['escala'])))
        return sintomas, leidas

    def catalogo(self, p):
        """El árbol de decisión en el orden en que se pregunta (A. Energía y arranque primero) y la escala."""
        m = self.configuracion.motor
        return {
            'categorias': self.diagnostico.arbol(),
            'escala': [{'codigo': o.codigo, 'etiqueta': o.etiqueta, 'valor': o.valor, 'color': o.color}
                       for o in self.diagnostico.opciones_respuesta()],
            'estadisticas': ser.fila(self.conocimiento.estadisticas()),
            'parametros': {'beta': m.beta, 'umbral_probabilidad': m.umbral_probabilidad,
                           'ganancia_minima': m.ganancia_minima, 'max_preguntas': m.max_preguntas,
                           'hipotesis_resultado': m.hipotesis_resultado},
            'base_datos': self.fabrica.descripcion,
        }

    def diagnosticar(self, p):
        """Siguiente pregunta y top 5 (sin guardar)."""
        sintomas, respuestas = self._leer_consulta(p['cuerpo'])
        u = p['usuario']
        return ser.sesion(self.diagnostico.reproducir(sintomas, respuestas, nombre=u.nombre, usuario_id=u.id,
                                                      categoria=_texto(p['cuerpo'], 'categoria', 1) or None))

    def guardar_consulta(self, p):
        """Guarda el diagnóstico terminado a nombre de la cuenta con la que se inició sesión."""
        c = p['cuerpo']
        u = p['usuario']
        sintomas, respuestas = self._leer_consulta(c)
        sesion = self.diagnostico.reproducir(sintomas, respuestas, _texto(c, 'equipo', 40), _texto(c, 'ubicacion', 100),
                                             _texto(c, 'descripcion', 2000), registrar=True, nombre=u.nombre,
                                             usuario_id=u.id, categoria=_texto(c, 'categoria', 1) or None)
        sesion.finalizar()
        return ser.sesion(sesion)

    def historial(self, p):
        """Solo los diagnósticos de la cuenta que inició sesión."""
        return {'consultas': ser.dto(self.diagnostico.historial(usuario_id=p['usuario'].id))}

    def consulta(self, p, diagnostico_id):
        return ser.sesion(self.diagnostico.reconstruir(int(diagnostico_id), usuario_id=p['usuario'].id))

    def informe(self, p, diagnostico_id):
        sesion = self.diagnostico.reconstruir(int(diagnostico_id), usuario_id=p['usuario'].id)
        return {'consulta_id': sesion.diagnostico_id, 'informe': sesion.informe()}

    # ================================================================ base de conocimiento (consulta)
    def hipotesis(self, p):
        todas = _booleano(p['consulta'].get('todas'))
        return {'hipotesis': [ser.fila(f) for f in self.conocimiento.hipotesis(todas)],
                'estadisticas': ser.fila(self.conocimiento.estadisticas())}

    def granulos_de_hipotesis(self, p, hipotesis_id):
        granulos = self.conocimiento.granulos_de(int(hipotesis_id), _booleano(p['consulta'].get('todas')))
        return {'hipotesis_id': int(hipotesis_id), 'granulos': [ser.granulo(g) for g in granulos]}

    def evidencias(self, p):
        todas = _booleano(p['consulta'].get('todas'))
        return {'evidencias': [ser.fila(f) for f in self.conocimiento.evidencias(todas)]}


# (método, ruta, función, pública, descripción) — la vista «Servicio» de la web muestra esta lista.
# pública = False: exige la cabecera «Authorization: Bearer <token>» de una sesión vigente.
RUTAS = [
    ('GET', r'/salud', 'salud', True, 'Estado del servicio y de las dos bases de datos'),
    ('POST', r'/auth/registro', 'registrar', True, 'Crear una cuenta (nombre, correo, contraseña); deja la sesión iniciada'),
    ('POST', r'/auth/ingresar', 'ingresar', True, 'Iniciar sesión con correo y contraseña; devuelve el token de sesión'),
    ('GET', r'/auth/sesion', 'sesion', False, 'Cuenta de la sesión actual (y token renovado)'),
    ('GET', r'/catalogo', 'catalogo', True, 'Árbol de decisión (categoría → rama → síntomas) y escala de respuestas'),
    ('POST', r'/diagnostico', 'diagnosticar', False, 'Siguiente pregunta, top 5 con peso probabilístico y explicación'),
    ('POST', r'/consultas', 'guardar_consulta', False, 'Guardar el diagnóstico a nombre de la cuenta'),
    ('GET', r'/consultas', 'historial', False, 'Historial de diagnósticos de la cuenta'),
    ('GET', r'/consultas/(\d+)', 'consulta', False, 'Razonamiento de un diagnóstico guardado (solo los propios)'),
    ('GET', r'/consultas/(\d+)/informe', 'informe', False, 'Informe en texto de un diagnóstico (solo los propios)'),
    ('GET', r'/conocimiento/hipotesis', 'hipotesis', True, 'Hipótesis de la base de conocimiento'),
    ('GET', r'/conocimiento/hipotesis/(\d+)', 'granulos_de_hipotesis', True, 'Gránulos (If / And / Then) de una hipótesis'),
    ('GET', r'/conocimiento/evidencias', 'evidencias', True, 'Síntomas y pruebas'),
]
