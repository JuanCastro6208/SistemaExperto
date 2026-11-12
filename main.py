"""Aplicación de escritorio de SEDATI: arma las tres capas y abre la interfaz gráfica.

    python main.py

Versión de escritorio del sistema experto (diagnóstico, base de conocimiento e historial). La versión
principal es la aplicación web, que guía el diagnóstico por el árbol de decisión:
    python servidor_web.py
"""
import sys
from tkinter import Tk, messagebox

from sedati.configuracion import cargar_configuracion
from sedati.datos import FabricaDAO, crear_conexiones
from sedati.negocio import ServicioConocimiento, ServicioDiagnostico


def main():
    configuracion = cargar_configuracion()

    # Capa de datos
    try:
        fabrica = FabricaDAO(*crear_conexiones(configuracion))
    except Exception as error:  # noqa: BLE001 - se informa cualquier fallo de conexión al usuario
        raiz = Tk()
        raiz.withdraw()
        messagebox.showerror('SEDATI', f'No fue posible conectar con la base de datos '
                                       f'({configuracion.motor_bd}).\n\n{error}\n\nRevise config.ini.')
        return 1

    # Capa de negocio (recibe los DAO, no SQL)
    diagnostico = ServicioDiagnostico(fabrica.conocimiento(), fabrica.diagnosticos(), fabrica.catalogo(),
                                      configuracion.motor, configuracion.ahora)
    conocimiento = ServicioConocimiento(fabrica.conocimiento())

    # Capa de presentación
    from sedati.presentacion import AplicacionSEDATI
    app = AplicacionSEDATI(diagnostico, conocimiento, fabrica.descripcion)
    try:
        app.mainloop()
    finally:
        fabrica.cerrar()
    return 0


if __name__ == '__main__':
    sys.exit(main())
