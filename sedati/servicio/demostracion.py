"""Incidentes de demostración, creados con la propia capa de negocio (no con SQL suelto).

Cada caso recorre el proceso real de RF-02: el solicitante reporta, un administrador toma el incidente,
programa la cita, ejecuta el motor de inferencia, confirma una hipótesis y registra la solución (o
escala). Las respuestas a las preguntas del motor las da un «técnico simulado» que conoce la causa real
del caso: responde «Sí» a las condiciones del gránulo de esa causa y «No» a lo demás.

Se usa al crear la base SQLite por primera vez (config.ini: datos_demostracion = si) y con
    python bd/instalar_mysql.py --demo
"""
from datetime import datetime, timedelta

from ..negocio import ServicioAtencion, ServicioDiagnostico, UsuarioActual


class RelojSimulado:
    def __init__(self, fecha):
        self.fecha = fecha

    def __call__(self):
        return self.fecha

    def avanzar(self, **delta):
        self.fecha += timedelta(**delta)


# (días atrás, solicitante, administrador, inventario, ubicación, descripción, [(regla de la causa, resultado)], escalar)
CASOS = [
    (21, 4, 2, 'IMP-BIB-01', 'Biblioteca, mostrador',
     'La impresora de la biblioteca no imprime: los documentos quedan en cola y no sale ninguna hoja.',
     [('R-47', 'SOLUCIONADO', 9)], None),
    (16, 3, 1, 'PC-SALA2-014', 'Sala de cómputo 2, puesto 14',
     'El computador del puesto 14 no enciende: al oprimir el botón no prende ninguna luz.',
     [('R-02', 'NO_SOLUCIONADO', 25), ('R-03', 'SOLUCIONADO', 15)], None),
    (11, 5, 1, 'PC-LABRED-07', 'Laboratorio de redes, puesto 7',
     'El equipo no tiene Internet desde esta mañana; los demás equipos del laboratorio sí navegan.',
     [('HIP-25', 'NO_SOLUCIONADO', 18)], ('El puerto del switch requiere cambio de VLAN; no hay acceso de '
                                          'administración al switch desde soporte.', 'Infraestructura de redes')),
    (7, 3, 2, 'PC-SALA2-014', 'Sala de cómputo 2, puesto 14',
     'La memoria USB de un estudiante no aparece en el equipo; en otros computadores sí funciona.',
     [('HIP-18', 'SOLUCIONADO', 12)], None),
    (4, 4, 1, 'PC-SALA1-003', 'Sala de cómputo 1, puesto 3',
     'El computador está muy lento para abrir los programas y se queda pensando varios minutos.',
     [('HIP-16', None, None)], None),
    (0, 5, None, 'POR-SOP-02', 'Oficina de soporte técnico',
     'El portátil de préstamo se reinicia solo cuando se usa con el cargador conectado.',
     [], None),
]


def _usuario(api, usuario_id):
    u = api.fabrica.usuarios().por_id(usuario_id)
    return UsuarioActual(u.id, u.nombre, u.correo, u.rol_codigo, api.fabrica.catalogo().permisos_de_rol(u.rol_codigo))


def _regla_objetivo(api, codigo, categoria=None):
    """Una regla concreta (R-NN) o la primera regla activa de una hipótesis (HIP-NN)."""
    admin = api.fabrica.administracion_conocimiento()
    if codigo.startswith('R-'):
        return admin.filas_granulo(codigo)
    h = api.fabrica.conocimiento().hipotesis_por_codigos([codigo])[0]
    filas = api.fabrica.conocimiento().condiciones_de_hipotesis(h['id'])
    reglas = sorted({f['regla'] for f in filas if not categoria or f['categoria_codigo'] == categoria})
    return admin.filas_granulo(reglas[0])


