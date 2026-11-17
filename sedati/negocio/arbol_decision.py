"""Árbol de decisión de SEDATI (figura SEDATI_arbol_completo.png) para el recorrido con «Sí» y «No».

La persona recorre el árbol respondiendo solo Sí o No:

    categoría (A. Energía y arranque, B. Video…)  →  situación (If)  →  detalle (And)  →  causas (Then)

    · Sí: entra al nodo (si tiene hijos pregunta por el primero; si es una hoja, termina el recorrido).
    · No: pasa al siguiente nodo del mismo nivel (la siguiente pregunta del árbol).

Al llegar a una hoja, el motor de inferencia continúa con preguntas graduadas (Sí, con certeza · Probablemente
sí · No lo sé · Probablemente no · No, con certeza) para asignar el peso probabilístico de cada causa.

Las preguntas del árbol no reemplazan la base de conocimiento: cada nodo indica qué evidencias de la tabla
evidencia (códigos E-NNN) quedan confirmadas con Sí y cuáles quedan negadas con No. Esas respuestas se
entregan al motor (las confirmadas como síntomas iniciales y las negadas como respuestas «No»), y el motor
consulta las reglas de la tabla granulo como siempre. Los nombres de las categorías y de las ramas salen de
la base de conocimiento; aquí solo están el texto de cada pregunta y las causas de cada hoja, tal como en la
figura. El nivel 2 de la figura son las 22 ramas de la base (A1 … G5).
"""


def _n(pregunta, si=(), no=(), causas=(), hijos=()):
    """Nodo del árbol. si / no: evidencias que se registran al responder Sí / No.
    Cada evidencia es 'E-NNN' (se registra como SI) o ('E-NNN', 'NO')."""
    def norm(lista):
        return [(e, 'SI') if isinstance(e, str) else tuple(e) for e in lista]
    return {'pregunta': pregunta, 'si': norm(si), 'no': norm(no), 'causas': list(causas), 'hijos': list(hijos)}


def _no(*codigos):
    return [(c, 'NO') for c in codigos]


