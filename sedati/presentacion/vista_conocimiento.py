"""Vista para explorar la base de conocimiento: hipótesis, sus gránulos y las evidencias."""
import customtkinter as ctk

from . import tema
from .componentes import Encabezado, Etiqueta, Insignia, Pestanas, Tabla, Tarjeta, VistaRegla


def _limpiar(frame):
    for w in frame.winfo_children():
        w.destroy()


class VistaConocimiento(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        self.app = app
        self.servicio = app.conocimiento
        self.hipotesis = self.servicio.hipotesis()
        self.botones = {}
        self.actual = None

        Encabezado(self, 'Base de conocimiento',
                   'Conocimiento del experto guardado en tres tablas: hipótesis, evidencia y gránulo '
                   '(una fila por cada condición If / And de una regla).').pack(fill='x', pady=(0, 14))

        est = self.servicio.estadisticas()
        tiles = ctk.CTkFrame(self, fg_color='transparent')
        tiles.pack(fill='x')
        for i, (valor, texto) in enumerate([(est['hipotesis'], 'hipótesis'), (est['evidencias'], 'evidencias'),
                                            (est['reglas'], 'reglas If / And / Then'),
                                            (est['filas_granulo'], 'filas de gránulo (condiciones)')]):
            tiles.grid_columnconfigure(i, weight=1, uniform='t')
            t = Tarjeta(tiles)
            t.grid(row=0, column=i, sticky='ew', padx=(0 if i == 0 else 7, 0 if i == 3 else 7))
            ctk.CTkLabel(t, text=str(valor), font=tema.fuente(26, 'bold'), text_color=tema.ACENTO,
                         anchor='w').pack(fill='x', padx=18, pady=(10, 0))
            ctk.CTkLabel(t, text=texto, font=tema.fuente(12), text_color=tema.TEXTO_SUAVE, anchor='w').pack(
                fill='x', padx=18, pady=(0, 10))

        pestanas = Pestanas(self, ['Hipótesis y gránulos', 'Evidencias'])
        pestanas.pack(fill='both', expand=True, pady=(14, 0))
        t1 = pestanas.pagina('Hipótesis y gránulos')
        t2 = pestanas.pagina('Evidencias')

        # ---------------------------------------------------------------- hipótesis y gránulos
        t1.grid_columnconfigure(0, weight=2, uniform='k')
        t1.grid_columnconfigure(1, weight=5, uniform='k')
        t1.grid_rowconfigure(1, weight=1)
        self.buscar = ctk.CTkEntry(t1, placeholder_text='Buscar hipótesis…', height=34, font=tema.fuente(12),
                                   border_color=tema.BORDE, fg_color=tema.TARJETA_SUAVE)
        self.buscar.grid(row=0, column=0, sticky='ew', padx=(4, 10), pady=(0, 8))
        self.buscar.bind('<KeyRelease>', lambda _e: self._filtrar())
        self.lista = ctk.CTkScrollableFrame(t1, fg_color='transparent')
        self.lista.grid(row=1, column=0, sticky='nsew', padx=(0, 10))
        self.titulo = ctk.CTkLabel(t1, text='', font=tema.fuente(17, 'bold'), text_color=tema.TEXTO, anchor='w')
        self.titulo.grid(row=0, column=1, sticky='ew')
        self.reglas = ctk.CTkScrollableFrame(t1, fg_color='transparent')
        self.reglas.grid(row=1, column=1, sticky='nsew')
        for h in self.hipotesis:
            self.botones[h['id']] = self._fila_hipotesis(h)
        self._filtrar()
        if self.hipotesis:
            self._mostrar(self.hipotesis[0])

        # ---------------------------------------------------------------- evidencias
        ctk.CTkLabel(t2, text='Las evidencias con la misma «variable» describen una misma observación: al responder '
                              'una, el motor deduce las demás según su polaridad (+1 la afirma, −1 la niega).',
                     font=tema.fuente(12), text_color=tema.TEXTO_SUAVE, anchor='w', justify='left',
                     wraplength=1100).pack(fill='x', padx=4, pady=(0, 8))
        tabla = Tabla(t2, [('codigo', 'Código', 70, False), ('tipo', 'Tipo', 80, False),
                           ('enunciado', 'Enunciado', 520, True), ('variable', 'Variable', 230, False),
                           ('pol', 'Polaridad', 80, False), ('reglas', 'Reglas', 60, False)], alto=18)
        tabla.pack(fill='both', expand=True, padx=4, pady=(0, 4))
        tabla.cargar((e['id'], (e['codigo'], e['tipo'].capitalize(), e['enunciado'], e['variable'] or '',
                                f"{e['polaridad']:+d}" if e['variable'] else '', e['reglas']))
                     for e in self.servicio.evidencias())

    def _fila_hipotesis(self, h):
        """Fila seleccionable: código y nombre arriba, dominio, reglas y previa abajo."""
        fila = ctk.CTkFrame(self.lista, corner_radius=10, border_width=1)
        Etiqueta(fila, text=f"{h['codigo']}  ·  {h['nombre']}", font=tema.fuente(12, 'bold'),
                 text_color=tema.TEXTO).pack(fill='x', padx=12, pady=(8, 0))
        ctk.CTkLabel(fila, text=f"{h['dominio']} · {h['reglas']} regla(s) · previa {h['probabilidad_previa']:.1%}",
                     font=tema.fuente(11), text_color=tema.TEXTO_SUAVE, anchor='w').pack(fill='x', padx=12,
                                                                                        pady=(0, 8))
        for w in [fila] + fila.winfo_children():
            w.bind('<Button-1>', lambda _e, x=h: self._mostrar(x))
        return fila

    def _estilo_boton(self, b, activo):
        b.configure(fg_color=tema.ACENTO_SUAVE if activo else tema.TARJETA_SUAVE,
                    border_color=tema.ACENTO if activo else tema.BORDE)

    def _filtrar(self):
        texto = self.buscar.get().strip().lower()
        for h in self.hipotesis:
            b = self.botones[h['id']]
            b.pack_forget()
            if not texto or texto in h['nombre'].lower() or texto in h['codigo'].lower():
                b.pack(fill='x', padx=4, pady=3)
            self._estilo_boton(b, self.actual == h['id'])

    def _mostrar(self, h):
        self.actual = h['id']
        for hid, b in self.botones.items():
            self._estilo_boton(b, hid == h['id'])
        self.titulo.configure(text=f"{h['codigo']} · {h['nombre']}")
        _limpiar(self.reglas)
        info = ctk.CTkFrame(self.reglas, fg_color='transparent')
        info.pack(fill='x', padx=6, pady=(0, 6))
        Insignia(info, h['dominio']).pack(side='left')
        Insignia(info, f"probabilidad previa {h['probabilidad_previa']:.2%}", fondo=tema.TARJETA_SUAVE,
                 color=tema.TEXTO_SUAVE).pack(side='left', padx=6)
        Insignia(info, f"{h['reglas']} gránulo(s)", fondo=tema.TARJETA_SUAVE, color=tema.TEXTO_SUAVE).pack(side='left')
        for g in self.servicio.granulos_de(h['id']):
            VistaRegla(self.reglas, g).pack(fill='x', padx=6, pady=5)

    def al_cambiar_tema(self):
        pass
