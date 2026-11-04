"""Vista «Nuevo diagnóstico»: datos del equipo y síntomas iniciales."""
import customtkinter as ctk

from . import tema
from .componentes import Encabezado, Etiqueta, Tarjeta, boton


class VistaInicio(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        self.app = app
        self.marcados = {}       # evidencia_id -> BooleanVar
        self.textos = {}         # evidencia_id -> enunciado

        Encabezado(self, 'Nuevo diagnóstico',
                   'Registre el equipo y marque los síntomas que observa. A partir de ellos el motor de inferencia '
                   'consulta la base de conocimiento y hace solo las preguntas necesarias.').pack(fill='x', pady=(0, 14))

        cuerpo = ctk.CTkFrame(self, fg_color='transparent')
        cuerpo.pack(fill='both', expand=True)
        cuerpo.grid_columnconfigure(0, weight=1, uniform='c')
        cuerpo.grid_columnconfigure(1, weight=3, uniform='c')
        cuerpo.grid_rowconfigure(0, weight=1)

        # ---------------------------------------------------------------- datos del equipo
        izq = Tarjeta(cuerpo, 'Datos del equipo', 'Opcionales: quedan en el registro de la consulta.')
        izq.grid(row=0, column=0, sticky='nsew', padx=(0, 14))
        self.equipo = self._campo(izq, 'Código de inventario', 'Ej.: PC-SALA2-014')
        self.ubicacion = self._campo(izq, 'Ubicación', 'Ej.: Sala de cómputo 2')
        ctk.CTkLabel(izq, text='Descripción de la falla', font=tema.fuente(12, 'bold'), text_color=tema.TEXTO,
                     anchor='w').pack(fill='x', padx=18, pady=(12, 4))
        self.descripcion = ctk.CTkTextbox(izq, height=120, font=tema.fuente(12), border_width=1,
                                          border_color=tema.BORDE, fg_color=tema.TARJETA_SUAVE, wrap='word')
        self.descripcion.pack(fill='x', padx=18)

        ayuda = Tarjeta(izq, fg_color=tema.ACENTO_SUAVE, border_width=0)
        ayuda.pack(fill='x', padx=18, pady=18, side='bottom')
        ctk.CTkLabel(ayuda, text='¿Cómo funciona?', font=tema.fuente(12, 'bold'), text_color=tema.ACENTO,
                     anchor='w').pack(fill='x', padx=14, pady=(10, 2))
        Etiqueta(ayuda, font=tema.fuente(11), text_color=tema.TEXTO,
                 text='1. Marque uno o más síntomas.\n'
                          '2. Responda cada pregunta con el grado de certeza que tenga (no solo sí o no).\n'
                          '3. El motor elige la siguiente pregunta según la información que aporta.\n'
                          '4. Al final entrega las 5 hipótesis más probables con su peso, la regla que las '
                          'sostiene y la acción recomendada.').pack(fill='x', padx=14, pady=(0, 12))

        # ---------------------------------------------------------------- síntomas
        der = Tarjeta(cuerpo, 'Síntomas observados',
                      'Agrupados por categoría del árbol de decisión. Puede marcar síntomas de varias categorías.')
        der.grid(row=0, column=1, sticky='nsew')
        self.lista = ctk.CTkScrollableFrame(der, fg_color='transparent')
        self.lista.pack(fill='both', expand=True, padx=8, pady=(8, 0))
        self.lista.grid_columnconfigure((0, 1), weight=1, uniform='s')

        pie = ctk.CTkFrame(der, fg_color='transparent')
        pie.pack(fill='x', padx=18, pady=14)
        self.resumen = Etiqueta(pie, text='', font=tema.fuente(12), text_color=tema.TEXTO_SUAVE)
        self.resumen.pack(side='left', fill='x', expand=True)
        self.boton_iniciar = boton(pie, 'Iniciar diagnóstico  →', self._iniciar, width=200, height=42)
        self.boton_iniciar.pack(side='right')
        boton(pie, 'Limpiar', self.limpiar, primario=False, width=100, height=42).pack(side='right', padx=8)

        self._cargar_sintomas()
        self._actualizar_resumen()

    def _campo(self, master, etiqueta, ejemplo):
        ctk.CTkLabel(master, text=etiqueta, font=tema.fuente(12, 'bold'), text_color=tema.TEXTO,
                     anchor='w').pack(fill='x', padx=18, pady=(12, 4))
        e = ctk.CTkEntry(master, placeholder_text=ejemplo, height=36, font=tema.fuente(12), border_color=tema.BORDE,
                         fg_color=tema.TARJETA_SUAVE)
        e.pack(fill='x', padx=18)
        return e

    def _cargar_sintomas(self):
        servicio = self.app.diagnostico
        vistos = set()
        for i, cat in enumerate(servicio.categorias()):
            caja = ctk.CTkFrame(self.lista, fg_color=tema.TARJETA_SUAVE, corner_radius=12)
            caja.grid(row=i // 2, column=i % 2, sticky='nsew', padx=8, pady=8)
            cab = ctk.CTkFrame(caja, fg_color='transparent')
            cab.pack(fill='x', padx=14, pady=(12, 6))
            ctk.CTkLabel(cab, text=cat['codigo'], width=28, height=28, corner_radius=8, fg_color=tema.ACENTO,
                         text_color='#FFFFFF', font=tema.fuente(13, 'bold')).pack(side='left')
            ctk.CTkLabel(cab, text='  ' + cat['nombre'], font=tema.fuente(13, 'bold'), text_color=tema.TEXTO,
                         anchor='w').pack(side='left')
            ctk.CTkLabel(cab, text=f"{cat['reglas']} reglas", font=tema.fuente(11),
                         text_color=tema.TEXTO_SUAVE).pack(side='right')
            for s in servicio.sintomas(cat['codigo']):
                if s['id'] in vistos:
                    continue
                vistos.add(s['id'])
                var = ctk.BooleanVar(value=False)
                texto = s['enunciado'][0].upper() + s['enunciado'][1:]
                self.marcados[s['id']] = var
                self.textos[s['id']] = texto
                ctk.CTkCheckBox(caja, text=texto, variable=var, command=self._actualizar_resumen,
                                font=tema.fuente(12), text_color=tema.TEXTO, checkbox_width=20, checkbox_height=20,
                                corner_radius=6, border_width=2).pack(fill='x', padx=16, pady=4, anchor='w')
            ctk.CTkFrame(caja, height=6, fg_color='transparent').pack()

    def seleccionados(self):
        return [i for i, v in self.marcados.items() if v.get()]

    def _actualizar_resumen(self):
        sel = self.seleccionados()
        if sel:
            self.resumen.configure(text=f'{len(sel)} síntoma(s): ' + '; '.join(self.textos[i] for i in sel),
                                   text_color=tema.TEXTO)
            self.boton_iniciar.configure(state='normal')
        else:
            self.resumen.configure(text='Marque al menos un síntoma para iniciar.', text_color=tema.TEXTO_SUAVE)
            self.boton_iniciar.configure(state='disabled')

    def limpiar(self):
        for v in self.marcados.values():
            v.set(False)
        for e in (self.equipo, self.ubicacion):
            e.delete(0, 'end')
        self.descripcion.delete('1.0', 'end')
        self._actualizar_resumen()

    def _iniciar(self):
        sel = self.seleccionados()
        if not sel:
            return
        self.app.iniciar_consulta(sel, self.equipo.get().strip(), self.ubicacion.get().strip(),
                                  self.descripcion.get('1.0', 'end').strip())

    def al_cambiar_tema(self):
        pass
