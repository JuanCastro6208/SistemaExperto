"""Colores y tipografía de la interfaz (cada color es una pareja: modo claro, modo oscuro)."""
import customtkinter as ctk

FUENTE = 'Segoe UI'

FONDO = ('#F2F4F7', '#0F141B')
LATERAL = ('#FFFFFF', '#151C25')
TARJETA = ('#FFFFFF', '#1B2430')
TARJETA_SUAVE = ('#F7F9FB', '#212C3A')
BORDE = ('#E3E7ED', '#2A3646')
TEXTO = ('#18212D', '#E7ECF2')
TEXTO_SUAVE = ('#5B6676', '#97A3B4')
ACENTO = ('#1F6FEB', '#4C8DF6')
ACENTO_HOVER = ('#195CC4', '#3B79DD')
ACENTO_SUAVE = ('#E7F0FE', '#1D2C44')
EXITO = ('#1E8E5A', '#3DBB7E')
AVISO = ('#B7791F', '#E0A848')
AVISO_FONDO = ('#FDF4E3', '#3A2E17')
PELIGRO = ('#C9473D', '#E06C62')
PELIGRO_FONDO = ('#FBE9E7', '#3B1F1D')

# Colores de las 5 hipótesis en las gráficas (de la más a la menos probable)
SERIE = ['#1F6FEB', '#13A89E', '#F2A541', '#8E6CEF', '#E5646E']


def fuente(tamano=13, peso='normal'):
    return ctk.CTkFont(family=FUENTE, size=tamano, weight=peso)


def color(par):
    """Color activo de una pareja (claro, oscuro) según el modo de apariencia actual."""
    return par[1] if ctk.get_appearance_mode() == 'Dark' else par[0]
