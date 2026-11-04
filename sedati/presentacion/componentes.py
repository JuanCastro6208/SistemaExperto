"""Componentes visuales reutilizables."""
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from . import tema


class Etiqueta(ctk.CTkLabel):
    """Etiqueta de varias líneas que ajusta el ancho de línea al espacio que le asigna su contenedor."""

    def __init__(self, master, **kw):
        kw.setdefault('anchor', 'w')
        kw.setdefault('justify', 'left')
        super().__init__(master, **kw)
        self._ancho = None
        tk.Misc.bind(self, '<Configure>', self._ajustar, add='+')

    def _ajustar(self, evento):
        escala = self._get_widget_scaling() if hasattr(self, '_get_widget_scaling') else 1.0
        ancho = max(int(evento.width / escala) - 8, 60)
        if self._ancho is None or abs(ancho - self._ancho) > 3:
            self._ancho = ancho
            self.configure(wraplength=ancho)


class Tarjeta(ctk.CTkFrame):
    def __init__(self, master, titulo=None, subtitulo=None, **kw):
        kw.setdefault('fg_color', tema.TARJETA)
        kw.setdefault('corner_radius', 14)
        kw.setdefault('border_width', 1)
        kw.setdefault('border_color', tema.BORDE)
        super().__init__(master, **kw)
        self.cuerpo = self
        if titulo:
            ctk.CTkLabel(self, text=titulo, font=tema.fuente(15, 'bold'), text_color=tema.TEXTO,
                         anchor='w').pack(fill='x', padx=18, pady=(14, 0))
        if subtitulo:
            Etiqueta(self, text=subtitulo, font=tema.fuente(12), text_color=tema.TEXTO_SUAVE).pack(
                fill='x', padx=18, pady=(2, 0))


class Pestanas(ctk.CTkFrame):
    """Tarjeta con pestañas (selector segmentado + páginas apiladas)."""

    def __init__(self, master, nombres, **kw):
        kw.setdefault('fg_color', tema.TARJETA)
        kw.setdefault('corner_radius', 14)
        kw.setdefault('border_width', 1)
        kw.setdefault('border_color', tema.BORDE)
        super().__init__(master, **kw)
        self.selector = ctk.CTkSegmentedButton(self, values=list(nombres), command=self.mostrar,
                                               font=tema.fuente(12, 'bold'), height=32,
                                               selected_color=tema.ACENTO, selected_hover_color=tema.ACENTO_HOVER,
                                               unselected_color=tema.TARJETA_SUAVE,
                                               unselected_hover_color=tema.BORDE, fg_color=tema.TARJETA_SUAVE,
                                               text_color=(tema.TEXTO[0], tema.TEXTO[1]))
        self.selector.pack(anchor='w', padx=14, pady=(14, 8))
        zona = ctk.CTkFrame(self, fg_color='transparent')
        zona.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        zona.grid_columnconfigure(0, weight=1)
        zona.grid_rowconfigure(0, weight=1)
        self.paginas = {}
        for n in nombres:
            p = ctk.CTkFrame(zona, fg_color='transparent')
            p.grid(row=0, column=0, sticky='nsew')
            self.paginas[n] = p
        self.mostrar(nombres[0])

    def mostrar(self, nombre):
        self.selector.set(nombre)
        self.paginas[nombre].tkraise()

    def pagina(self, nombre):
        return self.paginas[nombre]


class Insignia(ctk.CTkLabel):
    def __init__(self, master, texto, fondo=tema.ACENTO_SUAVE, color=tema.ACENTO, **kw):
        super().__init__(master, text=f'  {texto}  ', fg_color=fondo, text_color=color, corner_radius=8,
                         font=tema.fuente(11, 'bold'), height=24, **kw)


class Encabezado(ctk.CTkFrame):
    def __init__(self, master, titulo, subtitulo=''):
        super().__init__(master, fg_color='transparent')
        self.titulo = ctk.CTkLabel(self, text=titulo, font=tema.fuente(24, 'bold'), text_color=tema.TEXTO,
                                   anchor='w')
        self.titulo.pack(fill='x')
        self.subtitulo = Etiqueta(self, text=subtitulo, font=tema.fuente(13), text_color=tema.TEXTO_SUAVE)
        self.subtitulo.pack(fill='x')
        # sin tamaño propio: vacío no debe tapar el subtítulo (CTkFrame mide 200×200 por defecto)
        self.acciones = ctk.CTkFrame(self, fg_color='transparent', width=1, height=1)
        self.acciones.place(relx=1.0, rely=0.0, anchor='ne')


def boton(master, texto, comando, primario=True, **kw):
    if primario:
        kw.setdefault('fg_color', tema.ACENTO)
        kw.setdefault('hover_color', tema.ACENTO_HOVER)
        kw.setdefault('text_color', '#FFFFFF')
    else:
        kw.setdefault('fg_color', tema.TARJETA_SUAVE)
        kw.setdefault('hover_color', tema.BORDE)
        kw.setdefault('text_color', tema.TEXTO)
        kw.setdefault('border_width', 1)
        kw.setdefault('border_color', tema.BORDE)
    kw.setdefault('height', 38)
    kw.setdefault('corner_radius', 10)
    kw.setdefault('font', tema.fuente(13, 'bold'))
    return ctk.CTkButton(master, text=texto, command=comando, **kw)


