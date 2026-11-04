"""Vista con el historial de consultas guardadas."""
import customtkinter as ctk

from . import tema
from .componentes import Encabezado, Tabla, Tarjeta, boton


class VistaHistorial(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        self.app = app
        enc = Encabezado(self, 'Historial de consultas',
                         'Cada consulta guarda sus respuestas y las 5 hipótesis con su peso. Al abrir una, el motor '
                         'vuelve a razonar con las mismas respuestas para mostrar la explicación.')
        enc.pack(fill='x', pady=(0, 14))
        boton(enc.acciones, 'Abrir consulta', self._abrir, width=150).pack(side='right')
        boton(enc.acciones, 'Actualizar', self.cargar, primario=False, width=110).pack(side='right', padx=8)

        caja = Tarjeta(self)
        caja.pack(fill='both', expand=True)
        self.tabla = Tabla(caja, [('id', '#', 50, False), ('fecha', 'Fecha', 150, False),
                                  ('equipo', 'Equipo', 130, False), ('ubicacion', 'Ubicación', 170, False),
                                  ('estado', 'Estado', 100, False), ('preg', 'Preguntas', 80, False),
                                  ('hip', 'Hipótesis principal', 380, True), ('prob', 'Peso', 70, False)], alto=20)
        self.tabla.pack(fill='both', expand=True, padx=12, pady=12)
        self.tabla.arbol.bind('<Double-1>', lambda _e: self._abrir())
        self.vacio = ctk.CTkLabel(caja, text='', font=tema.fuente(12), text_color=tema.TEXTO_SUAVE)
        self.vacio.pack(pady=(0, 10))

    def cargar(self):
        filas = self.app.diagnostico.historial()
        self.tabla.cargar((c['id'], (c['id'], str(c['fecha_inicio'])[:16], c['equipo'] or '—', c['ubicacion'] or '—',
                                     c['estado'].replace('_', ' ').capitalize(), c['total_preguntas'],
                                     f"{c['hipotesis_codigo']} · {c['hipotesis_nombre']}" if c['hipotesis_codigo']
                                     else '—',
                                     f"{c['probabilidad']:.1%}" if c['probabilidad'] is not None else '—'))
                          for c in filas)
        self.vacio.configure(text='' if filas else 'Todavía no hay consultas registradas.')

    def _abrir(self):
        sel = self.tabla.seleccion()
        if sel:
            self.app.abrir_consulta_guardada(int(sel))

    def al_cambiar_tema(self):
        pass
