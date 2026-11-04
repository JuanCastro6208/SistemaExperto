"""API REST de SEDATI: expone el sistema experto como servicio web.

La misma clase atiende las peticiones en AWS Lambda (lambda_function.py) y en el servidor
local de pruebas (servidor_web.py). El servicio no guarda estado entre peticiones: el cliente
envía en cada llamada los síntomas iniciales y todas las respuestas, y el motor rehace el
razonamiento con consultas granulares a la base de conocimiento.

Rutas (todas bajo /api):
    GET  /salud                          estado del servicio y de la base de datos
    GET  /catalogo                       categorías con sus síntomas, escala de respuestas y estadísticas
    POST /diagnostico                    siguiente pregunta, top 5 de hipótesis, explicación y traza
    POST /consultas                      guarda la consulta terminada y su diagnóstico
    GET  /consultas                      historial de consultas guardadas
    GET  /consultas/{id}                 razonamiento de una consulta guardada
    GET  /consultas/{id}/informe         informe en texto de una consulta guardada
    GET  /conocimiento/hipotesis         hipótesis de la base de conocimiento
    GET  /conocimiento/hipotesis/{id}    gránulos (reglas If / And / Then) de una hipótesis
    GET  /conocimiento/evidencias        síntomas y pruebas
"""
import re

from ..configuracion import cargar_configuracion
from ..datos import RepositorioConocimiento, RepositorioConsultas, crear_conexion
from ..negocio import ServicioConocimiento, ServicioDiagnostico
from . import serializacion as ser


class ErrorPeticion(Exception):
    """Error en los datos que envió el cliente (respuesta HTTP 400 o 404)."""

    def __init__(self, mensaje, estado=400):
        super().__init__(mensaje)
        self.estado = estado


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


class ApiSEDATI:
    def __init__(self, configuracion=None):
        self.configuracion = configuracion or cargar_configuracion()
        self.conexion = crear_conexion(self.configuracion)
        repo_kb = RepositorioConocimiento(self.conexion)
        self.diagnostico = ServicioDiagnostico(repo_kb, RepositorioConsultas(self.conexion),
                                               self.configuracion.motor)
        self.conocimiento = ServicioConocimiento(repo_kb)
        self._rutas = [
            ('GET', r'/salud', self.salud),
            ('GET', r'/catalogo', self.catalogo),
            ('POST', r'/diagnostico', self.diagnosticar),
            ('POST', r'/consultas', self.guardar_consulta),
            ('GET', r'/consultas', self.historial),
            ('GET', r'/consultas/(\d+)', self.consulta),
            ('GET', r'/consultas/(\d+)/informe', self.informe),
            ('GET', r'/conocimiento/hipotesis', self.hipotesis),
            ('GET', r'/conocimiento/hipotesis/(\d+)', self.granulos_de_hipotesis),
            ('GET', r'/conocimiento/evidencias', self.evidencias),
        ]

    # ================================================================ enrutamiento
    def atender(self, metodo, ruta, cuerpo=None):
        """Devuelve (código HTTP, diccionario JSON) para una petición a la API."""
        indice = ruta.find('/api/')
        ruta = ruta[indice + 4:] if indice >= 0 else ruta
        ruta = '/' + ruta.strip('/')
        coincide_ruta = False
        for m, patron, accion in self._rutas:
            encontrado = re.fullmatch(patron, ruta)
            if not encontrado:
                continue
            coincide_ruta = True
            if m != metodo:
                continue
            try:
                self.conexion.verificar()
                args = encontrado.groups()
                return 200, (accion(cuerpo or {}, *args) if m == 'POST' else accion(*args))
            except ErrorPeticion as e:
                return e.estado, {'error': str(e)}
            except ValueError as e:
                return 400, {'error': str(e)}
        if coincide_ruta:
            return 405, {'error': f'Método {metodo} no permitido en {ruta}.'}
        return 404, {'error': f'La ruta {ruta} no existe.'}

    # ================================================================ estado y catálogo
    def salud(self):
        return {'estado': 'ok', 'servicio': 'SEDATI · sistema experto', 'base_datos': self.conexion.descripcion,
                'estadisticas': ser.fila(self.conocimiento.estadisticas())}

    def catalogo(self):
        categorias, vistos = [], set()
        for c in self.diagnostico.categorias():
            sintomas = []
            for s in self.diagnostico.sintomas(c['codigo']):
                if s['id'] in vistos:      # un síntoma se muestra en la primera categoría donde aparece
                    continue
                vistos.add(s['id'])
                sintomas.append({'id': s['id'], 'codigo': s['codigo'], 'enunciado': s['enunciado']})
            categorias.append({'codigo': c['codigo'], 'nombre': c['nombre'], 'reglas': c['reglas'],
                               'sintomas': sintomas})
        p = self.configuracion.motor
        return {
            'categorias': categorias,
            'escala': [{'codigo': o.codigo, 'etiqueta': o.etiqueta, 'valor': o.valor, 'color': o.color}
                       for o in self.diagnostico.opciones_respuesta()],
            'estadisticas': ser.fila(self.conocimiento.estadisticas()),
            'parametros': {'beta': p.beta, 'umbral_probabilidad': p.umbral_probabilidad,
                           'ganancia_minima': p.ganancia_minima, 'max_preguntas': p.max_preguntas,
                           'hipotesis_resultado': p.hipotesis_resultado},
            'base_datos': self.conexion.descripcion,
        }

    # ================================================================ diagnóstico
    @staticmethod
    def _leer_consulta(cuerpo):
        if not isinstance(cuerpo, dict):
            raise ErrorPeticion('El cuerpo de la petición debe ser un objeto JSON.')
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

    def diagnosticar(self, cuerpo):
        sintomas, respuestas = self._leer_consulta(cuerpo)
        return ser.sesion(self.diagnostico.reproducir(sintomas, respuestas))

    def guardar_consulta(self, cuerpo):
        sintomas, respuestas = self._leer_consulta(cuerpo)
        sesion = self.diagnostico.reproducir(
            sintomas, respuestas, _texto(cuerpo, 'equipo', 40), _texto(cuerpo, 'ubicacion', 100),
            _texto(cuerpo, 'descripcion', 2000), registrar=True)
        sesion.finalizar()
        return ser.sesion(sesion)

    def historial(self):
        return {'consultas': [ser.fila(f) for f in self.diagnostico.historial()]}

    def _reconstruir(self, consulta_id):
        sesion = self.diagnostico.reconstruir(int(consulta_id))
        if sesion is None:
            raise ErrorPeticion(f'No existe la consulta {consulta_id}.', 404)
        return sesion

    def consulta(self, consulta_id):
        return ser.sesion(self._reconstruir(consulta_id))

    def informe(self, consulta_id):
        sesion = self._reconstruir(consulta_id)
        return {'consulta_id': sesion.consulta_id, 'informe': sesion.informe()}

    # ================================================================ base de conocimiento
    def hipotesis(self):
        return {'hipotesis': [ser.fila(f) for f in self.conocimiento.hipotesis()],
                'estadisticas': ser.fila(self.conocimiento.estadisticas())}

    def granulos_de_hipotesis(self, hipotesis_id):
        granulos = self.conocimiento.granulos_de(int(hipotesis_id))
        if not granulos:
            raise ErrorPeticion(f'La hipótesis {hipotesis_id} no existe o no tiene reglas activas.', 404)
        return {'hipotesis_id': int(hipotesis_id), 'granulos': [ser.granulo(g) for g in granulos]}

    def evidencias(self):
        return {'evidencias': [ser.fila(f) for f in self.conocimiento.evidencias()]}
