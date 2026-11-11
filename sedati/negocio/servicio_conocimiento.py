"""RF-03. Administración de la base de conocimiento: hipótesis, evidencias y gránulos, sin tocar el código.

Cada cambio queda en auditoria_conocimiento (sedati_trx). Nada se elimina: se desactiva. Modificar
un gránulo sube su versión; los diagnósticos anteriores conservan la versión que usaron. Cambiar las
condiciones de una regla equivale a otra regla: se crea un gránulo nuevo y se desactiva el anterior.
"""
import json
import re

from . import certeza
from ..datos.conexion import ErrorIntegridad
from .errores import Conflicto, ErrorNegocio, NoEncontrado

DOMINIOS = ('Hardware', 'Sistema operativo', 'Periféricos', 'Red', 'Software', 'Accesos')


def _texto(valor, nombre, maximo, minimo=3):
    t = (valor or '').strip() if isinstance(valor, str) else ''
    if len(t) < minimo or len(t) > maximo:
        raise ErrorNegocio(f'{nombre} debe tener entre {minimo} y {maximo} caracteres.')
    return t


def _numero(valor, nombre, minimo, maximo):
    try:
        n = float(valor)
    except (TypeError, ValueError):
        raise ErrorNegocio(f'{nombre} debe ser un número.') from None
    if not minimo <= n <= maximo:
        raise ErrorNegocio(f'{nombre} debe estar entre {minimo:g} y {maximo:g}.')
    return n


