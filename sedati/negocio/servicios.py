"""Servicios del sistema experto: el diagnóstico con el motor de inferencia y la consulta del conocimiento."""
from . import explicacion
from .errores import ErrorNegocio, NoEncontrado
from .fabrica import evidencia_desde, granulos_desde
from .modelos import OpcionRespuesta
from .motor_inferencia import MotorInferencia


def _texto_fecha(fecha):
    return fecha.strftime('%Y-%m-%d %H:%M:%S') if hasattr(fecha, 'strftime') else str(fecha)


class SesionDiagnostico:
    """Un diagnóstico en curso: une el motor de inferencia con su registro en sedati_trx."""

    def __init__(self, motor, dao_diagnostico, diagnostico_id, opciones, datos, reloj):
        self.motor = motor
        self._dao = dao_diagnostico
        self._reloj = reloj
        self.diagnostico_id = diagnostico_id
        self.opciones = opciones
        self.datos = datos              # nombre de quien consulta, categoría del árbol, equipo, ubicación, descripción
        self.finalizada = False
        self.pregunta_actual = None
        self.motivo_conclusion = None
        self.iniciada_en = reloj()

    # compatibilidad con la interfaz de escritorio, que habla de «consulta»
    @property
    def consulta_id(self):
        return self.diagnostico_id

    # ------------------------------------------------------------ preguntas y respuestas
    def avanzar(self):
        """Calcula la siguiente pregunta y si conviene concluir."""
        self.pregunta_actual = self.motor.siguiente_pregunta()
        self.motivo_conclusion = self.motor.motivo_para_concluir(self.pregunta_actual)
        return self.pregunta_actual

    def _guardar(self, evidencia, opcion, origen):
        if self.diagnostico_id:
            r = self.motor.memoria.respuestas[evidencia.id]
            self._dao.guardar_respuesta(self.diagnostico_id, r.orden, evidencia.codigo, opcion.codigo, opcion.valor,
                                        origen, _texto_fecha(self._reloj()))

    def responder(self, evidencia, opcion):
        previa = self.motor.memoria.respuestas.get(evidencia.id)
        origen = 'SINTOMA_INICIAL' if previa and previa.origen == 'SINTOMA_INICIAL' else 'PREGUNTA'
        self.motor.responder(evidencia, opcion, origen)
        self._guardar(evidencia, opcion, origen)
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

    def propuestas(self):
        """Las hipótesis del resultado tal como se guardan en diagnostico_hipotesis."""
        salida = []
        for r in self.resultado():
            g = r.principal.granulo if r.principal else None
            salida.append({'posicion': r.posicion, 'hipotesis_codigo': r.hipotesis.codigo,
                           'hipotesis_nombre': r.hipotesis.nombre, 'granulo_codigo': g.regla if g else None,
                           'granulo_version': g.version if g else None, 'conclusion': g.conclusion if g else None,
                           'accion': g.accion if g else None, 'probabilidad': r.probabilidad, 'certeza': r.certeza})
        return salida

    def finalizar(self):
        if self.finalizada:
            return self.resultado()
        top = self.resultado()
        if self.diagnostico_id:
            self._dao.finalizar(self.diagnostico_id, self.motor.preguntas_respondidas, self.propuestas(),
                                _texto_fecha(self._reloj()))
        self.finalizada = True
        return top

    def cancelar(self):
        if self.diagnostico_id and not self.finalizada:
            self._dao.cancelar(self.diagnostico_id, _texto_fecha(self._reloj()))

    def informe(self):
        """Informe en texto plano del diagnóstico (para exportar)."""
        top = self.resultado()
        d = self.datos
        lineas = ['SEDATI - Informe de diagnóstico', '=' * 60,
                  f'Diagnóstico: {self.diagnostico_id or "-"}    Fecha: {_texto_fecha(self.iniciada_en)[:16]}',
                  f'Consultó: {d.get("nombre") or "-"}    Categoría del árbol: {d.get("categoria") or "-"}', '',
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
                lineas.append(f'Acción recomendada ({g.regla} v{g.version}): {g.accion}')
                if g.riesgo_perdida_datos:
                    lineas.append('ADVERTENCIA: la acción puede ocasionar pérdida de información; respalde antes.')
        lineas += ['', 'CONSULTAS GRANULARES A LA BASE DE CONOCIMIENTO', '-' * 60]
        for paso, desc, filas in self.motor.traza_consultas:
            lineas.append(f'paso {paso:>2} · {desc} → {filas} fila(s)')
        return '\n'.join(lineas)


class ServicioDiagnostico:
    def __init__(self, dao_conocimiento, dao_diagnostico, dao_catalogo, parametros, reloj):
        self._kb = dao_conocimiento
        self._diagnosticos = dao_diagnostico
        self._catalogo = dao_catalogo
        self.parametros = parametros
        self._reloj = reloj

    def opciones_respuesta(self):
        return [OpcionRespuesta(f['codigo'], f['etiqueta'], float(f['valor']), f['color'])
                for f in self._catalogo.escala_respuestas()]

    def categorias(self):
        return self._kb.categorias()

    def sintomas(self, categoria):
        return self._kb.sintomas_por_categoria(categoria)

    def arbol(self):
        """El árbol de decisión en el orden en que se recorre: categoría (A. Energía y arranque primero,
        luego B, C...) → ramas → síntomas con los que empiezan sus reglas."""
        categorias = {}
        for f in self._kb.ramas():
            c = categorias.setdefault(f['categoria_codigo'], {'codigo': f['categoria_codigo'],
                                                              'nombre': f['categoria_nombre'], 'ramas': {}})
            r = c['ramas'].setdefault(f['rama_codigo'], {'codigo': f['rama_codigo'], 'nombre': f['rama_nombre'],
                                                         'sintomas': []})
            r['sintomas'].append({'id': f['id'], 'codigo': f['codigo'], 'enunciado': f['enunciado']})
        salida = []
        for codigo in sorted(categorias):
            c = categorias[codigo]
            salida.append(dict(c, ramas=[c['ramas'][r] for r in sorted(c['ramas'])]))
        return salida

    def ids_de_hipotesis(self, codigos):
        return [f['id'] for f in self._kb.hipotesis_por_codigos(codigos)]

    @staticmethod
    def limpiar_nombre(nombre):
        return ' '.join(str(nombre or '').split())[:80]

    def iniciar(self, sintoma_ids, equipo='', ubicacion='', descripcion='', registrar=True, nombre='',
                categoria=None, descartadas=()):
        """Abre un diagnóstico. nombre: quien consulta (obligatorio si se registra); categoria: letra de la
        categoría del árbol que eligió; descartadas: códigos HIP-NN que no se deben proponer."""
        if not sintoma_ids:
            raise ErrorNegocio('Marque al menos un síntoma para iniciar el diagnóstico.')
        if categoria and (not isinstance(categoria, str) or len(categoria) != 1 or not 'A' <= categoria.upper() <= 'G'):
            raise ErrorNegocio('La categoría del árbol debe ser una letra de la A a la G.')
        categoria = categoria.upper() if categoria else None
        nombre = self.limpiar_nombre(nombre)
        if registrar and not nombre:
            raise ErrorNegocio('Escriba su nombre («¿Cómo te llamas?») para registrar el diagnóstico.')
        motor = MotorInferencia(self._kb, self.parametros)
        motor.iniciar(sintoma_ids, self.ids_de_hipotesis(descartadas))
        datos = {'nombre': nombre, 'categoria': categoria, 'equipo': equipo, 'ubicacion': ubicacion,
                 'descripcion': descripcion}
        diagnostico_id = None
        if registrar:
            diagnostico_id = self._diagnosticos.crear(nombre, categoria, self.parametros.como_texto(), datos,
                                                      _texto_fecha(self._reloj()))
            for r in motor.memoria.respuestas_en_orden():
                self._diagnosticos.guardar_respuesta(diagnostico_id, r.orden, r.evidencia.codigo, r.escala_codigo,
                                                     r.valor, r.origen, _texto_fecha(self._reloj()))
        sesion = SesionDiagnostico(motor, self._diagnosticos, diagnostico_id, self.opciones_respuesta(), datos,
                                   self._reloj)
        sesion.avanzar()
        return sesion

    def _evidencia(self, motor, evidencia_id):
        ev = motor.memoria.evidencias.get(evidencia_id)
        if ev is None:
            filas = self._kb.evidencias_por_ids([evidencia_id])
            if not filas:
                raise ErrorNegocio(f'La evidencia {evidencia_id} no existe en la base de conocimiento.')
            ev = evidencia_desde(filas[0])
        return ev

    def reproducir(self, sintoma_ids, respuestas, equipo='', ubicacion='', descripcion='', registrar=False,
                   nombre='', categoria=None, descartadas=()):
        """Rehace un diagnóstico a partir de sus síntomas y de la lista de respuestas [(evidencia_id, escala)].

        Lo usa el servicio web, que no guarda estado entre peticiones (AWS Lambda): cada petición trae
        todo lo respondido y el motor vuelve a razonar desde cero, con las mismas consultas granulares.
        Con registrar=True el diagnóstico y sus respuestas quedan guardados en sedati_trx.
        """
        sesion = self.iniciar(sintoma_ids, equipo, ubicacion, descripcion, registrar, nombre, categoria, descartadas)
        motor = sesion.motor
        for evidencia_id, escala in respuestas:
            ev = self._evidencia(motor, evidencia_id)
            try:
                opcion = sesion.opcion(escala)
            except StopIteration:
                raise ErrorNegocio(f'La respuesta «{escala}» no está en la escala de respuestas.') from None
            previa = motor.memoria.respuestas.get(ev.id)
            origen = 'SINTOMA_INICIAL' if previa and previa.origen == 'SINTOMA_INICIAL' else 'PREGUNTA'
            motor.responder(ev, opcion, origen)
            sesion._guardar(ev, opcion, origen)
        sesion.avanzar()
        return sesion

    def historial(self, nombre=None):
        """Diagnósticos guardados; con nombre, solo los de esa persona."""
        return self._diagnosticos.listar(nombre_usuario=self.limpiar_nombre(nombre) or None)

    def entradas_guardadas(self, diagnostico_id):
        """(síntomas iniciales, respuestas [(evidencia_id, escala)]) de un diagnóstico guardado."""
        respuestas = self._diagnosticos.respuestas(diagnostico_id)
        ids = {f['codigo']: f['id'] for f in self._kb.evidencias_por_codigos([r.evidencia_codigo for r in respuestas])}
        iniciales = [ids[r.evidencia_codigo] for r in respuestas if r.origen == 'SINTOMA_INICIAL' and r.evidencia_codigo in ids]
        preguntas = [(ids[r.evidencia_codigo], r.escala_codigo) for r in respuestas
                     if r.origen == 'PREGUNTA' and r.evidencia_codigo in ids]
        return iniciales, preguntas

    def reconstruir(self, diagnostico_id, descartadas=()):
        """Vuelve a ejecutar un diagnóstico guardado para ver su razonamiento (sin modificarlo)."""
        d = self._diagnosticos.por_id(diagnostico_id)
        if not d:
            raise NoEncontrado(f'No existe el diagnóstico {diagnostico_id}.')
        iniciales, preguntas = self.entradas_guardadas(diagnostico_id)
        if not iniciales:
            raise ErrorNegocio(f'El diagnóstico {diagnostico_id} no tiene síntomas registrados.')
        sesion = self.reproducir(iniciales, preguntas, d.equipo_texto or '', d.ubicacion_texto or '',
                                 d.descripcion or '', registrar=False, nombre=d.nombre_usuario,
                                 categoria=d.categoria_codigo, descartadas=descartadas)
        sesion.diagnostico_id = d.id
        sesion.finalizada = d.estado != 'EN_CURSO'
        sesion.iniciada_en = d.fecha_inicio
        return sesion


class ServicioConocimiento:
    """Consulta de la base de conocimiento para la pantalla de exploración."""

    def __init__(self, dao_conocimiento):
        self._kb = dao_conocimiento

    def estadisticas(self):
        return self._kb.estadisticas()

    def hipotesis(self, incluir_inactivas=False):
        return self._kb.resumen_hipotesis(incluir_inactivas)

    def granulos_de(self, hipotesis_id, incluir_inactivos=False):
        filas = self._kb.condiciones_de_hipotesis(hipotesis_id, incluir_inactivos)
        granulos = list(granulos_desde(filas).values())
        activos = {f['regla']: bool(f['granulo_activo']) for f in filas}
        for g in granulos:
            g.activo = activos.get(g.regla, True)
        return granulos

    def evidencias(self, incluir_inactivas=False):
        return self._kb.listar_evidencias(incluir_inactivas)
