"""Fábrica de DAO: entrega a la capa de negocio las implementaciones que corresponden al motor."""
from .sql_conocimiento import ConocimientoDAOSQL
from .sql_transaccional import CatalogoDAOSQL, DiagnosticoDAOSQL


class FabricaDAO:
    """Crea los DAO sobre las dos conexiones: sedati_kb (conocimiento) y sedati_trx (transaccional).

    Las implementaciones SQL sirven para MySQL 8 y para SQLite porque la conexión traduce el
    marcador de parámetros y normaliza los tipos. Un motor distinto solo necesitaría otra fábrica
    con sus propias implementaciones de las interfaces de dao/interfaces.py.
    """

    def __init__(self, conexion_kb, conexion_trx):
        self.conexion_kb = conexion_kb
        self.conexion_trx = conexion_trx

    # sedati_kb
    def conocimiento(self):
        return ConocimientoDAOSQL(self.conexion_kb)

    # sedati_trx
    def catalogo(self):
        return CatalogoDAOSQL(self.conexion_trx)

    def diagnosticos(self):
        return DiagnosticoDAOSQL(self.conexion_trx)

    def verificar(self):
        self.conexion_kb.verificar()
        self.conexion_trx.verificar()

    def cerrar(self):
        self.conexion_kb.cerrar()
        self.conexion_trx.cerrar()

    @property
    def descripcion(self):
        return f'{self.conexion_kb.descripcion} + {self.conexion_trx.descripcion.split(" · ")[-1]}'
