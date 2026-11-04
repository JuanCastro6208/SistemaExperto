"""Vista de la consulta en curso: preguntas del motor, respuestas graduadas y razonamiento en vivo."""
import customtkinter as ctk

from . import tema
from .componentes import Encabezado, Etiqueta, Insignia, Pestanas, Tarjeta, boton
from .graficos import GraficoEvolucion, GraficoProbabilidades


def _dos_lineas(texto):
    """Parte la etiqueta de una respuesta en dos líneas para que quepa en el botón."""
    if ', ' in texto:
        return texto.replace(', ', '\n', 1)
    partes = texto.rsplit(' ', 1)
    return '\n'.join(partes) if len(texto) > 10 and len(partes) == 2 else texto


def _limpiar(frame):
    for w in frame.winfo_children():
        w.destroy()


class VistaConsulta(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        self.app = app
        self.sesion = None
        self._por_que_visible = False

        self.encabezado = Encabezado(self, 'Consulta en curso', '')
        self.encabezado.pack(fill='x', pady=(0, 14))
        boton(self.encabezado.acciones, 'Ver diagnóstico', self.app.ver_resultado, width=150).pack(side='right')
        boton(self.encabezado.acciones, 'Cancelar consulta', self.app.cancelar_consulta, primario=False,
              width=150).pack(side='right', padx=8)

        cuerpo = ctk.CTkFrame(self, fg_color='transparent')
        cuerpo.pack(fill='both', expand=True)
        cuerpo.grid_columnconfigure(0, weight=11, uniform='c')
        cuerpo.grid_columnconfigure(1, weight=9, uniform='c')
        cuerpo.grid_rowconfigure(0, weight=1)

        # ---------------------------------------------------------------- columna izquierda
        izq = ctk.CTkFrame(cuerpo, fg_color='transparent')
        izq.grid(row=0, column=0, sticky='nsew', padx=(0, 14))
        izq.grid_rowconfigure(1, weight=1)
        izq.grid_columnconfigure(0, weight=1)

        self.tarjeta_pregunta = Tarjeta(izq)
        self.tarjeta_pregunta.grid(row=0, column=0, sticky='ew')

        resp = Tarjeta(izq, 'Respuestas registradas',
                       'Puede corregir cualquier respuesta: el motor vuelve a razonar con el cambio.')
        resp.grid(row=1, column=0, sticky='nsew', pady=(14, 0))
        self.lista_respuestas = ctk.CTkScrollableFrame(resp, fg_color='transparent')
        self.lista_respuestas.pack(fill='both', expand=True, padx=8, pady=8)

        # ---------------------------------------------------------------- columna derecha
        self.pestanas = Pestanas(cuerpo, ['Hipótesis en evaluación', 'Consultas a la base'])
        self.pestanas.grid(row=0, column=1, sticky='nsew')
        t1 = self.pestanas.pagina('Hipótesis en evaluación')
        t2 = self.pestanas.pagina('Consultas a la base')
        self.etiqueta_top = Etiqueta(t1, text='', font=tema.fuente(12), text_color=tema.TEXTO_SUAVE)
        self.etiqueta_top.pack(fill='x', padx=6, pady=(4, 0))
        self.grafico = GraficoProbabilidades(t1, alto=3.0)
        self.grafico.pack(fill='both', expand=True)
        ctk.CTkLabel(t1, text='Evolución del peso probabilístico', font=tema.fuente(12, 'bold'),
                     text_color=tema.TEXTO, anchor='w').pack(fill='x', padx=6)
        self.evolucion = GraficoEvolucion(t1, alto=2.3)
        self.evolucion.pack(fill='both', expand=True)

        self.etiqueta_traza = Etiqueta(t2, text='', font=tema.fuente(12), text_color=tema.TEXTO_SUAVE)
        self.etiqueta_traza.pack(fill='x', padx=6, pady=(4, 6))
        self.traza = ctk.CTkTextbox(t2, font=('Consolas', 12), fg_color=tema.TARJETA_SUAVE, wrap='none')
        self.traza.pack(fill='both', expand=True, padx=4, pady=(0, 4))

    # ================================================================ carga y refresco
    def cargar(self, sesion):
        self.sesion = sesion
        self._por_que_visible = False
        self.refrescar()

    def refrescar(self):
        s = self.sesion
        if s is None:
            return
        d = s.datos
        partes = [f'Consulta #{s.consulta_id}' if s.consulta_id else 'Consulta']
        if d.get('equipo'):
            partes.append(f'equipo {d["equipo"]}')
        if d.get('ubicacion'):
            partes.append(d['ubicacion'])
        partes.append(f'{s.motor.preguntas_respondidas} pregunta(s) respondida(s)')
        self.encabezado.subtitulo.configure(text='  ·  '.join(partes))
        self._pintar_pregunta()
        self._pintar_respuestas()
        self._pintar_razonamiento()

    def _pintar_pregunta(self):
        s, caja = self.sesion, self.tarjeta_pregunta
        _limpiar(caja)
        q = s.pregunta_actual

        if s.motivo_conclusion:
            aviso = ctk.CTkFrame(caja, fg_color=tema.AVISO_FONDO, corner_radius=10)
            aviso.pack(fill='x', padx=16, pady=(16, 0))
            ctk.CTkLabel(aviso, text='El motor recomienda concluir', font=tema.fuente(13, 'bold'),
                         text_color=tema.AVISO, anchor='w').pack(fill='x', padx=14, pady=(10, 0))
            Etiqueta(aviso, text=s.motivo_conclusion, font=tema.fuente(12), text_color=tema.TEXTO).pack(
                fill='x', padx=14)
            fila = ctk.CTkFrame(aviso, fg_color='transparent')
            fila.pack(fill='x', padx=14, pady=10)
            boton(fila, 'Ver diagnóstico', self.app.ver_resultado, width=160).pack(side='left')
            if q is not None:
                ctk.CTkLabel(fila, text='   o siga respondiendo para afinar el resultado.', font=tema.fuente(12),
                             text_color=tema.TEXTO_SUAVE).pack(side='left')

        if q is None:
            ctk.CTkLabel(caja, text='No quedan preguntas pendientes en el diagnóstico diferencial.',
                         font=tema.fuente(16, 'bold'), text_color=tema.TEXTO).pack(padx=18, pady=24)
            return

        ev = q.evidencia
        cab = ctk.CTkFrame(caja, fg_color='transparent')
        cab.pack(fill='x', padx=18, pady=(16, 6))
        Insignia(cab, f'Pregunta {q.numero}').pack(side='left')
        Insignia(cab, 'Síntoma' if ev.es_sintoma else 'Prueba de diagnóstico', fondo=tema.TARJETA_SUAVE,
                 color=tema.TEXTO_SUAVE).pack(side='left', padx=6)
        Insignia(cab, ev.codigo, fondo=tema.TARJETA_SUAVE, color=tema.TEXTO_SUAVE).pack(side='left')
        Insignia(cab, f'aporta {q.ganancia:.2f} bits', fondo=tema.TARJETA_SUAVE, color=tema.TEXTO_SUAVE).pack(
            side='right')

        Etiqueta(caja, text=ev.pregunta, font=tema.fuente(21, 'bold'), text_color=tema.TEXTO).pack(
            fill='x', padx=18, pady=(6, 2))
        ayuda = ('Responda según lo que reporta el usuario o lo que usted observa.' if ev.es_sintoma else
                 'Ejecute la prueba y responda según su resultado.')
        ctk.CTkLabel(caja, text=ayuda + '  Atajos de teclado: 1 a 5.', font=tema.fuente(12),
                     text_color=tema.TEXTO_SUAVE, anchor='w').pack(fill='x', padx=18)

        fila = ctk.CTkFrame(caja, fg_color='transparent')
        fila.pack(fill='x', padx=14, pady=(14, 6))
        for i, op in enumerate(s.opciones):
            fila.grid_columnconfigure(i, weight=1, uniform='r')
            ctk.CTkButton(fila, text=_dos_lineas(op.etiqueta), command=lambda o=op: self._responder(o),
                          height=58, width=60, corner_radius=10, fg_color=op.color, hover_color=op.color,
                          text_color='#FFFFFF', font=tema.fuente(12, 'bold')).grid(row=0, column=i, sticky='ew',
                                                                                  padx=4)

        pie = ctk.CTkFrame(caja, fg_color='transparent')
        pie.pack(fill='x', padx=18, pady=(4, 14))
        texto = 'Ocultar explicación' if self._por_que_visible else '¿Por qué pregunta esto?'
        ctk.CTkButton(pie, text=texto, command=self._alternar_por_que, fg_color='transparent',
                      hover_color=tema.ACENTO_SUAVE, text_color=tema.ACENTO, font=tema.fuente(12, 'bold'),
                      width=10, height=28, anchor='w').pack(side='left')
        if self._por_que_visible:
            caja_pq = ctk.CTkTextbox(caja, height=170, font=tema.fuente(12), fg_color=tema.TARJETA_SUAVE,
                                     wrap='word', border_width=0)
            caja_pq.pack(fill='x', padx=18, pady=(0, 16))
            caja_pq.insert('end', '\n'.join(s.explicar_pregunta()))
            caja_pq.configure(state='disabled')

    def _pintar_respuestas(self):
        s, lista = self.sesion, self.lista_respuestas
        _limpiar(lista)
        etiquetas = [o.etiqueta for o in s.opciones]
        por_codigo = {o.codigo: o for o in s.opciones}
        for r in reversed(s.motor.memoria.respuestas_en_orden()):
            fila = ctk.CTkFrame(lista, fg_color=tema.TARJETA_SUAVE, corner_radius=10)
            fila.pack(fill='x', padx=4, pady=3)
            op = por_codigo[r.escala_codigo]
            ctk.CTkLabel(fila, text=f'{r.orden:>2}', width=26, font=tema.fuente(12, 'bold'),
                         text_color=tema.TEXTO_SUAVE).pack(side='left', padx=(10, 0))
            tipo = 'síntoma inicial' if r.origen == 'SINTOMA_INICIAL' else r.evidencia.codigo
            ctk.CTkLabel(fila, text=tipo, width=96, font=tema.fuente(11), text_color=tema.TEXTO_SUAVE,
                         anchor='w').pack(side='left', padx=6)
            menu = ctk.CTkOptionMenu(fila, values=etiquetas, width=160, height=30, font=tema.fuente(12, 'bold'),
                                     fg_color=op.color, button_color=op.color, button_hover_color=op.color,
                                     text_color='#FFFFFF', dropdown_font=tema.fuente(12),
                                     command=lambda et, ev=r.evidencia: self._corregir(ev, et))
            menu.set(op.etiqueta)
            menu.pack(side='right', padx=8, pady=6)
            texto = r.evidencia.enunciado[0].upper() + r.evidencia.enunciado[1:]
            Etiqueta(fila, text=texto, font=tema.fuente(12), text_color=tema.TEXTO).pack(
                side='left', fill='x', expand=True, pady=6)

    def _pintar_razonamiento(self):
        s = self.sesion
        top = s.resultado()
        n = len(s.motor.memoria.hipotesis)
        self.etiqueta_top.configure(
            text=f'{n} hipótesis compiten en el diagnóstico diferencial; se muestran las {len(top)} de mayor peso.')
        self.grafico.mostrar(top)
        self.evolucion.mostrar(s.motor.pasos, top)
        traza = s.motor.traza_consultas
        filas = sum(t[2] for t in traza)
        self.etiqueta_traza.configure(
            text=f'El motor no carga toda la base: hizo {len(traza)} consultas granulares sucesivas '
                 f'({filas} filas) y tiene en memoria {len(s.motor.memoria.granulos)} de las 88 reglas.')
        self.traza.configure(state='normal')
        self.traza.delete('1.0', 'end')
        paso_ant = None
        for paso, desc, f in traza:
            if paso != paso_ant:
                titulo = 'Síntomas iniciales' if paso == 0 else f'Respuesta {paso}'
                self.traza.insert('end', f'\n── {titulo} ' + '─' * 40 + '\n')
                paso_ant = paso
            self.traza.insert('end', f'  {desc:<52} {f:>3} fila(s)\n')
        self.traza.configure(state='disabled')
        self.traza.see('end')

    # ================================================================ acciones
    def _responder(self, opcion):
        q = self.sesion.pregunta_actual if self.sesion else None
        if q is None:
            return
        self._por_que_visible = False
        self.sesion.responder(q.evidencia, opcion)
        self.refrescar()

    def _corregir(self, evidencia, etiqueta):
        op = next(o for o in self.sesion.opciones if o.etiqueta == etiqueta)
        self.sesion.responder(evidencia, op)
        self.refrescar()

    def responder_atajo(self, indice):
        if self.sesion and self.sesion.pregunta_actual and 0 <= indice < len(self.sesion.opciones):
            self._responder(self.sesion.opciones[indice])

    def _alternar_por_que(self):
        self._por_que_visible = not self._por_que_visible
        self._pintar_pregunta()

    def al_cambiar_tema(self):
        self.grafico.redibujar()
        self.evolucion.redibujar()
