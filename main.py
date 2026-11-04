"""Punto de entrada de SEDATI: arma las tres capas y abre la interfaz gráfica.

    python main.py
"""
import sys
from tkinter import Tk, messagebox

from sedati.configuracion import cargar_configuracion
from sedati.datos import RepositorioConocimiento, RepositorioConsultas, crear_conexion
from sedati.negocio import ServicioConocimiento, ServicioDiagnostico


def main():
    configuracion = cargar_configuracion()

    # Capa de datos
    try:
        conexion = crear_conexion(configuracion)
    except Exception as error:  # noqa: BLE001 - se informa cualquier fallo de conexión al usuario
        raiz = Tk()
        raiz.withdraw()
        messagebox.showerror('SEDATI', f'No fue posible conectar con la base de datos '
                                       f'({configuracion.motor_bd}).\n\n{error}\n\nRevise config.ini.')
        return 1
    repo_conocimiento = RepositorioConocimiento(conexion)
    repo_consultas = RepositorioConsultas(conexion)

    # Capa de negocio
    diagnostico = ServicioDiagnostico(repo_conocimiento, repo_consultas, configuracion.motor)
    conocimiento = ServicioConocimiento(repo_conocimiento)

    # Capa de presentación
    from sedati.presentacion import AplicacionSEDATI
    app = AplicacionSEDATI(diagnostico, conocimiento, conexion.descripcion)
    try:
        app.mainloop()
    finally:
        conexion.cerrar()
    return 0


if __name__ == '__main__':
    sys.exit(main())
