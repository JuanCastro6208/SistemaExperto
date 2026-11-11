"""API REST de SEDATI: expone el sistema experto y los procesos transaccionales como servicio web.

La misma clase atiende las peticiones en AWS Lambda (lambda_function.py) y en el servidor local
(servidor_web.py). El servicio no guarda estado entre peticiones:
  · la sesión viaja en un token firmado (cabecera «Authorization: Bearer <token>»); cada respuesta
    autenticada trae en «_sesion» un token renovado, y a los 15 minutos sin actividad vence;
  · en el diagnóstico, el cliente envía en cada llamada los síntomas iniciales y todas las respuestas,
    y el motor rehace el razonamiento con consultas granulares a la base de conocimiento.

Cada ruta declara el módulo y la acción que exige; el permiso se comprueba aquí, en el servidor,
contra la matriz rol_permiso de la base de datos (ocultar una opción del menú no es la única barrera).
Las rutas están documentadas en RUTAS (al final del archivo) y en la vista «Servicio» de la web.
"""
import re

from ..configuracion import cargar_configuracion
from ..datos import ErrorIntegridad, FabricaDAO, crear_conexiones
from ..negocio import (ErrorNegocio, NoAutenticado, ServicioAcceso, SinPermiso, ServicioAdministracionConocimiento,
                       ServicioAtencion, ServicioConocimiento, ServicioDiagnostico, ServicioUsuarios)
from ..negocio.seguridad import FirmadorSesion
from . import serializacion as ser


_PERMITIDAS_CLAVE_TEMPORAL = {'sesion', 'cambiar_contrasena', 'catalogos', 'salud'}


class ErrorPeticion(ErrorNegocio):
    """Error en los datos que envió el cliente (respuesta HTTP 400 o 404)."""


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
    return ('/api' + patron.replace(r'(\d+)', '{id}').replace(r'(R-\d+)', '{regla}')
            .replace(r'([A-Za-z0-9-]+)', '{inventario}'))


def _booleano(valor):
    return valor in (True, 1, '1', 'true', 'si', 'sí')