# rama (código de la base de conocimiento) -> nodo de nivel 2 con sus detalles
ARBOL = {
    # ------------------------------------------------------------------ A. Energía y arranque
    'A1': _n('¿El equipo no enciende?', si=['E-001'], hijos=[
        _n('¿No hay tensión en la toma eléctrica?', si=['E-002'], no=_no('E-002'),
           causas=['Falla la toma eléctrica', 'Falla el regulador o UPS', 'Falla la multitoma']),
        _n('¿Hay tensión en la toma y el equipo no da respuesta?', si=['E-003'],
           causas=['Falla la fuente de poder', 'Falla el cable de poder', 'Falla el botón de encendido']),
        _n('¿Los ventiladores giran pero el equipo no arranca?', si=['E-006'], no=_no('E-006'),
           causas=['Mal asentada la RAM', 'Falla la placa madre', 'Falla el procesador']),
    ]),
    'A2': _n('¿El equipo se apaga solo?', si=['E-008'], hijos=[
        _n('¿Se apaga tras varios minutos y el chasis está caliente?', si=['E-009', 'E-010'],
           causas=['Disipador obstruido con polvo', 'Pasta térmica degradada', 'Ventilador detenido']),
        _n('¿Se apaga de forma inmediata y aleatoria?', si=['E-012'], no=_no('E-012'),
           causas=['Fuente de poder insuficiente', 'Alimentación eléctrica inestable', 'Cortocircuito en la placa']),
    ]),
    'A3': _n('¿Se presentan reinicios inesperados?', si=['E-014'], hijos=[
        _n('¿Aparece pantalla azul con código de error?', si=['E-015'], no=_no('E-015'),
           causas=['Controlador defectuoso', 'Memoria RAM con errores', 'Disco con sectores dañados']),
        _n('¿Se reinicia sin mostrar ningún mensaje de error?', si=['E-018'],
           causas=['Falla la fuente de poder', 'Sobrecalentamiento del procesador', 'Actualización fallida']),
    ]),
    # ------------------------------------------------------------------ B. Video y pantalla
    'B1': _n('¿El equipo enciende pero no hay imagen?', si=['E-021', 'E-022'], hijos=[
        _n('¿El monitor no enciende?', si=['E-023'], no=_no('E-023'),
           causas=['Monitor apagado o en otra entrada', 'Falla el cable de poder', 'Falla el monitor']),
        _n('¿El monitor muestra «sin señal»?', si=['E-024'], no=_no('E-024'), hijos=[
            _n('¿Hay pitidos de POST al encender?', si=['E-025'], no=_no('E-025'),
               causas=['Memoria RAM mal asentada', 'Tarjeta de video mal asentada', 'Falla la placa madre']),
            _n('¿No hay pitidos de POST al encender?', si=['E-026'],
               causas=['Falla el cable de video', 'Puerto de video incorrecto', 'Falla la tarjeta gráfica']),
        ]),
    ]),
    'B2': _n('¿La imagen se ve distorsionada?', hijos=[
        _n('¿Hay líneas, colores alterados o artefactos en la pantalla?', si=['E-028'],
           causas=['Cable de video deteriorado', 'GPU sobrecalentada', 'Controlador gráfico dañado']),
        _n('¿La imagen es borrosa o tiene una resolución incorrecta?', si=['E-032'],
           causas=['Resolución no nativa', 'Controlador desactualizado', 'Frecuencia de refresco incorrecta']),
    ]),
    # ------------------------------------------------------------------ C. Sistema operativo y rendimiento
    'C1': _n('¿El sistema operativo no inicia?', si=['E-034'], hijos=[
        _n('¿Aparece «no bootable device» o un mensaje similar?', si=['E-035'], no=_no('E-035'),
           causas=['Disco no detectado en BIOS', 'Orden de arranque incorrecto', 'Partición de arranque dañada']),
        _n('¿Hay un bucle de reparación o pantalla azul al iniciar?', no=_no('E-038', 'E-040'),
           causas=['Archivos del sistema corruptos', 'Actualización fallida', 'Controlador incompatible']),
    ]),
    'C2': _n('¿El equipo está demasiado lento?', si=['E-042'], hijos=[
        _n('¿El uso de disco o de CPU se sostiene en 100 %?', si=_no('E-046'),
           causas=['Procesos en segundo plano', 'Software malicioso', 'Disco saturado']),
        _n('¿El uso de recursos es normal?', si=['E-046'], no=_no('E-046'),
           causas=['Memoria RAM insuficiente', 'Disco mecánico degradado', 'Perfil de usuario dañado']),
    ]),
    'C3': _n('¿Hay errores después de una actualización?', si=['E-049'], hijos=[
        _n('¿Falla un dispositivo o periférico?', si=['E-050'],
           causas=['Controlador incompatible', 'Controlador reemplazado', 'Firmware desactualizado']),
        _n('¿Falla el sistema o una aplicación?',
           causas=['Archivos de actualización corruptos', 'Conflicto con software instalado', 'Actualización incompleta']),
    ]),
    # ------------------------------------------------------------------ D. Almacenamiento y memoria
    'D1': _n('¿El disco duro no es reconocido?', si=['E-053'], hijos=[
        _n('¿El disco no aparece en la BIOS/UEFI?', si=['E-054'], no=_no('E-054'),
           causas=['Cable SATA o de poder suelto', 'Puerto de la placa dañado', 'Disco con daño físico']),
        _n('¿Aparece en la BIOS pero no en el sistema operativo?', si=['E-057', 'E-058'],
           causas=['Partición sin letra asignada', 'Sistema de archivos dañado', 'Controlador de almacenamiento']),
    ]),
    'D2': _n('¿La memoria RAM no es reconocida?', hijos=[
        _n('¿El equipo emite pitidos al encender?', si=['E-061'], no=_no('E-061'),
           causas=['Módulo defectuoso', 'Módulo mal asentado', 'Módulos incompatibles']),
        _n('¿El sistema reporta menos memoria de la instalada?', si=['E-064'],
           causas=['Ranura de memoria dañada', 'Memoria reservada por el video', 'Límite del sistema operativo']),
    ]),
    # ------------------------------------------------------------------ E. Periféricos
    'E1': _n('¿El teclado o el mouse no responde?', si=['E-067'], hijos=[
        _n('¿El dispositivo funciona en otro equipo?', si=['E-068'], no=_no('E-068'),
           causas=['Puerto USB dañado', 'Controlador del dispositivo', 'Suspensión selectiva de USB']),
        _n('¿El dispositivo tampoco funciona en otro equipo?', si=['E-071'],
           causas=['Dispositivo defectuoso', 'Cable o receptor inalámbrico', 'Pilas agotadas']),
    ]),
    'E2': _n('¿El dispositivo USB no es reconocido?', si=['E-074'], hijos=[
        _n('¿Otros puertos del equipo sí lo reconocen?', si=['E-075'], no=_no('E-075'),
           causas=['Puerto sin alimentación', 'Puerto físicamente dañado', 'Concentrador sobrecargado']),
        _n('¿Ningún puerto lo reconoce?', si=['E-076'],
           causas=['Controlador USB del sistema', 'Dispositivo dañado', 'Política que restringe USB']),
    ]),
    'E3': _n('¿La impresora no imprime?', si=['E-079'], hijos=[
        _n('¿La impresora no responde a la prueba de red?', si=['E-080'], no=_no('E-080'),
           causas=['Dirección IP cambiada', 'Impresora apagada o sin red', 'Puerto de impresión mal configurado']),
        _n('¿Responde, pero los trabajos se acumulan en la cola?', si=['E-083', 'E-084'],
           causas=['Cola de impresión detenida', 'Controlador dañado', 'Sin papel, tóner o con atasco']),
    ]),
    # ------------------------------------------------------------------ F. Red y conectividad
    'F1': _n('¿El equipo no tiene conexión a Internet?', si=['E-088'], hijos=[
        _n('¿No obtiene dirección IP (obtiene 169.254.x.x)?', si=['E-089'], no=_no('E-089'),
           causas=['Servicio DHCP detenido', 'VLAN incorrecta en el puerto', 'Cable o puerto del switch']),
        _n('¿Obtiene una dirección IP correcta?', si=['E-092'], hijos=[
            _n('¿No responde la puerta de enlace?', si=['E-093'], no=_no('E-093'),
               causas=['Puerto del switch en otra VLAN', 'Cableado horizontal deteriorado',
                       'Switch de acceso sin energía']),
            _n('¿Responde la puerta de enlace pero no responde 8.8.8.8?', si=['E-094', 'E-095'],
               causas=['Falla el enrutamiento de salida', 'Firewall perimetral bloqueando',
                       'Enlace del proveedor caído']),
        ]),
    ]),
    'F2': _n('¿El equipo no resuelve nombres de dominio?', si=['E-098'], hijos=[
        _n('¿Falla para todos los nombres consultados?',
           causas=['Servidor DNS mal configurado', 'Servidor DNS no disponible', 'Caché DNS corrupta']),
        _n('¿Falla solo para los nombres internos del dominio?', si=['E-101', 'E-102'],
           causas=['Sufijo DNS incorrecto', 'Zona interna sin replicar', 'Equipo fuera del dominio']),
    ]),
    'F3': _n('¿La conexión es lenta o inestable?', si=['E-103'], hijos=[
        _n('¿El enlace negocia a 10 o 100 Mbps?', si=['E-104'], no=_no('E-104'),
           causas=['Cable de red deteriorado', 'Conector mal ponchado', 'Puerto del switch degradado']),
        _n('¿La falla se presenta solo en Wi-Fi?', si=['E-106'],
           causas=['Cobertura insuficiente', 'Canal saturado o interferencia', 'Controlador inalámbrico obsoleto']),
    ]),
    'F4': _n('¿No hay comunicación con los equipos de la red?', si=['E-109'], hijos=[
        _n('¿Responde la puerta de enlace pero no los otros equipos?', si=['E-094'],
           causas=['Firewall local bloqueando', 'Descubrimiento de red desactivado', 'Equipo destino apagado']),
        _n('¿No responde ningún equipo de la red?',
           causas=['VLAN o subred distinta', 'Máscara de subred incorrecta', 'Aislamiento de puerto en el switch']),
    ]),
    # ------------------------------------------------------------------ G. Software y accesos
    'G1': _n('¿El usuario no puede iniciar sesión?', si=['E-114'], hijos=[
        _n('¿Hay un mensaje de contraseña incorrecta o cuenta bloqueada?',
           causas=['Credenciales erróneas', 'Cuenta bloqueada o vencida', 'Contraseña expirada']),
        _n('¿Hay un mensaje de dominio no disponible?', si=['E-118'], no=_no('E-118'),
           causas=['Equipo sin conectividad al dominio', 'DNS del dominio mal configurado',
                   'Relación de confianza rota']),
    ]),
    'G2': _n('¿Falla una aplicación?', hijos=[
        _n('¿La aplicación no inicia?', si=['E-123'],
           causas=['Instalación corrupta', 'Dependencias faltantes', 'Permisos insuficientes']),
        _n('¿La aplicación se cierra inesperadamente?', si=['E-127'],
           causas=['Archivos dañados', 'Memoria insuficiente', 'Incompatibilidad de versión']),
    ]),
    'G3': _n('¿No se puede instalar software?', si=['E-132'], hijos=[
        _n('¿Hay un mensaje de permisos o de política del sistema?', no=_no('E-133', 'E-135'),
           causas=['Sin permisos de administrador', 'Política de restricción activa', 'Control de cuentas bloqueando']),
        _n('¿El instalador se detiene sin un mensaje claro?',
           causas=['Espacio en disco insuficiente', 'Instalador incompleto o dañado', 'Antivirus bloqueando el proceso']),
    ]),
    'G4': _n('¿El antivirus presenta errores?', hijos=[
        _n('¿El servicio del antivirus no inicia o se detiene?', si=['E-139'],
           causas=['Servicio deshabilitado', 'Instalación dañada', 'Conflicto con otro antivirus']),
        _n('¿El antivirus no descarga actualizaciones?', si=['E-142'],
           causas=['Licencia vencida', 'Sin salida a Internet', 'Servidor de actualización bloqueado']),
    ]),
    'G5': _n('¿No hay acceso a los recursos compartidos?', si=['E-145'], hijos=[
        _n('¿Solicita credenciales y las rechaza?', si=['E-146'], no=_no('E-146'),
           causas=['Permisos del recurso insuficientes', 'Credenciales no válidas', 'Cuenta sin acceso al grupo']),
        _n('¿No encuentra la ruta o el servidor?', si=['E-150'],
           causas=['Servidor apagado o sin red', 'Nombre del servidor no resuelto', 'Servicio de archivos detenido']),
    ]),
}


def codigos_usados():
    """Todos los códigos de evidencia que menciona el árbol (para traer sus id de la base)."""
    codigos = set()

    def recorrer(nodo):
        codigos.update(c for c, _ in nodo['si'] + nodo['no'])
        for h in nodo['hijos']:
            recorrer(h)
    for nodo in ARBOL.values():
        recorrer(nodo)
    return codigos


def resolver(nodo, ids, ruta):
    """Copia del nodo con los códigos E-NNN convertidos a id de la base y un identificador de ruta (p. ej. C1.2.1)."""
    def evid(lista):
        faltan = [c for c, _ in lista if c not in ids]
        if faltan:
            raise ValueError(f'El árbol de decisión menciona evidencias que no existen o están inactivas: {faltan}')
        return [{'evidencia_id': ids[c], 'codigo': c, 'escala': e} for c, e in lista]
    return {'id': ruta, 'pregunta': nodo['pregunta'], 'si': evid(nodo['si']), 'no': evid(nodo['no']),
            'causas': nodo['causas'],
            'hijos': [resolver(h, ids, f'{ruta}.{i + 1}') for i, h in enumerate(nodo['hijos'])]}