class VistaRegla(ctk.CTkFrame):
    """Muestra un gránulo como regla If / And / Then, marcando el estado de cada condición."""

    def __init__(self, master, granulo, hipotesis_nombre=None, evaluacion=None, **kw):
        kw.setdefault('fg_color', tema.TARJETA_SUAVE)
        kw.setdefault('corner_radius', 10)
        super().__init__(master, **kw)
        cab = ctk.CTkFrame(self, fg_color='transparent')
        cab.pack(fill='x', padx=12, pady=(10, 4))
        ctk.CTkLabel(cab, text=granulo.regla, font=tema.fuente(13, 'bold'), text_color=tema.ACENTO).pack(side='left')
        info = f'rama {granulo.rama_codigo} · {granulo.rama_nombre} · FC del experto {granulo.factor_certeza:.0%}'
        if hipotesis_nombre:
            info = f'{hipotesis_nombre} · ' + info
        ctk.CTkLabel(cab, text='   ' + info, font=tema.fuente(11), text_color=tema.TEXTO_SUAVE).pack(side='left')
        if evaluacion is not None:
            Insignia(cab, f'aporte {evaluacion.certeza:+.2f}').pack(side='right')
        estados = evaluacion.estados if evaluacion is not None else [None] * len(granulo.condiciones)
        for cond, est in zip(granulo.condiciones, estados):
            fila = ctk.CTkFrame(self, fg_color='transparent')
            fila.pack(fill='x', padx=12)
            marca, col = '•', tema.TEXTO_SUAVE
            if est is not None and est.valor is not None:
                if est.valor.valor > 0:
                    marca, col = '✔', tema.EXITO
                elif est.valor.valor < 0:
                    marca, col = '✖', tema.PELIGRO
                else:
                    marca, col = '?', tema.TEXTO_SUAVE
            elif est is not None:
                marca = '○'
            ctk.CTkLabel(fila, text=marca, width=18, font=tema.fuente(13, 'bold'), text_color=col).pack(side='left')
            ctk.CTkLabel(fila, text=f'{cond.conector:<4}', width=36, anchor='w', font=tema.fuente(12, 'bold'),
                         text_color=tema.ACENTO).pack(side='left')
            texto = cond.evidencia.enunciado
            if est is not None and est.valor is not None and est.valor.deducido:
                texto += f'   (deducido de {est.valor.origen.codigo})'
            Etiqueta(fila, text=texto, font=tema.fuente(12), text_color=tema.TEXTO).pack(
                side='left', fill='x', expand=True)
        fila = ctk.CTkFrame(self, fg_color='transparent')
        fila.pack(fill='x', padx=12, pady=(0, 4))
        ctk.CTkLabel(fila, text='', width=18).pack(side='left')
        ctk.CTkLabel(fila, text='Then', width=36, anchor='w', font=tema.fuente(12, 'bold'),
                     text_color=tema.EXITO).pack(side='left')
        Etiqueta(fila, text=granulo.conclusion, font=tema.fuente(12, 'bold'), text_color=tema.TEXTO).pack(
            side='left', fill='x', expand=True)
        Etiqueta(self, text=f'Acción: {granulo.accion}', font=tema.fuente(11), text_color=tema.TEXTO_SUAVE).pack(
            fill='x', padx=(66, 12), pady=(0, 2))
        if granulo.riesgo_perdida_datos:
            Etiqueta(self, text='⚠ La acción puede ocasionar pérdida de información: respalde antes.',
                     font=tema.fuente(11, 'bold'), text_color=tema.PELIGRO).pack(fill='x', padx=(66, 12), pady=(0, 2))
        ctk.CTkFrame(self, height=6, fg_color='transparent').pack()


def estilo_tablas(raiz):
    """Ajusta los ttk.Treeview al modo claro / oscuro."""
    st = ttk.Style(raiz)
    st.theme_use('clam')
    fondo, texto, borde = tema.color(tema.TARJETA), tema.color(tema.TEXTO), tema.color(tema.BORDE)
    cab = tema.color(tema.TARJETA_SUAVE)
    # ttk no se escala con el DPI como CustomTkinter: tamaños en píxeles multiplicados por la escala
    escala = ctk.ScalingTracker.get_widget_scaling(raiz)
    px = -round(13 * escala)
    st.configure('SEDATI.Treeview', background=fondo, fieldbackground=fondo, foreground=texto,
                 rowheight=round(32 * escala), borderwidth=0, font=(tema.FUENTE, px))
    st.configure('SEDATI.Treeview.Heading', background=cab, foreground=texto, relief='flat',
                 font=(tema.FUENTE, px, 'bold'), borderwidth=0, padding=(6, round(6 * escala)))
    st.map('SEDATI.Treeview', background=[('selected', tema.color(tema.ACENTO))],
           foreground=[('selected', '#FFFFFF')])
    st.map('SEDATI.Treeview.Heading', background=[('active', borde)])
    return st


class Tabla(ctk.CTkFrame):
    """Tabla con barra de desplazamiento basada en ttk.Treeview."""

    def __init__(self, master, columnas, alto=12, **kw):
        kw.setdefault('fg_color', tema.TARJETA)
        super().__init__(master, **kw)
        self.arbol = ttk.Treeview(self, columns=[c[0] for c in columnas], show='headings', height=alto,
                                  style='SEDATI.Treeview')
        escala = ctk.ScalingTracker.get_widget_scaling(self)
        for clave, titulo, ancho, estirar in columnas:
            self.arbol.heading(clave, text=titulo, anchor='w')
            self.arbol.column(clave, width=round(ancho * escala), minwidth=round(ancho * escala * 0.6),
                              stretch=estirar, anchor='w')
        barra = ctk.CTkScrollbar(self, command=self.arbol.yview)
        self.arbol.configure(yscrollcommand=barra.set)
        self.arbol.pack(side='left', fill='both', expand=True)
        barra.pack(side='right', fill='y')

    def cargar(self, filas):
        self.arbol.delete(*self.arbol.get_children())
        for iid, valores in filas:
            self.arbol.insert('', tk.END, iid=str(iid), values=valores)

    def seleccion(self):
        sel = self.arbol.selection()
        return sel[0] if sel else None