class ApiSEDATI:
    def __init__(self, configuracion=None):
        self.configuracion = conf = configuracion or cargar_configuracion()
        kb, trx = crear_conexiones(conf)
        self.fabrica = f = FabricaDAO(kb, trx)
        reloj = conf.ahora
        self.diagnostico = ServicioDiagnostico(f.conocimiento(), f.diagnosticos(), f.catalogo(), conf.motor, reloj)
        self.conocimiento = ServicioConocimiento(f.conocimiento())
        self.acceso = ServicioAcceso(f.usuarios(), f.bitacora_acceso(), f.catalogo(), FirmadorSesion(conf.secreto),
                                     reloj)
        self.usuarios = ServicioUsuarios(f.usuarios(), f.catalogo(), reloj)
        self.atencion = ServicioAtencion(f, self.diagnostico, reloj)
        self.admin_conocimiento = ServicioAdministracionConocimiento(
            f.administracion_conocimiento(), f.conocimiento(), f.auditoria(), reloj)
        if getattr(trx, 'creada', False) and conf.datos_demostracion:
            from .demostracion import cargar_demostracion
            cargar_demostracion(self)
        self._rutas = [(m, re.compile(p), getattr(self, h), publica) for m, p, h, publica, _ in RUTAS]

    # ================================================================ enrutamiento
    def atender(self, metodo, ruta, cuerpo=None, cabeceras=None, consulta=None, ip=None):
        """Devuelve (código HTTP, diccionario JSON) para una petición a la API."""
        indice = ruta.find('/api/')
        ruta = ruta[indice + 4:] if indice >= 0 else ruta
        ruta = '/' + ruta.strip('/')
        cabeceras = {k.lower(): v for k, v in (cabeceras or {}).items()}
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
                    token = (cabeceras.get('authorization') or '').removeprefix('Bearer ').strip()
                    peticion['usuario'] = self.acceso.autenticar(token)
                    if peticion['usuario'].debe_cambiar_contrasena and accion.__name__ not in _PERMITIDAS_CLAVE_TEMPORAL:
                        raise SinPermiso('Debe cambiar su contraseña temporal antes de continuar.')
                datos = accion(peticion, *encontrado.groups())
                if peticion['usuario'] is not None and isinstance(datos, dict):
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

    # ================================================================ estado y acceso (RF-01)
    def salud(self, p):
        return {'estado': 'ok', 'servicio': 'SEDATI · sistema experto', 'base_datos': self.fabrica.descripcion,
                'estadisticas': ser.fila(self.conocimiento.estadisticas()),
                'rutas': [{'metodo': m, 'ruta': _ruta_legible(r), 'publica': pub, 'descripcion': d}
                          for m, r, _, pub, d in RUTAS]}

    def ingresar(self, p):
        c = p['cuerpo']
        token, exp, usuario = self.acceso.ingresar(c.get('correo'), c.get('contrasena'), p['ip'])
        return {'usuario': usuario.como_dict(), '_sesion': {'token': token, 'expira': exp}}

    def sesion(self, p):
        return {'usuario': p['usuario'].como_dict()}

    def cambiar_contrasena(self, p):
        self.acceso.cambiar_contrasena(p['usuario'], p['cuerpo'].get('actual'), p['cuerpo'].get('nueva'))
        return {'mensaje': 'Contraseña actualizada.'}

    def catalogos(self, p):
        c = self.usuarios.catalogos()
        if not p['usuario'].es_administrador:
            c.pop('permisos')
        return ser.dto(c)

    # ================================================================ usuarios (RF-01)
    def listar_usuarios(self, p):
        return {'usuarios': ser.dto(self.usuarios.listar(p['usuario']))}

    def administradores(self, p):
        p['usuario'].exigir('INCIDENTES')
        return {'administradores': [{'id': a.id, 'nombre': a.nombre} for a in self.usuarios.administradores()]}

    def crear_usuario(self, p):
        cuenta, temporal = self.usuarios.crear(p['usuario'], p['cuerpo'])
        return {'usuario': ser.dto(cuenta), 'contrasena_temporal': temporal}

    def modificar_usuario(self, p, usuario_id):
        return {'usuario': ser.dto(self.usuarios.modificar(p['usuario'], int(usuario_id), p['cuerpo']))}

    def estado_usuario(self, p, usuario_id):
        cuenta = self.usuarios.cambiar_estado(p['usuario'], int(usuario_id), _booleano(p['cuerpo'].get('activo')))
        return {'usuario': ser.dto(cuenta)}

    def desbloquear_usuario(self, p, usuario_id):
        cuenta, temporal = self.usuarios.desbloquear(p['usuario'], int(usuario_id),
                                                     _booleano(p['cuerpo'].get('restablecer')))
        return {'usuario': ser.dto(cuenta), 'contrasena_temporal': temporal}

    def bitacora(self, p):
        return {'accesos': [ser.fila(f) for f in self.acceso.bitacora(p['usuario'])]}

    # ================================================================ incidentes y citas (RF-02)
    def listar_incidentes(self, p):
        q = p['consulta']
        filtros = {k: q.get(k) for k in ('estado', 'categoria', 'inventario', 'desde', 'hasta', 'texto')}
        if q.get('responsable') == 'yo':
            filtros['administrador_id'] = p['usuario'].id
        elif q.get('responsable') == 'ninguno':
            filtros['sin_asignar'] = True
        elif q.get('responsable'):
            filtros['administrador_id'] = _entero(q['responsable'], 'responsable')
        return {'incidentes': ser.dto(self.atencion.listar(p['usuario'], filtros))}

    def reportar_incidente(self, p):
        return {'incidente': ser.dto(self.atencion.reportar(p['usuario'], p['cuerpo']))}

    def detalle_incidente(self, p, incidente_id):
        d = self.atencion.detalle(p['usuario'], int(incidente_id))
        salida = {k: ser.dto(v) for k, v in d.items() if k not in ('rondas', 'riesgos', 'descartadas')}
        if 'rondas' in d:
            salida['rondas'] = [{'diagnostico': ser.dto(r['diagnostico']), 'hipotesis': ser.dto(r['hipotesis']),
                                 'respuestas': r['respuestas']} for r in d['rondas']]
            salida['riesgos'] = d['riesgos']
            salida['descartadas'] = d['descartadas']
        return salida

    def tomar_incidente(self, p, incidente_id):
        return {'incidente': ser.dto(self.atencion.tomar(p['usuario'], int(incidente_id),
                                                         p['cuerpo'].get('administrador_id')))}

    def programar_cita(self, p, incidente_id):
        return {'cita': ser.dto(self.atencion.programar_cita(p['usuario'], int(incidente_id), p['cuerpo']))}

    def reprogramar_cita(self, p, cita_id):
        return {'cita': ser.dto(self.atencion.reprogramar_cita(p['usuario'], int(cita_id), p['cuerpo']))}

    def estado_cita(self, p, cita_id):
        return {'cita': ser.dto(self.atencion.cambiar_estado_cita(p['usuario'], int(cita_id),
                                                                  p['cuerpo'].get('estado')))}

    def agenda(self, p):
        return {'citas': ser.dto(self.atencion.agenda(p['usuario']))}

    def escalar_incidente(self, p, incidente_id):
        return {'incidente': ser.dto(self.atencion.escalar(p['usuario'], int(incidente_id), p['cuerpo']))}

    # ================================================================ diagnóstico (RF-02)
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
        p['usuario'].exigir('DIAGNOSTICO')
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
        m = self.configuracion.motor
        return {
            'categorias': categorias,
            'escala': [{'codigo': o.codigo, 'etiqueta': o.etiqueta, 'valor': o.valor, 'color': o.color}
                       for o in self.diagnostico.opciones_respuesta()],
            'estadisticas': ser.fila(self.conocimiento.estadisticas()),
            'parametros': {'beta': m.beta, 'umbral_probabilidad': m.umbral_probabilidad,
                           'ganancia_minima': m.ganancia_minima, 'max_preguntas': m.max_preguntas,
                           'hipotesis_resultado': m.hipotesis_resultado},
            'base_datos': self.fabrica.descripcion,
        }

    def diagnosticar(self, p):
        """Siguiente pregunta y top 5 (sin guardar). Con «incidente_id» excluye las hipótesis descartadas."""
        p['usuario'].exigir('DIAGNOSTICO')
        sintomas, respuestas = self._leer_consulta(p['cuerpo'])
        incidente = p['cuerpo'].get('incidente_id')
        if incidente:
            return ser.sesion(self.atencion.diagnosticar(p['usuario'], _entero(incidente, 'incidente_id'), sintomas,
                                                         respuestas))
        return ser.sesion(self.diagnostico.reproducir(sintomas, respuestas))

    def ronda_incidente(self, p, incidente_id):
        r = self.atencion.preparar_ronda(p['usuario'], int(incidente_id))
        return {'incidente': ser.dto(r['incidente']), 'ronda': r['ronda'], 'descartadas': r['descartadas'],
                'sintomas': r['sintomas'], 'respuestas': r['respuestas']}

    def guardar_diagnostico_incidente(self, p, incidente_id):
        sintomas, respuestas = self._leer_consulta(p['cuerpo'])
        return ser.sesion(self.atencion.guardar_diagnostico(p['usuario'], int(incidente_id), sintomas, respuestas))

    def guardar_consulta(self, p):
        """Consulta libre (sin incidente): queda en el historial de diagnósticos."""
        p['usuario'].exigir('DIAGNOSTICO', 'crear')
        c = p['cuerpo']
        sintomas, respuestas = self._leer_consulta(c)
        sesion = self.diagnostico.reproducir(sintomas, respuestas, _texto(c, 'equipo', 40), _texto(c, 'ubicacion', 100),
                                             _texto(c, 'descripcion', 2000), registrar=True,
                                             registrado_por=p['usuario'].id)
        sesion.finalizar()
        return ser.sesion(sesion)

    def historial(self, p):
        p['usuario'].exigir('DIAGNOSTICO')
        return {'consultas': ser.dto(self.diagnostico.historial())}

    def _reconstruir(self, p, diagnostico_id):
        p['usuario'].exigir('DIAGNOSTICO')
        return self.diagnostico.reconstruir(int(diagnostico_id))

    def consulta(self, p, diagnostico_id):
        return ser.sesion(self._reconstruir(p, diagnostico_id))

    def informe(self, p, diagnostico_id):
        sesion = self._reconstruir(p, diagnostico_id)
        return {'consulta_id': sesion.diagnostico_id, 'informe': sesion.informe()}

    def decidir_hipotesis(self, p, propuesta_id):
        return {'propuesta': ser.dto(self.atencion.decidir_hipotesis(p['usuario'], int(propuesta_id),
                                                                     p['cuerpo'].get('estado')))}

    def registrar_intervencion(self, p, propuesta_id):
        return {'incidente': ser.dto(self.atencion.registrar_intervencion(p['usuario'], int(propuesta_id),
                                                                          p['cuerpo']))}

    # ================================================================ historial, indicadores, reportes
    def equipos(self, p):
        return {'equipos': [ser.fila(f) for f in self.atencion.equipos(p['usuario'])]}

    def historial_equipo(self, p, inventario):
        h = self.atencion.historial_equipo(p['usuario'], inventario)
        return {'equipo': ser.dto(h['equipo']),
                'incidentes': [{'incidente': ser.dto(i['incidente']), 'confirmadas': ser.dto(i['confirmadas']),
                                'intervenciones': ser.dto(i['intervenciones'])} for i in h['incidentes']]}

    def indicadores(self, p):
        q = p['consulta']
        return ser.dto(self.atencion.indicadores(p['usuario'], q.get('desde'), q.get('hasta')))

    def exportar_incidentes(self, p):
        q = p['consulta']
        filtros = {k: q.get(k) for k in ('estado', 'categoria', 'inventario', 'desde', 'hasta', 'texto')}
        fecha = self.configuracion.ahora().strftime('%Y%m%d_%H%M')
        return {'nombre': f'incidentes_sedati_{fecha}.csv',
                'contenido': self.atencion.exportar_csv(p['usuario'], filtros)}

    # ================================================================ base de conocimiento (RF-03)
    def hipotesis(self, p):
        p['usuario'].exigir('CONOCIMIENTO')
        todas = _booleano(p['consulta'].get('todas'))
        return {'hipotesis': [ser.fila(f) for f in self.conocimiento.hipotesis(todas)],
                'estadisticas': ser.fila(self.conocimiento.estadisticas())}

    def granulos_de_hipotesis(self, p, hipotesis_id):
        p['usuario'].exigir('CONOCIMIENTO')
        granulos = self.conocimiento.granulos_de(int(hipotesis_id), _booleano(p['consulta'].get('todas')))
        return {'hipotesis_id': int(hipotesis_id), 'granulos': [ser.granulo(g) for g in granulos]}

    def evidencias(self, p):
        p['usuario'].exigir('CONOCIMIENTO')
        todas = _booleano(p['consulta'].get('todas'))
        return {'evidencias': [ser.fila(f) for f in self.conocimiento.evidencias(todas)]}

    def ramas(self, p):
        return {'ramas': [ser.fila(f) for f in self.admin_conocimiento.ramas(p['usuario'])]}

    def auditoria(self, p):
        return {'auditoria': ser.dto(self.admin_conocimiento.auditoria(p['usuario'], p['consulta'].get('codigo')))}

    def crear_hipotesis(self, p):
        return {'hipotesis': ser.fila(self.admin_conocimiento.crear_hipotesis(p['usuario'], p['cuerpo']))}

    def estado_hipotesis(self, p, hipotesis_id):
        h = self.admin_conocimiento.cambiar_estado_hipotesis(p['usuario'], int(hipotesis_id),
                                                             _booleano(p['cuerpo'].get('activo')))
        return {'hipotesis': ser.fila(h)}

    def crear_evidencia(self, p):
        return {'evidencia': ser.fila(self.admin_conocimiento.crear_evidencia(p['usuario'], p['cuerpo']))}

    def estado_evidencia(self, p, evidencia_id):
        e = self.admin_conocimiento.cambiar_estado_evidencia(p['usuario'], int(evidencia_id),
                                                             _booleano(p['cuerpo'].get('activo')))
        return {'evidencia': ser.fila(e)}

    def crear_granulo(self, p):
        return {'condiciones': [ser.fila(f) for f in self.admin_conocimiento.crear_granulo(p['usuario'], p['cuerpo'])]}

    def ver_granulo(self, p, regla):
        return {'condiciones': [ser.fila(f) for f in self.admin_conocimiento.granulo(p['usuario'], regla)]}

    def modificar_granulo(self, p, regla):
        filas = self.admin_conocimiento.modificar_granulo(p['usuario'], regla, p['cuerpo'])
        return {'condiciones': [ser.fila(f) for f in filas]}

    def estado_granulo(self, p, regla):
        filas = self.admin_conocimiento.cambiar_estado_granulo(p['usuario'], regla, _booleano(p['cuerpo'].get('activo')))
        return {'condiciones': [ser.fila(f) for f in filas]}

    def simular_granulo(self, p, regla):
        return self.admin_conocimiento.simular(p['usuario'], regla, p['cuerpo'].get('evidencias'))


