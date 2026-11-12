"""API REST de SEDATI: expone el sistema experto como servicio web.

La misma clase atiende las peticiones en AWS Lambda (lambda_function.py) y en el servidor local
(servidor_web.py). No hay cuentas, contraseñas ni roles: la persona escribe su nombre al entrar
(«¿Cómo te llamas?») y ese nombre queda en cada diagnóstico que guarda.

El servicio no guarda estado entre peticiones: en el diagnóstico, el cliente envía en cada llamada los
síntomas iniciales (los que eligió al recorrer el árbol de decisión) y todas las respuestas, y el motor
rehace el razonamiento con consultas granulares a la base de conocimiento.
Las rutas están documentadas en RUTAS (al final del archivo) y en la vista «Servicio» de la web.
"""
import re

from ..configuracion import cargar_configuracion
from ..datos import ErrorIntegridad, FabricaDAO, crear_conexiones
from ..negocio import ErrorNegocio, ServicioConocimiento, ServicioDiagnostico
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


class ApiSEDATI:
    def __init__(self, configuracion=None):
        self.configuracion = conf = configuracion or cargar_configuracion()
        kb, trx = crear_conexiones(conf)
        self.fabrica = f = FabricaDAO(kb, trx)
        self.diagnostico = ServicioDiagnostico(f.conocimiento(), f.diagnosticos(), f.catalogo(), conf.motor, conf.ahora)
        self.conocimiento = ServicioConocimiento(f.conocimiento())
        self._rutas = [(m, re.compile(p), getattr(self, h)) for m, p, h, _ in RUTAS]

    # ================================================================ enrutamiento
    def atender(self, metodo, ruta, cuerpo=None, cabeceras=None, consulta=None, ip=None):
        """Devuelve (código HTTP, diccionario JSON) para una petición a la API."""
        indice = ruta.find('/api/')
        ruta = ruta[indice + 4:] if indice >= 0 else ruta
        ruta = '/' + ruta.strip('/')
        coincide_ruta = False
        for m, patron, accion in self._rutas:
            encontrado = patron.fullmatch(ruta)
            if not encontrado:
                continue
            coincide_ruta = True
            if m != metodo:
                continue
            try:
                self.fabrica.verificar()
                peticion = {'cuerpo': cuerpo if isinstance(cuerpo, dict) else {}, 'consulta': consulta or {}, 'ip': ip}
                return 200, accion(peticion, *encontrado.groups())
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
                'rutas': [{'metodo': m, 'ruta': _ruta_legible(r), 'descripcion': d} for m, r, _, d in RUTAS]}

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
        c = p['cuerpo']
        return ser.sesion(self.diagnostico.reproducir(sintomas, respuestas, nombre=_texto(c, 'nombre', 80),
                                                      categoria=_texto(c, 'categoria', 1) or None))

    def guardar_consulta(self, p):
        """Guarda el diagnóstico terminado con el nombre de quien consultó."""
        c = p['cuerpo']
        sintomas, respuestas = self._leer_consulta(c)
        sesion = self.diagnostico.reproducir(sintomas, respuestas, _texto(c, 'equipo', 40), _texto(c, 'ubicacion', 100),
                                             _texto(c, 'descripcion', 2000), registrar=True,
                                             nombre=_texto(c, 'nombre', 80), categoria=_texto(c, 'categoria', 1) or None)
        sesion.finalizar()
        return ser.sesion(sesion)

    def historial(self, p):
        nombre = p['consulta'].get('nombre')
        return {'consultas': ser.dto(self.diagnostico.historial(nombre))}

    def consulta(self, p, diagnostico_id):
        return ser.sesion(self.diagnostico.reconstruir(int(diagnostico_id)))

    def informe(self, p, diagnostico_id):
        sesion = self.diagnostico.reconstruir(int(diagnostico_id))
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


# (método, ruta, función, descripción) — la vista «Servicio» de la web muestra esta lista.
RUTAS = [
    ('GET', r'/salud', 'salud', 'Estado del servicio y de las dos bases de datos'),
    ('GET', r'/catalogo', 'catalogo', 'Árbol de decisión (categoría → rama → síntomas) y escala de respuestas'),
    ('POST', r'/diagnostico', 'diagnosticar', 'Siguiente pregunta, top 5 con peso probabilístico y explicación'),
    ('POST', r'/consultas', 'guardar_consulta', 'Guardar el diagnóstico con el nombre de quien consultó'),
    ('GET', r'/consultas', 'historial', 'Historial de diagnósticos (?nombre= para ver solo los de una persona)'),
    ('GET', r'/consultas/(\d+)', 'consulta', 'Razonamiento de un diagnóstico guardado'),
    ('GET', r'/consultas/(\d+)/informe', 'informe', 'Informe en texto de un diagnóstico'),
    ('GET', r'/conocimiento/hipotesis', 'hipotesis', 'Hipótesis de la base de conocimiento'),
    ('GET', r'/conocimiento/hipotesis/(\d+)', 'granulos_de_hipotesis', 'Gránulos (If / And / Then) de una hipótesis'),
    ('GET', r'/conocimiento/evidencias', 'evidencias', 'Síntomas y pruebas'),
]
