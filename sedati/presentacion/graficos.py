"""Gráficas de matplotlib integradas en la interfaz."""
import textwrap

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from . import tema


class _Grafico(ctk.CTkFrame):
    def __init__(self, master, alto=3.0, **kw):
        kw.setdefault('fg_color', 'transparent')
        super().__init__(master, **kw)
        self.figura = Figure(figsize=(5.2, alto), dpi=100)
        self.ejes = self.figura.add_subplot(111)
        self.lienzo = FigureCanvasTkAgg(self.figura, master=self)
        self.lienzo.get_tk_widget().pack(fill='both', expand=True)
        self._datos = None

    def _colores_base(self):
        fondo = tema.color(tema.TARJETA)
        texto = tema.color(tema.TEXTO)
        suave = tema.color(tema.TEXTO_SUAVE)
        borde = tema.color(tema.BORDE)
        self.figura.set_facecolor(fondo)
        self.ejes.set_facecolor(fondo)
        for lado in ('top', 'right'):
            self.ejes.spines[lado].set_visible(False)
        for lado in ('left', 'bottom'):
            self.ejes.spines[lado].set_color(borde)
        self.ejes.tick_params(colors=suave, labelsize=9)
        get_tk = self.lienzo.get_tk_widget()
        get_tk.configure(background=fondo, highlightthickness=0)
        return texto, suave, borde

    def redibujar(self):
        if self._datos is not None:
            self.mostrar(*self._datos)


class GraficoProbabilidades(_Grafico):
    """Barras horizontales con el peso probabilístico de las hipótesis."""

    def mostrar(self, resultados, titulo=None):
        self._datos = (resultados, titulo)
        self.ejes.clear()
        texto, suave, borde = self._colores_base()
        if not resultados:
            self.lienzo.draw_idle()
            return
        nombres = ['\n'.join(textwrap.wrap(f'{r.hipotesis.nombre}', 30)) for r in resultados]
        valores = [r.probabilidad * 100 for r in resultados]
        posiciones = list(range(len(resultados)))[::-1]
        barras = self.ejes.barh(posiciones, valores, color=tema.SERIE[:len(resultados)], height=0.62)
        self.ejes.set_yticks(posiciones, nombres, color=texto, fontsize=9)
        self.ejes.set_xlim(0, 100)
        self.ejes.xaxis.set_major_formatter(lambda x, _: f'{x:.0f}%')
        self.ejes.grid(axis='x', color=borde, linewidth=0.6)
        self.ejes.set_axisbelow(True)
        for b, v, r in zip(barras, valores, resultados):
            etiqueta = f'{v:.1f}%   FC {r.certeza:+.2f}'
            y = b.get_y() + b.get_height() / 2
            if v > 62:   # no cabe a la derecha: va dentro de la barra
                self.ejes.text(v - 1.5, y, etiqueta, va='center', ha='right', fontsize=9, color='white',
                               fontweight='bold')
            else:
                self.ejes.text(v + 1.5, y, etiqueta, va='center', fontsize=9, color=texto, fontweight='bold')
        if titulo:
            self.ejes.set_title(titulo, color=texto, fontsize=10, loc='left')
        self.figura.tight_layout(pad=0.8)
        self.lienzo.draw_idle()


class GraficoEvolucion(_Grafico):
    """Evolución del peso probabilístico de las hipótesis líderes con cada respuesta."""

    def mostrar(self, pasos, resultados):
        self._datos = (pasos, resultados)
        self.ejes.clear()
        texto, suave, borde = self._colores_base()
        if not pasos or not resultados:
            self.lienzo.draw_idle()
            return
        x = [p.numero for p in pasos]
        for i, r in enumerate(resultados):
            y = [p.probabilidades.get(r.hipotesis.id, 0) * 100 for p in pasos]
            self.ejes.plot(x, y, marker='o', markersize=4, linewidth=2, color=tema.SERIE[i % len(tema.SERIE)],
                           label=r.hipotesis.codigo)
        self.ejes.set_ylim(0, 100)
        self.ejes.set_xlim(-0.2, max(x) + 0.2 if x else 1)
        self.ejes.set_xticks(x)
        self.ejes.yaxis.set_major_formatter(lambda v, _: f'{v:.0f}%')
        self.ejes.set_xlabel('respuesta', color=suave, fontsize=9)
        self.ejes.grid(color=borde, linewidth=0.6)
        ley = self.ejes.legend(loc='upper left', fontsize=8, frameon=False, ncols=5)
        for t in ley.get_texts():
            t.set_color(texto)
        self.figura.tight_layout(pad=0.8)
        self.lienzo.draw_idle()
