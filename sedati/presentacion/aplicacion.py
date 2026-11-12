"""Ventana principal de SEDATI."""
from tkinter import messagebox

import customtkinter as ctk

from . import tema
from .componentes import estilo_tablas
from .vista_conocimiento import VistaConocimiento
from .vista_consulta import VistaConsulta
from .vista_historial import VistaHistorial
from .vista_inicio import VistaInicio
from .vista_resultado import VistaResultado

NAVEGACION = [
    ('inicio', '＋   Nuevo diagnóstico'),
    ('consulta', '◉   Consulta en curso'),
    ('conocimiento', '▤   Base de conocimiento'),
    ('historial', '☰   Historial'),
]


class AplicacionSEDATI(ctk.CTk):
    def __init__(self, servicio_diagnostico, servicio_conocimiento, descripcion_bd):
        ctk.set_appearance_mode('light')
        ctk.set_default_color_theme('blue')
        super().__init__(fg_color=tema.FONDO)
        self.diagnostico = servicio_diagnostico
        self.conocimiento = servicio_conocimiento
        self.sesion = None
        self.vista_actual = None

        self.title('SEDATI · Sistema experto para el diagnóstico de incidentes')
        self.geometry('1440x880')
        self.minsize(1240, 760)
        estilo_tablas(self)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._construir_lateral(descripcion_bd)
        contenedor = ctk.CTkFrame(self, fg_color='transparent')
        contenedor.grid(row=0, column=1, sticky='nsew', padx=26, pady=22)
        contenedor.grid_columnconfigure(0, weight=1)
        contenedor.grid_rowconfigure(0, weight=1)
        self.vistas = {
            'inicio': VistaInicio(contenedor, self),
            'consulta': VistaConsulta(contenedor, self),
            'resultado': VistaResultado(contenedor, self),
            'conocimiento': VistaConocimiento(contenedor, self),
            'historial': VistaHistorial(contenedor, self),
        }
        for v in self.vistas.values():
            v.grid(row=0, column=0, sticky='nsew')

        self.bind('<Key>', self._tecla)
        self.protocol('WM_DELETE_WINDOW', self._cerrar)
        self.mostrar('inicio')

    # ================================================================ estructura
    def _construir_lateral(self, descripcion_bd):
        lat = ctk.CTkFrame(self, width=250, corner_radius=0, fg_color=tema.LATERAL, border_width=0)
        lat.grid(row=0, column=0, sticky='nsw')
        lat.grid_propagate(False)
        lat.pack_propagate(False)
        marca = ctk.CTkFrame(lat, fg_color='transparent')
        marca.pack(fill='x', padx=22, pady=(26, 6))
        ctk.CTkLabel(marca, text='SEDATI', font=tema.fuente(28, 'bold'), text_color=tema.ACENTO, anchor='w').pack(
            fill='x')
        ctk.CTkLabel(marca, text='Sistema experto para el diagnóstico\ny asistencia técnica de incidentes',
                     font=tema.fuente(11), text_color=tema.TEXTO_SUAVE, anchor='w', justify='left').pack(fill='x')
        ctk.CTkFrame(lat, height=1, fg_color=tema.BORDE).pack(fill='x', padx=18, pady=16)

        self.botones_nav = {}
        for clave, texto in NAVEGACION:
            b = ctk.CTkButton(lat, text=texto, anchor='w', height=42, corner_radius=10, font=tema.fuente(13, 'bold'),
                              command=lambda c=clave: self.mostrar(c))
            b.pack(fill='x', padx=14, pady=3)
            self.botones_nav[clave] = b

        pie = ctk.CTkFrame(lat, fg_color='transparent')
        pie.pack(side='bottom', fill='x', padx=18, pady=18)
        est = self.conocimiento.estadisticas()
        p = self.diagnostico.parametros
        ctk.CTkLabel(pie, text=f"{est['hipotesis']} hipótesis · {est['reglas']} reglas\n"
                               f"{est['evidencias']} evidencias · {est['filas_granulo']} gránulos",
                     font=tema.fuente(11), text_color=tema.TEXTO_SUAVE, anchor='w', justify='left').pack(fill='x')
        ctk.CTkLabel(pie, text=f'Motor: β = {p.beta:g} · umbral {p.umbral_probabilidad:.0%} · '
                               f'{p.hipotesis_resultado} hipótesis', font=tema.fuente(11),
                     text_color=tema.TEXTO_SUAVE, anchor='w').pack(fill='x', pady=(4, 0))
        ctk.CTkLabel(pie, text=f'Base de datos: {descripcion_bd}', font=tema.fuente(11), text_color=tema.TEXTO_SUAVE,
                     anchor='w').pack(fill='x', pady=(4, 10))
        self.interruptor = ctk.CTkSwitch(pie, text='Modo oscuro', command=self._cambiar_tema, font=tema.fuente(12),
                                         text_color=tema.TEXTO, progress_color=tema.ACENTO)
        self.interruptor.pack(fill='x')

    def _pintar_navegacion(self):
        activa = 'consulta' if self.vista_actual == 'resultado' and self._hay_consulta_abierta() else self.vista_actual
        for clave, b in self.botones_nav.items():
            sel = clave == activa
            habil = clave != 'consulta' or self._hay_consulta_abierta()
            b.configure(fg_color=tema.ACENTO_SUAVE if sel else 'transparent',
                        hover_color=tema.ACENTO_SUAVE,
                        text_color=tema.ACENTO if sel else (tema.TEXTO if habil else tema.BORDE),
                        state='normal' if habil else 'disabled')

    def _hay_consulta_abierta(self):
        return self.sesion is not None and not self.sesion.finalizada

    # ================================================================ navegación
    def mostrar(self, nombre):
        if nombre == 'consulta' and not self._hay_consulta_abierta():
            return
        if nombre == 'historial':
            self.vistas['historial'].cargar()
        self.vista_actual = nombre
        self.vistas[nombre].tkraise()
        self._pintar_navegacion()

    def iniciar_consulta(self, sintomas, equipo, ubicacion, descripcion, nombre=''):
        if self._hay_consulta_abierta():
            if not messagebox.askyesno('SEDATI', 'Hay una consulta en curso. ¿Desea cancelarla e iniciar una nueva?',
                                       parent=self):
                return
            self.sesion.cancelar()
        self.sesion = self.diagnostico.iniciar(sintomas, equipo, ubicacion, descripcion, nombre=nombre)
        self.vistas['consulta'].cargar(self.sesion)
        self.mostrar('consulta')

    def ver_resultado(self):
        if self.sesion is None:
            return
        self.vistas['resultado'].cargar(self.sesion)
        self.mostrar('resultado')

    def finalizar_consulta(self):
        self.sesion.finalizar()
        self.vistas['resultado'].cargar(self.sesion)
        self.vistas['inicio'].limpiar()
        self._pintar_navegacion()

    def cancelar_consulta(self):
        if self.sesion and messagebox.askyesno('SEDATI', '¿Cancelar la consulta en curso?', parent=self):
            self.sesion.cancelar()
            self.sesion = None
            self.mostrar('inicio')

    def abrir_consulta_guardada(self, consulta_id):
        try:
            sesion = self.diagnostico.reconstruir(consulta_id)
        except Exception as error:  # noqa: BLE001 - se informa al usuario
            messagebox.showerror('SEDATI', str(error), parent=self)
            return
        if not sesion.finalizada:
            if self._hay_consulta_abierta() and self.sesion.consulta_id != consulta_id:
                if not messagebox.askyesno('SEDATI', 'Hay otra consulta en curso. ¿Desea dejarla y retomar esta?',
                                           parent=self):
                    return
            self.sesion = sesion
            self.vistas['consulta'].cargar(sesion)
            self.mostrar('consulta')
        else:
            self.vistas['resultado'].cargar(sesion)
            self.mostrar('resultado')

    # ================================================================ otros
    def _tecla(self, evento):
        if self.vista_actual != 'consulta' or evento.char not in '12345' or not evento.char:
            return
        foco = self.focus_get()
        if foco is not None and foco.winfo_class() in ('Entry', 'Text'):
            return
        self.vistas['consulta'].responder_atajo(int(evento.char) - 1)

    def _cambiar_tema(self):
        ctk.set_appearance_mode('dark' if self.interruptor.get() else 'light')
        estilo_tablas(self)
        for v in self.vistas.values():
            v.al_cambiar_tema()
        self._pintar_navegacion()

    def _cerrar(self):
        if self._hay_consulta_abierta():
            self.sesion.cancelar()
        self.destroy()