def _respuestas_del_tecnico(diagnostico, filas_objetivo, descartadas):
    """Simula al técnico: confirma las condiciones de la causa real y niega lo demás."""
    objetivo = {f['evidencia_id'] for f in filas_objetivo}
    variables = {f['variable']: f['polaridad'] for f in filas_objetivo if f['variable']}
    sintomas = [filas_objetivo[0]['evidencia_id']]
    respuestas = []
    for _ in range(12):
        sesion = diagnostico.reproducir(sintomas, respuestas, descartadas=descartadas)
        q = sesion.pregunta_actual
        if q is None or sesion.motivo_conclusion:
            break
        e = q.evidencia
        if e.id in objetivo:
            escala = 'SI'
        elif e.variable and e.variable in variables:
            escala = 'SI' if e.polaridad == variables[e.variable] else 'NO'
        else:
            escala = 'NO'
        respuestas.append((e.id, escala))
    return sintomas, respuestas


def cargar_demostracion(api):
    hoy = api.configuracion.ahora().replace(hour=8, minute=0, second=0)
    reloj = RelojSimulado(hoy)
    f = api.fabrica
    diagnostico = ServicioDiagnostico(f.conocimiento(), f.diagnosticos(), f.catalogo(), api.configuracion.motor, reloj)
    atencion = ServicioAtencion(f, diagnostico, reloj)
    for dias, solicitante_id, admin_id, inventario, ubicacion, descripcion, rondas, escalar in CASOS:
        reloj.fecha = hoy - timedelta(days=dias) + timedelta(minutes=37 * solicitante_id)
        solicitante = _usuario(api, solicitante_id)
        inc = atencion.reportar(solicitante, {'inventario': inventario, 'ubicacion': ubicacion,
                                              'descripcion': descripcion})
        if admin_id is None:
            continue
        admin = _usuario(api, admin_id)
        reloj.avanzar(minutes=40)
        atencion.tomar(admin, inc.id)
        reloj.avanzar(minutes=5)
        inicio = reloj.fecha + timedelta(hours=2) if dias else reloj.fecha + timedelta(days=1)
        if dias == 4:
            inicio = datetime.combine((hoy + timedelta(days=1)).date(), datetime.min.time()) + timedelta(hours=10)
        cita = atencion.programar_cita(solicitante if dias % 2 else admin, inc.id, {
            'inicio': inicio.strftime('%Y-%m-%d %H:%M'), 'fin': (inicio + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M'),
            'lugar': ubicacion})
        if dias != 4:
            reloj.fecha = inicio + timedelta(minutes=10)
            atencion.cambiar_estado_cita(admin, cita.id, 'ATENDIDA')
        causas = {_regla_objetivo(api, o, 'F' if o == 'HIP-25' else None)[0]['hipotesis_id'] for o, _, _ in rondas}
        codigos = {h['id']: h['codigo'] for h in f.conocimiento().resumen_hipotesis()}
        for objetivo, resultado, minutos in rondas:
            filas = _regla_objetivo(api, objetivo, 'F' if objetivo == 'HIP-25' else None)
            descartadas = f.diagnosticos().descartadas_de_incidente(inc.id)
            sintomas, respuestas = _respuestas_del_tecnico(diagnostico, filas, descartadas)
            reloj.avanzar(minutes=8)
            sesion = atencion.guardar_diagnostico(admin, inc.id, sintomas, respuestas)
            if resultado is None:
                break
            propuestas = f.diagnosticos().hipotesis(sesion.diagnostico_id)
            codigo_objetivo = codigos.get(filas[0]['hipotesis_id'])
            elegida = next((p for p in propuestas if p.hipotesis_codigo == codigo_objetivo), propuestas[0])
            reservadas = {codigos[c] for c in causas}       # causas de rondas siguientes: no se descartan
            for p in propuestas:
                if p.id != elegida.id and p.posicion <= 2 and p.hipotesis_codigo not in reservadas:
                    atencion.decidir_hipotesis(admin, p.id, 'DESCARTADA')
            atencion.decidir_hipotesis(admin, elegida.id, 'CONFIRMADA')
            reloj.avanzar(minutes=minutos)
            atencion.registrar_intervencion(admin, elegida.id, {
                'accion_aplicada': elegida.accion, 'resultado': resultado, 'tiempo_min': minutos,
                'observaciones': 'Caso de demostración.' if resultado == 'SOLUCIONADO'
                else 'La acción no resolvió la falla; se ejecuta una nueva ronda.'})
        if escalar:
            reloj.avanzar(minutes=20)
            atencion.escalar(admin, inc.id, {'motivo': escalar[0], 'destino': escalar[1]})
