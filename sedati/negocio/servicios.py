"""Servicios que la capa de presentación usa para trabajar con el sistema experto."""
from datetime import datetime

from . import explicacion
from .fabrica import evidencia_desde, granulos_desde
from .modelos import OpcionRespuesta
from .motor_inferencia import MotorInferencia


class SesionDiagnostico:
    """Una consulta en curso: une el motor de inferencia con su registro en la base de datos."""

    def __init__(self, motor, repo_consultas, consulta_id, opciones, datos):
        self.motor = motor
        self._repo = repo_consultas
        self.consulta_id = consulta_id
        self.opciones = opciones
        self.datos = datos              # equipo, ubicación, descripción
        self.finalizada = False
        self.pregunta_actual = None
        self.motivo_conclusion = None
        self.iniciada_en = datetime.now()

    # ------------------------------------------------------------ preguntas y respuestas
    def avanzar(self):
        """Calcula la siguiente pregunta y si conviene concluir."""
        self.pregunta_actual = self.motor.siguiente_pregunta()
        self.motivo_conclusion = self.motor.motivo_para_concluir(self.pregunta_actual)
        return self.pregunta_actual

    def responder(self, evidencia, opcion):
        es_inicial = (evidencia.id in self.motor.memoria.respuestas and
                      self.motor.memoria.respuestas[evidencia.id].origen == 'SINTOMA_INICIAL')
        origen = 'SINTOMA_INICIAL' if es_inicial else 'PREGUNTA'
        self.motor.responder(evidencia, opcion, origen)
        r = self.motor.memoria.respuestas[evidencia.id]
        if self.consulta_id:
            self._repo.guardar_respuesta(self.consulta_id, r.orden, evidencia.id, opcion.codigo, opcion.valor, origen)
        return self.avanzar()

    def opcion(self, codigo):
        return next(o for o in self.opciones if o.codigo == codigo)

    # ------------------------------------------------------------ resultado
    def resultado(self):
        return self.motor.resultado()

    def explicar_pregunta(self):
        return explicacion.por_que(self.motor, self.pregunta_actual) if self.pregunta_actual else []

    def explicar_hipotesis(self, resultado):
        return explicacion.como(resultado, self.motor.parametros.beta)

    def finalizar(self):
        if self.finalizada:
            return self.resultado()
        top = self.resultado()
        if self.consulta_id:
            self._repo.finalizar(
                self.consulta_id, self.motor.preguntas_respondidas,
                [(r.posicion, r.hipotesis.id, r.probabilidad, r.certeza,
                  r.principal.granulo.regla if r.principal else None) for r in top])
        self.finalizada = True
        return top

    def cancelar(self):
        if self.consulta_id and not self.finalizada:
            self._repo.cancelar(self.consulta_id)

    def informe(self):
        """Informe en texto plano de la consulta (para exportar)."""
        top = self.resultado()
        d = self.datos
        lineas = ['SEDATI - Informe de diagnóstico', '=' * 60,
                  f'Consulta: {self.consulta_id or "-"}    Fecha: {self.iniciada_en:%Y-%m-%d %H:%M}',
                  f'Equipo: {d.get("equipo") or "-"}    Ubicación: {d.get("ubicacion") or "-"}',
                  f'Descripción: {d.get("descripcion") or "-"}', '',
                  'RESPUESTAS', '-' * 60]
        etiquetas = {o.codigo: o.etiqueta for o in self.opciones}
        for r in self.motor.memoria.respuestas_en_orden():
            lineas.append(f'{r.orden:>2}. [{r.evidencia.codigo}] {r.evidencia.enunciado} → '
                          f'{etiquetas.get(r.escala_codigo, r.escala_codigo)}')
        lineas += ['', f'HIPÓTESIS MÁS PROBABLES ({len(top)})', '-' * 60]
        for r in top:
            lineas.append(f'{r.posicion}. {r.hipotesis.nombre:<55} {r.probabilidad:6.1%}   FC {r.certeza:+.2f}')
        for r in top:
            lineas += ['', '=' * 60] + self.explicar_hipotesis(r)
            if r.principal:
                g = r.principal.granulo
                lineas.append(f'Acción recomendada ({g.regla}): {g.accion}')
                if g.riesgo_perdida_datos:
                    lineas.append('ADVERTENCIA: la acción puede ocasionar pérdida de información; respalde antes.')
        lineas += ['', 'CONSULTAS GRANULARES A LA BASE DE CONOCIMIENTO', '-' * 60]
        for paso, desc, filas in self.motor.traza_consultas:
            lineas.append(f'paso {paso:>2} · {desc} → {filas} fila(s)')
        return '\n'.join(lineas)


