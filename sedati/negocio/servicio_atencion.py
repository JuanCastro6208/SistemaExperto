"""RF-02. Gestión de la atención de incidentes, con el diagnóstico asistido por el motor de inferencia."""
import csv
import io
import re
from datetime import datetime, timedelta

from ..datos.conexion import ErrorIntegridad
from .errores import Conflicto, ErrorNegocio, NoEncontrado, SinPermiso

ESTADOS = ('ABIERTO', 'EN_DIAGNOSTICO', 'ESCALADO', 'CERRADO')
_FECHA = re.compile(r'^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})(?::\d{2})?$')


def _texto(fecha):
    return fecha.strftime('%Y-%m-%d %H:%M:%S')


def _fecha_hora(valor, nombre):
    m = _FECHA.match((valor or '').strip())
    if not m:
        raise ErrorNegocio(f'«{nombre}» debe tener el formato AAAA-MM-DD HH:MM.')
    try:
        return datetime.strptime(f'{m.group(1)} {m.group(2)}:{m.group(3)}:00', '%Y-%m-%d %H:%M:%S')
    except ValueError:
        raise ErrorNegocio(f'«{nombre}» no es una fecha válida.') from None


def _texto_requerido(valor, nombre, maximo, minimo=1):
    texto = (valor or '').strip() if isinstance(valor, str) else ''
    if len(texto) < minimo:
        raise ErrorNegocio(f'Escriba {nombre}.')
    if len(texto) > maximo:
        raise ErrorNegocio(f'{nombre[0].upper()}{nombre[1:]} admite como máximo {maximo} caracteres.')
    return texto


def _integridad(funcion, *args):
    """Ejecuta una operación y traduce el rechazo de la base de datos en un error de negocio."""
    try:
        return funcion(*args)
    except ErrorIntegridad as e:
        raise Conflicto(str(e)) from None