class ServicioAdministracionConocimiento:
    def __init__(self, dao_administracion, dao_conocimiento, dao_auditoria, reloj):
        self._admin = dao_administracion
        self._kb = dao_conocimiento
        self._auditoria = dao_auditoria
        self._reloj = reloj

    def _ahora(self):
        return self._reloj().strftime('%Y-%m-%d %H:%M:%S')

    def _auditar(self, usuario, entidad, codigo, version, accion, detalle):
        self._auditoria.registrar(entidad, codigo, version, accion, usuario.id,
                                  json.dumps(detalle, ensure_ascii=False, default=str), self._ahora())

    @staticmethod
    def _integridad(funcion, *args):
        try:
            return funcion(*args)
        except ErrorIntegridad as e:
            mensaje = str(e)
            if 'UNIQUE' in mensaje.upper() or 'Duplicate' in mensaje:
                raise Conflicto('Ya existe un elemento con ese nombre o enunciado.') from None
            raise Conflicto(mensaje) from None

    # ================================================================ hipótesis
    def crear_hipotesis(self, usuario, datos):
        usuario.exigir('CONOCIMIENTO', 'crear')
        nombre = _texto(datos.get('nombre'), 'El nombre de la hipótesis', 120)
        dominio = datos.get('dominio')
        if dominio not in DOMINIOS:
            raise ErrorNegocio(f'El dominio debe ser uno de: {", ".join(DOMINIOS)}.')
        previa = _numero(datos.get('probabilidad_previa', 0.01) or 0.01, 'La probabilidad previa', 0.0001, 1)
        codigo = self._admin.siguiente_codigo('HIPOTESIS')
        nuevo = self._integridad(self._admin.crear_hipotesis, codigo, nombre, dominio, previa)
        self._auditar(usuario, 'HIPOTESIS', codigo, None, 'CREAR', {'nombre': nombre, 'dominio': dominio,
                                                                    'probabilidad_previa': previa})
        return self._admin.hipotesis(nuevo)

    def cambiar_estado_hipotesis(self, usuario, hipotesis_id, activo):
        usuario.exigir('CONOCIMIENTO', 'modificar')
        h = self._admin.hipotesis(hipotesis_id)
        if h is None:
            raise NoEncontrado(f'No existe la hipótesis {hipotesis_id}.')
        self._admin.cambiar_estado_hipotesis(hipotesis_id, activo)
        self._auditar(usuario, 'HIPOTESIS', h['codigo'], None, 'ACTIVAR' if activo else 'DESACTIVAR', {'activo': activo})
        return self._admin.hipotesis(hipotesis_id)

    # ================================================================ evidencias
    def crear_evidencia(self, usuario, datos):
        usuario.exigir('CONOCIMIENTO', 'crear')
        tipo = datos.get('tipo')
        if tipo not in ('SINTOMA', 'PRUEBA'):
            raise ErrorNegocio('El tipo de evidencia debe ser SINTOMA o PRUEBA.')
        enunciado = _texto(datos.get('enunciado'), 'El enunciado', 250, 5)
        enunciado = enunciado[0].lower() + enunciado[1:]
        pregunta = (datos.get('pregunta') or '').strip() or f'¿{enunciado[0].upper()}{enunciado[1:]}?'
        pregunta = _texto(pregunta, 'La pregunta', 300, 5)
        variable = (datos.get('variable') or '').strip().upper() or None
        if variable and not re.fullmatch(r'[A-Z0-9_]{2,40}', variable):
            raise ErrorNegocio('La variable solo admite letras, números y «_» (ej.: TENSION_TOMA).')
        polaridad = -1 if str(datos.get('polaridad', 1)) == '-1' else 1
        codigo = self._admin.siguiente_codigo('EVIDENCIA')
        nuevo = self._integridad(self._admin.crear_evidencia, codigo, tipo, enunciado, pregunta, variable, polaridad)
        self._auditar(usuario, 'EVIDENCIA', codigo, None, 'CREAR', {'tipo': tipo, 'enunciado': enunciado})
        return self._admin.evidencia(nuevo)

    def cambiar_estado_evidencia(self, usuario, evidencia_id, activo):
        usuario.exigir('CONOCIMIENTO', 'modificar')
        e = self._admin.evidencia(evidencia_id)
        if e is None:
            raise NoEncontrado(f'No existe la evidencia {evidencia_id}.')
        self._admin.cambiar_estado_evidencia(evidencia_id, activo)
        self._auditar(usuario, 'EVIDENCIA', e['codigo'], None, 'ACTIVAR' if activo else 'DESACTIVAR', {'activo': activo})
        return self._admin.evidencia(evidencia_id)

    # ================================================================ gránulos
    def ramas(self, usuario):
        usuario.exigir('CONOCIMIENTO')
        return self._admin.ramas()

    def _datos_regla(self, datos):
        conclusion = _texto(datos.get('conclusion'), 'La conclusión (Then)', 250, 5)
        accion = _texto(datos.get('accion'), 'La acción recomendada', 500, 5)
        fc = _numero(datos.get('factor_certeza'), 'El factor de certeza', 0, 100)
        return {'conclusion': conclusion, 'accion': accion, 'factor_certeza': round(fc, 2),
                'riesgo_perdida_datos': bool(datos.get('riesgo_perdida_datos'))}

    def crear_granulo(self, usuario, datos):
        usuario.exigir('CONOCIMIENTO', 'crear')
        try:
            hipotesis_id = int(datos.get('hipotesis_id'))
        except (TypeError, ValueError):
            raise ErrorNegocio('Elija la hipótesis que concluye la regla.') from None
        h = self._admin.hipotesis(hipotesis_id)
        if h is None or not h['activo']:
            raise ErrorNegocio('La hipótesis no existe o está desactivada.')
        rama = next((r for r in self._admin.ramas() if r['rama_codigo'] == datos.get('rama_codigo')), None)
        if rama is None:
            raise ErrorNegocio('Elija una rama del árbol de decisión.')
        condiciones = datos.get('condiciones') or []
        if not isinstance(condiciones, list) or not condiciones:
            raise ErrorNegocio('El gránulo necesita al menos una condición (If).')
        ids = []
        for c in condiciones:
            try:
                ids.append(int(c['evidencia_id'] if isinstance(c, dict) else c))
            except (TypeError, ValueError, KeyError):
                raise ErrorNegocio('Cada condición debe indicar una evidencia del catálogo.') from None
        if len(set(ids)) != len(ids):
            raise ErrorNegocio('Un gránulo no puede repetir una evidencia entre sus condiciones.')
        existentes = {f['id']: f for f in self._kb.evidencias_por_ids(ids)}
        if any(i not in existentes for i in ids):
            raise ErrorNegocio('Alguna condición usa una evidencia que no existe.')
        pesos = []
        for c in condiciones:
            peso = c.get('peso', 1) if isinstance(c, dict) else 1
            pesos.append(round(_numero(peso or 1, 'El peso de una condición', 0.1, 5), 2))
        regla = self._admin.siguiente_codigo('GRANULO')
        cuerpo = self._datos_regla(datos)
        cuerpo.update({'categoria_codigo': rama['categoria_codigo'], 'categoria_nombre': rama['categoria_nombre'],
                       'rama_codigo': rama['rama_codigo'], 'rama_nombre': rama['rama_nombre'],
                       'procesos': (datos.get('procesos') or rama['procesos'] or '')[:20],
                       'fuente': f'Administrador: {usuario.nombre} ({self._ahora()[:10]})'[:160]})
        self._integridad(self._admin.crear_granulo, regla, hipotesis_id, list(zip(ids, pesos)), cuerpo, self._ahora())
        self._auditar(usuario, 'GRANULO', regla, 1, 'CREAR',
                      {'hipotesis': h['codigo'], 'rama': rama['rama_codigo'],
                       'condiciones': [existentes[i]['codigo'] for i in ids], **cuerpo})
        return self.granulo(usuario, regla)

    def granulo(self, usuario, regla):
        usuario.exigir('CONOCIMIENTO')
        filas = self._admin.filas_granulo(regla)
        if not filas:
            raise NoEncontrado(f'No existe el gránulo {regla}.')
        return filas

    def modificar_granulo(self, usuario, regla, datos):
        usuario.exigir('CONOCIMIENTO', 'modificar')
        filas = self.granulo(usuario, regla)
        anterior = {k: filas[0][k] for k in ('conclusion', 'accion', 'factor_certeza', 'riesgo_perdida_datos')}
        nuevo = self._datos_regla(datos)
        if all(str(anterior[k]) == str(nuevo[k]) for k in ('conclusion', 'accion')) \
                and float(anterior['factor_certeza']) == nuevo['factor_certeza'] \
                and bool(anterior['riesgo_perdida_datos']) == nuevo['riesgo_perdida_datos']:
            raise ErrorNegocio('No hay cambios que guardar.')
        self._integridad(self._admin.modificar_granulo, regla, nuevo, self._ahora())
        version = filas[0]['version'] + 1
        self._auditar(usuario, 'GRANULO', regla, version, 'MODIFICAR', {'anterior': anterior, 'nuevo': nuevo})
        return self._admin.filas_granulo(regla)

    def cambiar_estado_granulo(self, usuario, regla, activo):
        usuario.exigir('CONOCIMIENTO', 'modificar')
        filas = self.granulo(usuario, regla)
        self._admin.cambiar_estado_granulo(regla, activo, self._ahora())
        self._auditar(usuario, 'GRANULO', regla, filas[0]['version'], 'ACTIVAR' if activo else 'DESACTIVAR',
                      {'activo': activo})
        return self._admin.filas_granulo(regla)

    def simular(self, usuario, regla, evidencia_ids):
        """Certeza que daría un gránulo si se observaran (con «Sí, con certeza») las evidencias indicadas."""
        usuario.exigir('CONOCIMIENTO')
        filas = self.granulo(usuario, regla)
        observadas = {int(i) for i in (evidencia_ids or [])}
        fc = float(filas[0]['factor_certeza']) / 100
        cumplidas = sum(1 for f in filas if f['evidencia_id'] in observadas)
        entrada = 1.0 if filas[0]['evidencia_id'] in observadas else None
        resto = filas[1:] if len(filas) > 1 else filas
        grado = certeza.grado_cumplimiento((float(f['peso']), 1.0 if f['evidencia_id'] in observadas else None)
                                           for f in resto)
        aplica = certeza.aplicabilidad(entrada, 0.10) if len(filas) > 1 else 1.0
        return {'regla': regla, 'cumplidas': cumplidas, 'total': len(filas),
                'certeza_proporcional': round(100 * fc * cumplidas / len(filas), 2),
                'aplicabilidad': round(aplica, 4), 'grado': round(grado, 4),
                'aporte_motor': round(aplica * grado * fc, 4),
                'condiciones': [{'orden': f['orden'], 'conector': f['conector'], 'evidencia_id': f['evidencia_id'],
                                 'codigo': f['evidencia_codigo'], 'enunciado': f['enunciado'],
                                 'cumplida': f['evidencia_id'] in observadas} for f in filas]}

    def auditoria(self, usuario, codigo=None):
        usuario.exigir('CONOCIMIENTO')
        return self._auditoria.listar(codigo)