class ServicioDiagnostico:
    def __init__(self, repo_conocimiento, repo_consultas, parametros):
        self._kb = repo_conocimiento
        self._consultas = repo_consultas
        self.parametros = parametros

    def opciones_respuesta(self):
        return [OpcionRespuesta(f['codigo'], f['etiqueta'], float(f['valor']), f['color'])
                for f in self._consultas.escala()]

    def categorias(self):
        return self._kb.categorias()

    def sintomas(self, categoria):
        return self._kb.sintomas_por_categoria(categoria)

    def iniciar(self, sintoma_ids, equipo='', ubicacion='', descripcion='', registrar=True):
        motor = MotorInferencia(self._kb, self.parametros)
        motor.iniciar(sintoma_ids)
        consulta_id = None
        if registrar:
            consulta_id = self._consultas.crear(equipo, ubicacion, descripcion, self.parametros.como_texto())
            for r in motor.memoria.respuestas_en_orden():
                self._consultas.guardar_respuesta(consulta_id, r.orden, r.evidencia.id, r.escala_codigo,
                                                  r.valor, r.origen)
        sesion = SesionDiagnostico(motor, self._consultas, consulta_id, self.opciones_respuesta(),
                                   {'equipo': equipo, 'ubicacion': ubicacion, 'descripcion': descripcion})
        sesion.avanzar()
        return sesion

    def reproducir(self, sintoma_ids, respuestas, equipo='', ubicacion='', descripcion='', registrar=False):
        """Rehace una consulta a partir de sus síntomas y de la lista de respuestas [(evidencia_id, escala)].

        Lo usa el servicio web, que no guarda estado entre peticiones (AWS Lambda): cada petición trae
        todo lo respondido y el motor vuelve a razonar desde cero, con las mismas consultas granulares.
        Con registrar=True la consulta y sus respuestas quedan guardadas en la base.
        """
        sesion = self.iniciar(sintoma_ids, equipo, ubicacion, descripcion, registrar=registrar)
        motor = sesion.motor
        for evidencia_id, escala in respuestas:
            ev = motor.memoria.evidencias.get(evidencia_id)
            if ev is None:
                filas = self._kb.evidencias_por_ids([evidencia_id])
                if not filas:
                    raise ValueError(f'La evidencia {evidencia_id} no existe en la base de conocimiento.')
                ev = evidencia_desde(filas[0])
            try:
                opcion = sesion.opcion(escala)
            except StopIteration:
                raise ValueError(f'La respuesta «{escala}» no está en la escala de respuestas.') from None
            previa = motor.memoria.respuestas.get(ev.id)
            origen = 'SINTOMA_INICIAL' if previa and previa.origen == 'SINTOMA_INICIAL' else 'PREGUNTA'
            motor.responder(ev, opcion, origen)
            if sesion.consulta_id:
                r = motor.memoria.respuestas[ev.id]
                self._consultas.guardar_respuesta(sesion.consulta_id, r.orden, ev.id, opcion.codigo,
                                                  opcion.valor, origen)
        sesion.avanzar()
        return sesion

    def historial(self):
        return self._consultas.listar()

    def reconstruir(self, consulta_id):
        """Vuelve a ejecutar una consulta guardada para ver su razonamiento (sin modificarla)."""
        datos = self._consultas.obtener(consulta_id)
        if not datos:
            return None
        c = datos['consulta']
        iniciales = [r['evidencia_id'] for r in datos['respuestas'] if r['origen'] == 'SINTOMA_INICIAL']
        sesion = self.iniciar(iniciales, c.get('equipo') or '', c.get('ubicacion') or '',
                              c.get('descripcion') or '', registrar=False)
        sesion.consulta_id = c['id']
        for r in datos['respuestas']:
            if r['origen'] == 'PREGUNTA':
                ev = sesion.motor.memoria.evidencias.get(r['evidencia_id'])
                if ev is None:
                    ev = evidencia_desde(self._kb.evidencias_por_ids([r['evidencia_id']])[0])
                sesion.motor.responder(ev, sesion.opcion(r['escala_codigo']))
        sesion.finalizada = c['estado'] != 'EN_CURSO'
        sesion.avanzar()
        return sesion


class ServicioConocimiento:
    """Consulta de la base de conocimiento para la pantalla de exploración."""

    def __init__(self, repo_conocimiento):
        self._kb = repo_conocimiento

    def estadisticas(self):
        return self._kb.estadisticas()

    def hipotesis(self):
        return self._kb.resumen_hipotesis()

    def granulos_de(self, hipotesis_id):
        return list(granulos_desde(self._kb.condiciones_de_hipotesis(hipotesis_id)).values())

    def evidencias(self):
        return self._kb.listar_evidencias()