# (método, ruta, función, pública, descripción) — la vista «Servicio» de la web muestra esta lista.
RUTAS = [
    ('GET', r'/salud', 'salud', True, 'Estado del servicio y de las dos bases de datos'),
    ('POST', r'/auth/ingresar', 'ingresar', True, 'Ingreso con correo y contraseña; devuelve el token de sesión'),
    ('GET', r'/auth/sesion', 'sesion', False, 'Usuario de la sesión y sus permisos'),
    ('POST', r'/auth/contrasena', 'cambiar_contrasena', False, 'Cambio de la contraseña propia'),
    ('GET', r'/catalogos', 'catalogos', False, 'Roles, dependencias, tipos de equipo y matriz de permisos'),
    ('GET', r'/usuarios', 'listar_usuarios', False, 'Cuentas de usuario (administrador)'),
    ('POST', r'/usuarios', 'crear_usuario', False, 'Crear una cuenta con contraseña temporal'),
    ('GET', r'/usuarios/bitacora', 'bitacora', False, 'Bitácora de intentos de ingreso'),
    ('POST', r'/usuarios/(\d+)', 'modificar_usuario', False, 'Modificar nombre, correo, dependencia o rol'),
    ('POST', r'/usuarios/(\d+)/estado', 'estado_usuario', False, 'Activar o desactivar una cuenta'),
    ('POST', r'/usuarios/(\d+)/desbloquear', 'desbloquear_usuario', False, 'Desbloquear y restablecer la contraseña'),
    ('GET', r'/administradores', 'administradores', False, 'Administradores activos (para asignar responsables)'),
    ('GET', r'/incidentes', 'listar_incidentes', False, 'Incidentes (el solicitante solo ve los suyos), con filtros'),
    ('POST', r'/incidentes', 'reportar_incidente', False, 'Reportar un incidente (crea el equipo si no existe)'),
    ('GET', r'/incidentes/(\d+)', 'detalle_incidente', False, 'Incidente con historial, citas, rondas y soluciones'),
    ('POST', r'/incidentes/(\d+)/tomar', 'tomar_incidente', False, 'Asumir o asignar el incidente'),
    ('POST', r'/incidentes/(\d+)/citas', 'programar_cita', False, 'Programar una cita de atención'),
    ('GET', r'/incidentes/(\d+)/ronda', 'ronda_incidente', False, 'Datos para la siguiente ronda de diagnóstico'),
    ('POST', r'/incidentes/(\d+)/diagnosticos', 'guardar_diagnostico_incidente', False,
     'Guardar una ronda de diagnóstico del incidente'),
    ('POST', r'/incidentes/(\d+)/escalar', 'escalar_incidente', False, 'Escalar el incidente a otra área'),
    ('GET', r'/citas', 'agenda', False, 'Agenda de citas'),
    ('POST', r'/citas/(\d+)', 'reprogramar_cita', False, 'Reprogramar una cita PROGRAMADA'),
    ('POST', r'/citas/(\d+)/estado', 'estado_cita', False, 'Cancelar, marcar atendida o inasistencia'),
    ('GET', r'/catalogo', 'catalogo', False, 'Categorías del árbol, síntomas iniciales y escala de respuestas'),
    ('POST', r'/diagnostico', 'diagnosticar', False, 'Siguiente pregunta, top 5 con peso probabilístico y explicación'),
    ('POST', r'/consultas', 'guardar_consulta', False, 'Guardar una consulta libre (sin incidente)'),
    ('GET', r'/consultas', 'historial', False, 'Historial de diagnósticos'),
    ('GET', r'/consultas/(\d+)', 'consulta', False, 'Razonamiento de un diagnóstico guardado'),
    ('GET', r'/consultas/(\d+)/informe', 'informe', False, 'Informe en texto de un diagnóstico'),
    ('POST', r'/propuestas/(\d+)/decision', 'decidir_hipotesis', False, 'Confirmar o descartar una hipótesis'),
    ('POST', r'/propuestas/(\d+)/intervencion', 'registrar_intervencion', False,
     'Registrar la solución aplicada y su resultado'),
    ('GET', r'/equipos', 'equipos', False, 'Equipos del inventario con su número de incidentes'),
    ('GET', r'/equipos/([A-Za-z0-9-]+)/historial', 'historial_equipo', False, 'Historial de un equipo'),
    ('GET', r'/indicadores', 'indicadores', False, 'Indicadores de la atención'),
    ('GET', r'/reportes/incidentes', 'exportar_incidentes', False, 'Listado de incidentes en CSV'),
    ('GET', r'/conocimiento/hipotesis', 'hipotesis', False, 'Hipótesis de la base de conocimiento'),
    ('POST', r'/conocimiento/hipotesis', 'crear_hipotesis', False, 'Crear una hipótesis'),
    ('GET', r'/conocimiento/hipotesis/(\d+)', 'granulos_de_hipotesis', False, 'Gránulos (If / And / Then) de una hipótesis'),
    ('POST', r'/conocimiento/hipotesis/(\d+)/estado', 'estado_hipotesis', False, 'Activar o desactivar una hipótesis'),
    ('GET', r'/conocimiento/evidencias', 'evidencias', False, 'Síntomas y pruebas'),
    ('POST', r'/conocimiento/evidencias', 'crear_evidencia', False, 'Crear una evidencia'),
    ('POST', r'/conocimiento/evidencias/(\d+)/estado', 'estado_evidencia', False, 'Activar o desactivar una evidencia'),
    ('GET', r'/conocimiento/ramas', 'ramas', False, 'Ramas del árbol de decisión'),
    ('GET', r'/conocimiento/auditoria', 'auditoria', False, 'Auditoría de cambios del conocimiento'),
    ('POST', r'/conocimiento/granulos', 'crear_granulo', False, 'Crear un gránulo (regla If / And / Then)'),
    ('GET', r'/conocimiento/granulos/(R-\d+)', 'ver_granulo', False, 'Condiciones de un gránulo'),
    ('POST', r'/conocimiento/granulos/(R-\d+)', 'modificar_granulo', False, 'Modificar un gránulo (sube la versión)'),
    ('POST', r'/conocimiento/granulos/(R-\d+)/estado', 'estado_granulo', False, 'Activar o desactivar un gránulo'),
    ('POST', r'/conocimiento/granulos/(R-\d+)/simular', 'simular_granulo', False, 'Simular la certeza de un gránulo'),
]
