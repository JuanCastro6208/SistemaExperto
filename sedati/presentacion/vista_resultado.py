"""Vista del diagnóstico: las 5 hipótesis con su peso probabilístico y la explicación de cada una."""
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import tema
from .componentes import Encabezado, Etiqueta, Insignia, Tarjeta, VistaRegla, boton
from .graficos import GraficoProbabilidades


def _limpiar(frame):
    for w in frame.winfo_children():
        w.destroy()


class VistaResultado(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        self.app = app
        self.sesion = None
        self.resultados = []
        self.seleccion = 0

        self.encabezado = Encabezado(self, 'Diagnóstico', '')
        self.encabezado.pack(fill='x', pady=(0, 14))
        self.barra = self.encabezado.acciones

        self.lider = Tarjeta(self)
        self.lider.pack(fill='x')

        cuerpo = ctk.CTkFrame(self, fg_color='transparent')
        cuerpo.pack(fill='both', expand=True, pady=(14, 0))
        cuerpo.grid_columnconfigure(0, weight=9, uniform='c')
        cuerpo.grid_columnconfigure(1, weight=11, uniform='c')
        cuerpo.grid_rowconfigure(0, weight=1)

        izq = Tarjeta(cuerpo, 'Las 5 hipótesis más probables',
                      'Peso probabilístico normalizado sobre el diagnóstico diferencial. Seleccione una para ver '
                      'cómo se llegó a ella.')
        izq.grid(row=0, column=0, sticky='nsew', padx=(0, 14))
        self.grafico = GraficoProbabilidades(izq, alto=2.7)
        self.grafico.pack(fill='both', expand=True, padx=8, pady=(6, 0))
        self.lista = ctk.CTkFrame(izq, fg_color='transparent')
        self.lista.pack(fill='x', padx=12, pady=(0, 12))

        self.detalle = Tarjeta(cuerpo, '¿Cómo se llegó a esta conclusión?')
        self.detalle.grid(row=0, column=1, sticky='nsew')
        self.detalle_resumen = Etiqueta(self.detalle, text='', font=tema.fuente(12), text_color=tema.TEXTO_SUAVE)
        self.detalle_resumen.pack(fill='x', padx=18, pady=(2, 6))
        self.detalle_reglas = ctk.CTkScrollableFrame(self.detalle, fg_color='transparent')
        self.detalle_reglas.pack(fill='both', expand=True, padx=8, pady=(0, 10))

    # ================================================================ carga
    def cargar(self, sesion):
        self.sesion = sesion
        self.resultados = sesion.resultado()
        self.seleccion = 0
        s = sesion
        partes = [f'Consulta #{s.consulta_id}' if s.consulta_id else 'Consulta',
                  f'{s.motor.preguntas_respondidas} pregunta(s)',
                  f'{len(s.motor.memoria.respuestas)} respuesta(s) registrada(s)']
        if s.datos.get('equipo'):
            partes.insert(1, f'equipo {s.datos["equipo"]}')
        partes.append('consulta cerrada y guardada' if s.finalizada else 'consulta abierta')
        self.encabezado.subtitulo.configure(text='  ·  '.join(partes))

        _limpiar(self.barra)
        boton(self.barra, 'Exportar informe', self._exportar, primario=False, width=150).pack(side='right')
        if s.finalizada:
            boton(self.barra, 'Nuevo diagnóstico', lambda: self.app.mostrar('inicio'), width=170).pack(
                side='right', padx=8)
        else:
            boton(self.barra, 'Guardar y cerrar consulta', self._finalizar, width=210).pack(side='right', padx=8)
            boton(self.barra, '← Seguir preguntando', lambda: self.app.mostrar('consulta'), primario=False,
                  width=180).pack(side='right')

        self._pintar_lider()
        self.grafico.mostrar(self.resultados)
        self._pintar_lista()
        self._pintar_detalle()

    def _pintar_lider(self):
        _limpiar(self.lider)
        if not self.resultados:
            return
        r = self.resultados[0]
        fila = ctk.CTkFrame(self.lider, fg_color='transparent')
        fila.pack(fill='x', padx=20, pady=16)
        pct = ctk.CTkFrame(fila, fg_color=tema.ACENTO_SUAVE, corner_radius=14, width=150, height=96)
        pct.pack(side='left')
        pct.pack_propagate(False)
        ctk.CTkLabel(pct, text=f'{r.probabilidad:.0%}', font=tema.fuente(34, 'bold'), text_color=tema.ACENTO).pack(
            pady=(12, 0))
        ctk.CTkLabel(pct, text='peso probabilístico', font=tema.fuente(11), text_color=tema.ACENTO).pack()
        txt = ctk.CTkFrame(fila, fg_color='transparent')
        txt.pack(side='left', fill='both', expand=True, padx=18)
        cab = ctk.CTkFrame(txt, fg_color='transparent')
        cab.pack(fill='x')
        Insignia(cab, 'Hipótesis más probable').pack(side='left')
        Insignia(cab, f'{r.hipotesis.codigo} · {r.hipotesis.dominio}', fondo=tema.TARJETA_SUAVE,
                 color=tema.TEXTO_SUAVE).pack(side='left', padx=6)
        Insignia(cab, f'FC combinado {r.certeza:+.2f}', fondo=tema.TARJETA_SUAVE, color=tema.TEXTO_SUAVE).pack(
            side='left')
        ctk.CTkLabel(txt, text=r.hipotesis.nombre, font=tema.fuente(22, 'bold'), text_color=tema.TEXTO,
                     anchor='w').pack(fill='x', pady=(6, 0))
        if r.principal:
            g = r.principal.granulo
            Etiqueta(txt, text=f'Conclusión ({g.regla}): {g.conclusion}.', font=tema.fuente(13),
                     text_color=tema.TEXTO).pack(fill='x')
            Etiqueta(txt, text=f'Acción recomendada: {g.accion}', font=tema.fuente(13, 'bold'),
                     text_color=tema.EXITO).pack(fill='x', pady=(2, 0))
            if g.riesgo_perdida_datos:
                Etiqueta(txt, text='⚠ Esta acción puede ocasionar pérdida de información: respalde antes de aplicarla.',
                         font=tema.fuente(12, 'bold'), text_color=tema.PELIGRO).pack(fill='x')

    def _pintar_lista(self):
        _limpiar(self.lista)
        for i, r in enumerate(self.resultados):
            activo = i == self.seleccion
            fila = ctk.CTkButton(
                self.lista, anchor='w', height=40, corner_radius=10, border_width=1,
                fg_color=tema.ACENTO_SUAVE if activo else tema.TARJETA_SUAVE,
                hover_color=tema.ACENTO_SUAVE, border_color=tema.ACENTO if activo else tema.BORDE,
                text_color=tema.TEXTO, font=tema.fuente(12, 'bold' if activo else 'normal'),
                text=f'  {r.posicion}.  {r.hipotesis.nombre}      {r.probabilidad:.1%}  ·  FC {r.certeza:+.2f}',
                command=lambda k=i: self._seleccionar(k))
            fila.pack(fill='x', pady=3)

    def _pintar_detalle(self):
        _limpiar(self.detalle_reglas)
        if not self.resultados:
            return
        r = self.resultados[self.seleccion]
        h = r.hipotesis
        self.detalle_resumen.configure(
            text=f'{h.codigo} · {h.nombre}.  Probabilidad previa {h.probabilidad_previa:.1%} (global) → '
                 f'{r.previa_contextual:.1%} según los síntomas → factor de certeza combinado {r.certeza:+.3f} → peso '
                 f'{r.probabilidad:.1%}.  Cada regla aporta: aplicabilidad del síntoma de entrada × grado de '
                 f'cumplimiento de sus condiciones And × FC del experto. Los aportes positivos se combinan con la '
                 f'regla de MYCIN y el peso es previa · e^({self.sesion.motor.parametros.beta:g}·FC), normalizado.')
        for ev in r.evaluaciones:
            VistaRegla(self.detalle_reglas, ev.granulo, evaluacion=ev).pack(fill='x', padx=6, pady=5)
            ctk.CTkLabel(self.detalle_reglas,
                         text=f'aplicabilidad {ev.aplicabilidad:.2f}  ×  grado {ev.grado:+.2f}  ({ev.cumplidas} de '
                              f'{ev.total} condiciones confirmadas, {ev.negadas} negadas)  ×  FC '
                              f'{ev.granulo.factor_certeza:.2f}  =  aporte {ev.certeza:+.3f}',
                         font=tema.fuente(11), text_color=tema.TEXTO_SUAVE, anchor='w').pack(fill='x', padx=14)

    # ================================================================ acciones
    def _seleccionar(self, k):
        self.seleccion = k
        self._pintar_lista()
        self._pintar_detalle()

    def _finalizar(self):
        self.app.finalizar_consulta()

    def _exportar(self):
        nombre = f'informe_consulta_{self.sesion.consulta_id or "sin_guardar"}.txt'
        ruta = filedialog.asksaveasfilename(parent=self, title='Exportar informe', initialfile=nombre,
                                            defaultextension='.txt', filetypes=[('Texto', '*.txt')])
        if ruta:
            with open(ruta, 'w', encoding='utf-8') as f:
                f.write(self.sesion.informe())
            messagebox.showinfo('SEDATI', f'Informe guardado en:\n{ruta}', parent=self)

    def al_cambiar_tema(self):
        self.grafico.redibujar()