class ServicioAtencion:
    def __init__(self, fabrica, servicio_diagnostico, reloj):
        self._incidentes = fabrica.incidentes()
        self._equipos = fabrica.equipos()
        self._citas = fabrica.citas()
        self._diagnosticos = fabrica.diagnosticos()
        self._intervenciones = fabrica.intervenciones()
        self._escalamientos = fabrica.escalamientos()
        self._usuarios = fabrica.usuarios()
        self._catalogo = fabrica.catalogo()
        self._indicadores = fabrica.indicadores()
        self._admin_kb = fabrica.administracion_conocimiento()
        self._trx = fabrica.conexion_trx
        self._diagnostico = servicio_diagnostico
        self._reloj = reloj

    # ================================================================ utilidades
    def _ahora(self):
        return _texto(self._reloj())

    def _incidente(self, usuario, incidente_id):
        inc = self._incidentes.por_id(incidente_id)
        if inc is None:
            raise NoEncontrado(f'No existe el incidente {incidente_id}.')
        if not usuario.es_administrador and inc.solicitante_id != usuario.id:
            # el solicitante solo ve sus propios incidentes: para él, los demás no existen
            raise NoEncontrado(f'No existe el incidente {incidente_id}.')
        return inc

    @staticmethod
    def _exigir_admin(usuario, modulo='DIAGNOSTICO', accion='crear'):
        usuario.exigir(modulo, accion)
        if not usuario.es_administrador:
            raise SinPermiso('Solo un administrador puede hacer esta operación.')

    @staticmethod
    def _abierto(inc, accion='modificar'):
        if inc.estado == 'CERRADO':
            raise Conflicto(f'El incidente {inc.codigo} está cerrado y no admite cambios. '
                            'Si la falla reaparece, reporte un incidente nuevo.')
        if inc.estado == 'ESCALADO':
            raise Conflicto(f'El incidente {inc.codigo} fue escalado a otra área y no se puede {accion} aquí.')

    # ================================================================ reporte y consulta
    def reportar(self, usuario, datos):
        usuario.exigir('INCIDENTES', 'crear')
        inventario = _texto_requerido(datos.get('inventario'), 'el código de inventario del equipo', 20, 3).upper()
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]{2,19}', inventario):
            raise ErrorNegocio('El código de inventario solo admite letras, números y guiones (ej.: PC-SALA2-014).')
        ubicacion = _texto_requerido(datos.get('ubicacion'), 'la ubicación del equipo', 100, 3)
        descripcion = _texto_requerido(datos.get('descripcion'), 'la descripción de la falla', 2000, 10)
        equipo = self._equipos.por_inventario(inventario)
        if equipo is None:
            tipos = {t['id'] for t in self._catalogo.tipos_equipo()}
            try:
                tipo = int(datos.get('tipo_equipo_id') or 0)
            except (TypeError, ValueError):
                tipo = 0
            if tipo not in tipos:
                raise ErrorNegocio('El equipo no está en el inventario: indique su tipo para registrarlo.')
            marca = (datos.get('marca') or '').strip()[:60] or None
            modelo = (datos.get('modelo') or '').strip()[:60] or None
            dependencia = datos.get('dependencia_id') or None
            equipo_id = _integridad(self._equipos.crear, inventario, tipo, int(dependencia) if dependencia else None,
                                    marca, modelo, ubicacion)
        else:
            if not equipo.activo:
                raise ErrorNegocio('El equipo está dado de baja en el inventario.')
            equipo_id = equipo.id
        nuevo = _integridad(self._incidentes.crear, usuario.id, equipo_id, ubicacion, descripcion, self._ahora())
        return self._incidentes.por_id(nuevo)

    def listar(self, usuario, filtros=None):
        usuario.exigir('INCIDENTES')
        f = dict(filtros or {})
        if f.get('estado') and f['estado'] not in ESTADOS:
            raise ErrorNegocio('Estado no válido.')
        if not usuario.es_administrador:
            f = {'estado': f.get('estado'), 'solicitante_id': usuario.id}
        return self._incidentes.listar(f)

    def detalle(self, usuario, incidente_id):
        usuario.exigir('INCIDENTES')
        inc = self._incidente(usuario, incidente_id)
        datos = {'incidente': inc, 'equipo': self._equipos.por_id(inc.equipo_id),
                 'historial': self._incidentes.historial(inc.id), 'citas': self._citas.de_incidente(inc.id)}
        if usuario.puede('DIAGNOSTICO'):
            rondas = []
            riesgos = {}
            for d in self._diagnosticos.de_incidente(inc.id):
                hipotesis = self._diagnosticos.hipotesis(d.id)
                for h in hipotesis:
                    if h.granulo_codigo and h.granulo_codigo not in riesgos:
                        filas = self._admin_kb.filas_granulo(h.granulo_codigo)
                        riesgos[h.granulo_codigo] = bool(filas and filas[0]['riesgo_perdida_datos'])
                rondas.append({'diagnostico': d, 'hipotesis': hipotesis,
                               'respuestas': len(self._diagnosticos.respuestas(d.id))})
            datos.update({'rondas': rondas, 'riesgos': riesgos,
                          'intervenciones': self._intervenciones.de_incidente(inc.id),
                          'escalamientos': self._escalamientos.de_incidente(inc.id),
                          'descartadas': self._diagnosticos.descartadas_de_incidente(inc.id)})
        return datos

    def tomar(self, usuario, incidente_id, administrador_id=None):
        """El administrador queda como responsable (o asigna a otro administrador activo)."""
        self._exigir_admin(usuario, 'INCIDENTES', 'modificar')
        inc = self._incidente(usuario, incidente_id)
        self._abierto(inc)
        destino = int(administrador_id or usuario.id)
        if destino not in {a.id for a in self._usuarios.listar('ADMINISTRADOR', solo_activos=True)}:
            raise ErrorNegocio('El responsable debe ser un administrador activo.')
        _integridad(self._incidentes.asignar, inc.id, destino, usuario.id, self._ahora())
        return self._incidentes.por_id(inc.id)

    # ================================================================ citas
    def _validar_horario(self, inicio, fin):
        a, b = _fecha_hora(inicio, 'inicio'), _fecha_hora(fin, 'fin')
        if b <= a:
            raise ErrorNegocio('La hora de fin debe ser posterior a la de inicio.')
        if b - a > timedelta(hours=8):
            raise ErrorNegocio('Una cita no puede durar más de ocho horas.')
        if a < self._reloj() - timedelta(minutes=5):
            raise ErrorNegocio('La cita no puede quedar en el pasado.')
        return _texto(a), _texto(b)

    def programar_cita(self, usuario, incidente_id, datos):
        usuario.exigir('CITAS', 'crear')
        inc = self._incidente(usuario, incidente_id)
        self._abierto(inc, 'programar citas')
        inicio, fin = self._validar_horario(datos.get('inicio'), datos.get('fin'))
        lugar = _texto_requerido(datos.get('lugar') or inc.ubicacion, 'el lugar de la cita', 100, 3)
        administrador = inc.administrador_id
        if administrador is None:
            if not usuario.es_administrador:
                raise Conflicto('Su incidente aún no tiene un administrador asignado. '
                                'Podrá programar la cita cuando un administrador lo tome.')
            administrador = usuario.id
            _integridad(self._incidentes.asignar, inc.id, usuario.id, usuario.id, self._ahora())
        nueva = _integridad(self._citas.crear, inc.id, administrador, inicio, fin, lugar, usuario.id, self._ahora())
        return self._citas.por_id(nueva)

    def _cita(self, usuario, cita_id):
        c = self._citas.por_id(cita_id)
        if c is None:
            raise NoEncontrado(f'No existe la cita {cita_id}.')
        self._incidente(usuario, c.incidente_id)      # comprueba que el solicitante sea el dueño
        if c.estado != 'PROGRAMADA':
            raise Conflicto(f'La cita está {c.estado.replace("_", " ").lower()} y ya no se puede modificar.')
        return c

    def reprogramar_cita(self, usuario, cita_id, datos):
        usuario.exigir('CITAS', 'modificar')
        c = self._cita(usuario, cita_id)
        inicio, fin = self._validar_horario(datos.get('inicio'), datos.get('fin'))
        lugar = _texto_requerido(datos.get('lugar') or c.lugar, 'el lugar de la cita', 100, 3)
        _integridad(self._citas.reprogramar, c.id, inicio, fin, lugar)
        return self._citas.por_id(c.id)

    def cambiar_estado_cita(self, usuario, cita_id, estado):
        usuario.exigir('CITAS', 'modificar')
        if estado not in ('CANCELADA', 'ATENDIDA', 'NO_ASISTIO'):
            raise ErrorNegocio('Estado de cita no válido.')
        c = self._cita(usuario, cita_id)
        if estado != 'CANCELADA' and not usuario.es_administrador:
            raise SinPermiso('Solo el administrador marca una cita como atendida o como inasistencia.')
        _integridad(self._citas.cambiar_estado, c.id, estado)
        return self._citas.por_id(c.id)

    def agenda(self, usuario):
        usuario.exigir('CITAS')
        if usuario.es_administrador:
            return self._citas.listar(desde=_texto(self._reloj() - timedelta(days=1)))
        return self._citas.listar(solicitante_id=usuario.id)

    # ================================================================ diagnóstico ligado al incidente
    def preparar_ronda(self, usuario, incidente_id):
        """Lo que necesita la pantalla para diagnosticar: ronda siguiente, descartadas y evidencias previas."""
        self._exigir_admin(usuario)
        inc = self._incidente(usuario, incidente_id)
        self._abierto(inc, 'diagnosticar')
        rondas = self._diagnosticos.de_incidente(inc.id)
        anteriores = [d for d in rondas if d.estado == 'FINALIZADO']
        sintomas, respuestas = [], []
        if anteriores:
            sintomas, respuestas = self._diagnostico.entradas_guardadas(anteriores[-1].id)
        return {'incidente': inc, 'ronda': (max((d.ronda for d in rondas), default=0) + 1),
                'descartadas': self._diagnosticos.descartadas_de_incidente(inc.id),
                'sintomas': sintomas, 'respuestas': [{'evidencia_id': e, 'escala': s} for e, s in respuestas]}

    def diagnosticar(self, usuario, incidente_id, sintomas, respuestas):
        """Ronda en curso (sin guardar): el motor descarta las hipótesis rechazadas antes."""
        self._exigir_admin(usuario)
        inc = self._incidente(usuario, incidente_id)
        self._abierto(inc, 'diagnosticar')
        sesion = self._diagnostico.reproducir(sintomas, respuestas, inc.inventario, inc.ubicacion, inc.descripcion,
                                              registrar=False,
                                              descartadas=self._diagnosticos.descartadas_de_incidente(inc.id))
        sesion.incidente_id = inc.id
        sesion.datos['incidente'] = inc.codigo
        return sesion

    def guardar_diagnostico(self, usuario, incidente_id, sintomas, respuestas):
        """Registra la ronda (evidencias e hipótesis propuestas) y pasa el incidente a EN_DIAGNOSTICO."""
        self._exigir_admin(usuario)
        inc = self._incidente(usuario, incidente_id)
        self._abierto(inc, 'diagnosticar')
        if inc.administrador_id is None:
            _integridad(self._incidentes.asignar, inc.id, usuario.id, usuario.id, self._ahora())
        try:
            sesion = self._diagnostico.reproducir(
                sintomas, respuestas, inc.inventario, inc.ubicacion, inc.descripcion, registrar=True,
                incidente_id=inc.id, registrado_por=usuario.id,
                descartadas=self._diagnosticos.descartadas_de_incidente(inc.id))
            top = sesion.finalizar()
        except ErrorIntegridad as e:
            raise Conflicto(str(e)) from None
        categoria = top[0].principal.granulo.categoria_codigo if top and top[0].principal else None
        if inc.estado == 'ABIERTO' or categoria:
            _integridad(self._incidentes.cambiar_estado, inc.id, 'EN_DIAGNOSTICO', usuario.id, self._ahora(), categoria)
        sesion.datos['incidente'] = inc.codigo
        return sesion

    def _propuesta(self, usuario, diagnostico_hipotesis_id):
        dh = self._diagnosticos.propuesta(diagnostico_hipotesis_id)
        if dh is None:
            raise NoEncontrado(f'No existe la hipótesis propuesta {diagnostico_hipotesis_id}.')
        diag = self._diagnosticos.por_id(dh.diagnostico_id)
        inc = self._incidente(usuario, diag.incidente_id)
        self._abierto(inc)
        ultima = max(d.ronda for d in self._diagnosticos.de_incidente(inc.id))
        if diag.ronda != ultima:
            raise Conflicto('Solo se decide sobre las hipótesis de la última ronda del diagnóstico.')
        return dh, diag, inc

    def decidir_hipotesis(self, usuario, diagnostico_hipotesis_id, estado):
        self._exigir_admin(usuario, 'DIAGNOSTICO', 'modificar')
        if estado not in ('PROPUESTA', 'CONFIRMADA', 'DESCARTADA'):
            raise ErrorNegocio('La decisión debe ser CONFIRMADA, DESCARTADA o PROPUESTA.')
        dh, diag, inc = self._propuesta(usuario, diagnostico_hipotesis_id)
        intervenidas = {i.diagnostico_hipotesis_id for i in self._intervenciones.de_incidente(inc.id)}
        if dh.id in intervenidas:
            raise Conflicto('Esta hipótesis ya tiene una intervención registrada; su decisión no cambia.')
        if estado == 'CONFIRMADA' and intervenidas & {h.id for h in self._diagnosticos.hipotesis(diag.id)}:
            raise Conflicto('La solución de esta ronda no funcionó: ejecute una nueva ronda de diagnóstico.')
        _integridad(self._diagnosticos.decidir, dh.id, estado)
        return self._diagnosticos.propuesta(dh.id)

    def registrar_intervencion(self, usuario, diagnostico_hipotesis_id, datos):
        """SOLUCIONADO cierra el incidente; NO_SOLUCIONADO deja lista una nueva ronda sin esa hipótesis."""
        self._exigir_admin(usuario, 'DIAGNOSTICO', 'crear')
        dh, diag, inc = self._propuesta(usuario, diagnostico_hipotesis_id)
        if dh.estado != 'CONFIRMADA':
            raise Conflicto('Primero confirme la hipótesis sobre la que va a actuar.')
        resultado = datos.get('resultado')
        if resultado not in ('SOLUCIONADO', 'NO_SOLUCIONADO'):
            raise ErrorNegocio('El resultado debe ser SOLUCIONADO o NO_SOLUCIONADO.')
        accion = _texto_requerido(datos.get('accion_aplicada') or dh.accion, 'la acción aplicada', 500, 5)
        tiempo = datos.get('tiempo_min')
        if tiempo in (None, ''):
            tiempo = None
        else:
            try:
                tiempo = int(tiempo)
            except (TypeError, ValueError):
                raise ErrorNegocio('El tiempo invertido debe ser un número de minutos.') from None
            if not 0 <= tiempo <= 1440:
                raise ErrorNegocio('El tiempo invertido debe estar entre 0 y 1440 minutos.')
        observaciones = (datos.get('observaciones') or '').strip()[:2000] or None
        ahora = self._ahora()
        cx = self._trx
        try:
            with cx.transaccion():
                self._intervenciones.registrar(dh.id, usuario.id, accion, resultado, tiempo, observaciones, ahora)
                if resultado == 'SOLUCIONADO':
                    self._incidentes.cambiar_estado(inc.id, 'CERRADO', usuario.id, ahora)
        except ErrorIntegridad as e:
            raise Conflicto(str(e)) from None
        return self._incidentes.por_id(inc.id)

    def escalar(self, usuario, incidente_id, datos):
        self._exigir_admin(usuario, 'INCIDENTES', 'modificar')
        inc = self._incidente(usuario, incidente_id)
        self._abierto(inc, 'escalar')
        if inc.estado != 'EN_DIAGNOSTICO':
            raise Conflicto('Solo se escala un incidente que ya está en diagnóstico.')
        motivo = _texto_requerido(datos.get('motivo'), 'el motivo del escalamiento', 2000, 10)
        destino = _texto_requerido(datos.get('destino'), 'el área de destino', 100, 3)
        ahora = self._ahora()
        cx = self._trx
        try:
            with cx.transaccion():
                self._escalamientos.registrar(inc.id, motivo, destino, usuario.id, ahora)
                self._incidentes.cambiar_estado(inc.id, 'ESCALADO', usuario.id, ahora)
        except ErrorIntegridad as e:
            raise Conflicto(str(e)) from None
        return self._incidentes.por_id(inc.id)

    # ================================================================ historial, indicadores y reportes
    def historial_equipo(self, usuario, inventario):
        self._exigir_admin(usuario, 'INDICADORES', 'consultar')
        equipo = self._equipos.por_inventario((inventario or '').strip())
        if equipo is None:
            raise NoEncontrado(f'No hay un equipo con el inventario «{inventario}».')
        incidentes = []
        for inc in self._incidentes.de_equipo(equipo.id):
            confirmadas = [h for d in self._diagnosticos.de_incidente(inc.id)
                           for h in self._diagnosticos.hipotesis(d.id) if h.estado == 'CONFIRMADA']
            incidentes.append({'incidente': inc, 'confirmadas': confirmadas,
                               'intervenciones': self._intervenciones.de_incidente(inc.id)})
        return {'equipo': equipo, 'incidentes': incidentes}

    def equipos(self, usuario):
        self._exigir_admin(usuario, 'INDICADORES', 'consultar')
        return self._equipos.listar()

    def indicadores(self, usuario, desde=None, hasta=None):
        self._exigir_admin(usuario, 'INDICADORES', 'consultar')
        r = self._indicadores.resumen(desde or None, hasta or None)
        horas = []
        for c in r['cerrados']:
            a = datetime.strptime(c['fecha_apertura'][:19], '%Y-%m-%d %H:%M:%S')
            b = datetime.strptime(c['fecha_cierre'][:19], '%Y-%m-%d %H:%M:%S')
            horas.append((b - a).total_seconds() / 3600)
        cerrados = len(r['cerrados'])
        por_estado = {e: 0 for e in ESTADOS}
        por_estado.update({f['estado']: f['n'] for f in r['por_estado']})
        return {
            'total': sum(por_estado.values()), 'por_estado': por_estado, 'por_categoria': r['por_categoria'],
            'cerrados': cerrados,
            'horas_promedio_solucion': round(sum(horas) / len(horas), 2) if horas else None,
            'minutos_promedio_intervencion': round(r['minutos_intervencion'], 1) if r['minutos_intervencion'] else None,
            'resueltos_primera_ronda': r['resueltos_primera_ronda'],
            'porcentaje_primera_ronda': round(100 * r['resueltos_primera_ronda'] / cerrados, 1) if cerrados else None,
            'escalamientos': r['escalamientos'], 'hipotesis_confirmadas': r['hipotesis_confirmadas'],
            'equipos': r['equipos'],
        }

    def exportar_csv(self, usuario, filtros=None):
        """Listado de incidentes en CSV (separador «;», para abrirlo en Excel en español)."""
        self._exigir_admin(usuario, 'INDICADORES', 'consultar')
        salida = io.StringIO()
        w = csv.writer(salida, delimiter=';')
        w.writerow(['Incidente', 'Estado', 'Categoría', 'Equipo', 'Tipo', 'Ubicación', 'Solicitante', 'Responsable',
                    'Apertura', 'Cierre', 'Rondas', 'Descripción'])
        for i in self.listar(usuario, filtros):
            w.writerow([i.codigo, i.estado, i.categoria_codigo or '', i.inventario, i.tipo_equipo, i.ubicacion,
                        i.solicitante, i.administrador or '', i.fecha_apertura, i.fecha_cierre or '', i.rondas,
                        i.descripcion.replace('\n', ' ')])
        return '﻿' + salida.getvalue()
