-- =====================================================================
-- SEDATI - Base transaccional (sedati_trx) para SQLite
-- Equivalente a bd/mysql/03_trx_esquema.sql (archivo bd/sedati_trx.db).
-- SQLite no permite asignar columnas en un disparador BEFORE INSERT: donde MySQL corrige el valor
-- (estado inicial, ronda del diagnóstico), aquí el disparador rechaza el valor incorrecto y la capa
-- DAO envía el correcto.
-- =====================================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS auditoria_conocimiento;
DROP TABLE IF EXISTS intervencion;
DROP TABLE IF EXISTS diagnostico_hipotesis;
DROP TABLE IF EXISTS incidente_evidencia;
DROP TABLE IF EXISTS diagnostico;
DROP TABLE IF EXISTS escala_respuesta;
DROP TABLE IF EXISTS escalamiento;
DROP TABLE IF EXISTS cita;
DROP TABLE IF EXISTS incidente_historial;
DROP TABLE IF EXISTS incidente;
DROP TABLE IF EXISTS equipo;
DROP TABLE IF EXISTS tipo_equipo;
DROP TABLE IF EXISTS bitacora_acceso;
DROP TABLE IF EXISTS usuario;
DROP TABLE IF EXISTS dependencia;
DROP TABLE IF EXISTS rol_permiso;
DROP TABLE IF EXISTS modulo;
DROP TABLE IF EXISTS rol;

-- ------------------------------------------------------------- seguridad
CREATE TABLE rol (
    id          INTEGER      NOT NULL PRIMARY KEY,
    codigo      VARCHAR(20)  NOT NULL UNIQUE,
    nombre      VARCHAR(40)  NOT NULL UNIQUE,
    descripcion VARCHAR(250) NOT NULL
);

CREATE TABLE modulo (
    id     INTEGER     NOT NULL PRIMARY KEY,
    codigo VARCHAR(20) NOT NULL UNIQUE,
    nombre VARCHAR(60) NOT NULL
);

CREATE TABLE rol_permiso (
    rol_id          INTEGER NOT NULL REFERENCES rol (id),
    modulo_id       INTEGER NOT NULL REFERENCES modulo (id),
    puede_consultar INTEGER NOT NULL DEFAULT 0,
    puede_crear     INTEGER NOT NULL DEFAULT 0 CHECK (puede_crear = 0 OR puede_consultar = 1),
    puede_modificar INTEGER NOT NULL DEFAULT 0 CHECK (puede_modificar = 0 OR puede_consultar = 1),
    PRIMARY KEY (rol_id, modulo_id)
);

CREATE TABLE dependencia (
    id     INTEGER      NOT NULL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    activo INTEGER      NOT NULL DEFAULT 1
);

CREATE TABLE usuario (
    id                      INTEGER      NOT NULL PRIMARY KEY,
    rol_id                  INTEGER      NOT NULL REFERENCES rol (id),
    dependencia_id          INTEGER      NULL REFERENCES dependencia (id),
    documento               VARCHAR(20)  NOT NULL UNIQUE,
    nombre                  VARCHAR(120) NOT NULL,
    correo                  VARCHAR(120) NOT NULL UNIQUE COLLATE NOCASE,
    contrasena_hash         VARCHAR(255) NOT NULL CHECK (contrasena_hash LIKE 'pbkdf2_sha256$%'),
    debe_cambiar_contrasena INTEGER      NOT NULL DEFAULT 1,
    activo                  INTEGER      NOT NULL DEFAULT 1,
    intentos_fallidos       INTEGER      NOT NULL DEFAULT 0,
    bloqueado_hasta         DATETIME     NULL,
    ultimo_ingreso          DATETIME     NULL,
    creado_en               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE bitacora_acceso (
    id               INTEGER      NOT NULL PRIMARY KEY,
    usuario_id       INTEGER      NULL REFERENCES usuario (id),
    correo_intentado VARCHAR(120) NOT NULL,
    exitoso          INTEGER      NOT NULL,
    motivo           VARCHAR(40)  NOT NULL,
    ip               VARCHAR(45)  NULL,
    fecha            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------- equipos
CREATE TABLE tipo_equipo (
    id     INTEGER     NOT NULL PRIMARY KEY,
    codigo VARCHAR(20) NOT NULL UNIQUE,
    nombre VARCHAR(60) NOT NULL
);

CREATE TABLE equipo (
    id             INTEGER      NOT NULL PRIMARY KEY,
    inventario     VARCHAR(20)  NOT NULL UNIQUE COLLATE NOCASE,
    tipo_equipo_id INTEGER      NOT NULL REFERENCES tipo_equipo (id),
    dependencia_id INTEGER      NULL REFERENCES dependencia (id),
    marca          VARCHAR(60)  NULL,
    modelo         VARCHAR(60)  NULL,
    ubicacion      VARCHAR(100) NOT NULL,
    activo         INTEGER      NOT NULL DEFAULT 1
);

-- ------------------------------------------------------------- atención del incidente
CREATE TABLE incidente (
    id               INTEGER      NOT NULL PRIMARY KEY,
    codigo           CHAR(15)     NULL UNIQUE,
    solicitante_id   INTEGER      NOT NULL REFERENCES usuario (id),
    administrador_id INTEGER      NULL REFERENCES usuario (id),
    equipo_id        INTEGER      NOT NULL REFERENCES equipo (id),
    ubicacion        VARCHAR(100) NOT NULL,
    descripcion      TEXT         NOT NULL,
    categoria_codigo CHAR(1)      NULL CHECK (categoria_codigo IS NULL OR categoria_codigo BETWEEN 'A' AND 'G'),
    estado           VARCHAR(15)  NOT NULL DEFAULT 'ABIERTO'
                     CHECK (estado IN ('ABIERTO','EN_DIAGNOSTICO','ESCALADO','CERRADO')),
    fecha_apertura   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_cierre     DATETIME     NULL,
    actualizado_por  INTEGER      NULL REFERENCES usuario (id),
    actualizado_en   DATETIME     NULL,
    CHECK ((estado = 'CERRADO') = (fecha_cierre IS NOT NULL))
);
CREATE INDEX ix_incidente_estado ON incidente (estado);
CREATE INDEX ix_incidente_equipo ON incidente (equipo_id);

CREATE TABLE incidente_historial (
    id              INTEGER     NOT NULL PRIMARY KEY,
    incidente_id    INTEGER     NOT NULL REFERENCES incidente (id),
    estado_anterior VARCHAR(15) NULL,
    estado_nuevo    VARCHAR(15) NOT NULL,
    usuario_id      INTEGER     NULL REFERENCES usuario (id),
    cambiado_en     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_historial_incidente ON incidente_historial (incidente_id);

CREATE TABLE cita (
    id               INTEGER      NOT NULL PRIMARY KEY,
    incidente_id     INTEGER      NOT NULL REFERENCES incidente (id),
    administrador_id INTEGER      NOT NULL REFERENCES usuario (id),
    inicio           DATETIME     NOT NULL,
    fin              DATETIME     NOT NULL,
    lugar            VARCHAR(100) NOT NULL,
    estado           VARCHAR(12)  NOT NULL DEFAULT 'PROGRAMADA'
                     CHECK (estado IN ('PROGRAMADA','ATENDIDA','CANCELADA','NO_ASISTIO')),
    creado_por       INTEGER      NOT NULL REFERENCES usuario (id),
    creado_en        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (fin > inicio)
);
CREATE INDEX ix_cita_administrador ON cita (administrador_id, inicio);

CREATE TABLE escalamiento (
    id           INTEGER      NOT NULL PRIMARY KEY,
    incidente_id INTEGER      NOT NULL REFERENCES incidente (id),
    motivo       TEXT         NOT NULL,
    destino      VARCHAR(100) NOT NULL,
    escalado_por INTEGER      NOT NULL REFERENCES usuario (id),
    escalado_en  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------- diagnóstico y solución
CREATE TABLE escala_respuesta (
    codigo   VARCHAR(10)  NOT NULL PRIMARY KEY,
    etiqueta VARCHAR(40)  NOT NULL,
    valor    DECIMAL(3,2) NOT NULL CHECK (valor BETWEEN -1 AND 1),
    orden    INTEGER      NOT NULL,
    color    CHAR(7)      NOT NULL
);

CREATE TABLE diagnostico (
    id              INTEGER      NOT NULL PRIMARY KEY,
    incidente_id    INTEGER      NULL REFERENCES incidente (id),
    ronda           INTEGER      NOT NULL DEFAULT 1,
    registrado_por  INTEGER      NULL REFERENCES usuario (id),
    estado          VARCHAR(10)  NOT NULL DEFAULT 'EN_CURSO' CHECK (estado IN ('EN_CURSO','FINALIZADO','CANCELADO')),
    total_preguntas INTEGER      NOT NULL DEFAULT 0,
    parametros      VARCHAR(200) NULL,
    equipo_texto    VARCHAR(40)  NULL,
    ubicacion_texto VARCHAR(100) NULL,
    descripcion     TEXT         NULL,
    fecha_inicio    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_fin       DATETIME     NULL,
    UNIQUE (incidente_id, ronda)
);

CREATE TABLE incidente_evidencia (
    id               INTEGER      NOT NULL PRIMARY KEY,
    diagnostico_id   INTEGER      NOT NULL REFERENCES diagnostico (id),
    orden            INTEGER      NOT NULL,
    evidencia_codigo CHAR(5)      NOT NULL,
    escala_codigo    VARCHAR(10)  NOT NULL REFERENCES escala_respuesta (codigo),
    valor            DECIMAL(3,2) NOT NULL CHECK (valor BETWEEN -1 AND 1),
    origen           VARCHAR(15)  NOT NULL CHECK (origen IN ('SINTOMA_INICIAL','PREGUNTA')),
    registrado_en    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (diagnostico_id, evidencia_codigo)
);

CREATE TABLE diagnostico_hipotesis (
    id               INTEGER      NOT NULL PRIMARY KEY,
    diagnostico_id   INTEGER      NOT NULL REFERENCES diagnostico (id),
    posicion         INTEGER      NOT NULL CHECK (posicion BETWEEN 1 AND 10),
    hipotesis_codigo CHAR(6)      NOT NULL,
    hipotesis_nombre VARCHAR(120) NOT NULL,
    granulo_codigo   VARCHAR(6)   NULL,
    granulo_version  INTEGER      NULL,
    conclusion       VARCHAR(250) NULL,
    accion           VARCHAR(500) NULL,
    probabilidad     DECIMAL(6,5) NOT NULL CHECK (probabilidad BETWEEN 0 AND 1),
    certeza          DECIMAL(6,4) NOT NULL CHECK (certeza BETWEEN -1 AND 1),
    estado           VARCHAR(10)  NOT NULL DEFAULT 'PROPUESTA' CHECK (estado IN ('PROPUESTA','CONFIRMADA','DESCARTADA')),
    UNIQUE (diagnostico_id, posicion)
);

CREATE TABLE intervencion (
    id                       INTEGER      NOT NULL PRIMARY KEY,
    diagnostico_hipotesis_id INTEGER      NOT NULL UNIQUE REFERENCES diagnostico_hipotesis (id),
    administrador_id         INTEGER      NOT NULL REFERENCES usuario (id),
    accion_aplicada          VARCHAR(500) NOT NULL,
    resultado                VARCHAR(15)  NOT NULL CHECK (resultado IN ('SOLUCIONADO','NO_SOLUCIONADO')),
    tiempo_min               INTEGER      NULL CHECK (tiempo_min IS NULL OR tiempo_min >= 0),
    observaciones            TEXT         NULL,
    registrado_en            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------- conocimiento
CREATE TABLE auditoria_conocimiento (
    id         INTEGER    NOT NULL PRIMARY KEY,
    entidad    VARCHAR(9) NOT NULL CHECK (entidad IN ('HIPOTESIS','EVIDENCIA','GRANULO')),
    codigo     VARCHAR(6) NULL,
    version    INTEGER    NULL,
    accion     VARCHAR(13) NOT NULL CHECK (accion IN ('CREAR','MODIFICAR','ACTIVAR','DESACTIVAR','CARGA_INICIAL')),
    usuario_id INTEGER    NULL REFERENCES usuario (id),
    fecha      DATETIME   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    detalle    TEXT       NULL
);
CREATE INDEX ix_auditoria_codigo ON auditoria_conocimiento (codigo);

-- =====================================================================
-- Disparadores de integridad
-- =====================================================================

-- Nada se elimina.
CREATE TRIGGER tr_rol_no_borrar BEFORE DELETE ON rol BEGIN SELECT RAISE(ABORT, 'Los registros no se eliminan.'); END;
CREATE TRIGGER tr_modulo_no_borrar BEFORE DELETE ON modulo BEGIN SELECT RAISE(ABORT, 'Los registros no se eliminan.'); END;
CREATE TRIGGER tr_rol_permiso_no_borrar BEFORE DELETE ON rol_permiso BEGIN SELECT RAISE(ABORT, 'Los registros no se eliminan.'); END;
CREATE TRIGGER tr_dependencia_no_borrar BEFORE DELETE ON dependencia BEGIN SELECT RAISE(ABORT, 'Las dependencias no se eliminan: desactívelas.'); END;
CREATE TRIGGER tr_usuario_no_borrar BEFORE DELETE ON usuario BEGIN SELECT RAISE(ABORT, 'Las cuentas no se eliminan: desactívelas.'); END;
CREATE TRIGGER tr_bitacora_no_borrar BEFORE DELETE ON bitacora_acceso BEGIN SELECT RAISE(ABORT, 'La bitácora de acceso no se elimina.'); END;
CREATE TRIGGER tr_tipo_equipo_no_borrar BEFORE DELETE ON tipo_equipo BEGIN SELECT RAISE(ABORT, 'Los registros no se eliminan.'); END;
CREATE TRIGGER tr_equipo_no_borrar BEFORE DELETE ON equipo BEGIN SELECT RAISE(ABORT, 'Los equipos no se eliminan: desactívelos.'); END;
CREATE TRIGGER tr_incidente_no_borrar BEFORE DELETE ON incidente BEGIN SELECT RAISE(ABORT, 'Los incidentes no se eliminan.'); END;
CREATE TRIGGER tr_historial_no_borrar BEFORE DELETE ON incidente_historial BEGIN SELECT RAISE(ABORT, 'El historial no se elimina.'); END;
CREATE TRIGGER tr_cita_no_borrar BEFORE DELETE ON cita BEGIN SELECT RAISE(ABORT, 'Las citas no se eliminan: cancélelas.'); END;
CREATE TRIGGER tr_escalamiento_no_borrar BEFORE DELETE ON escalamiento BEGIN SELECT RAISE(ABORT, 'Los escalamientos no se eliminan.'); END;
CREATE TRIGGER tr_escala_no_borrar BEFORE DELETE ON escala_respuesta BEGIN SELECT RAISE(ABORT, 'Los registros no se eliminan.'); END;
CREATE TRIGGER tr_diagnostico_no_borrar BEFORE DELETE ON diagnostico BEGIN SELECT RAISE(ABORT, 'Los diagnósticos no se eliminan.'); END;
CREATE TRIGGER tr_ie_no_borrar BEFORE DELETE ON incidente_evidencia BEGIN SELECT RAISE(ABORT, 'Las evidencias registradas no se eliminan.'); END;
CREATE TRIGGER tr_dh_no_borrar BEFORE DELETE ON diagnostico_hipotesis BEGIN SELECT RAISE(ABORT, 'Las hipótesis de un diagnóstico no se eliminan.'); END;
CREATE TRIGGER tr_intervencion_no_borrar BEFORE DELETE ON intervencion BEGIN SELECT RAISE(ABORT, 'Las intervenciones no se eliminan.'); END;
CREATE TRIGGER tr_auditoria_no_borrar BEFORE DELETE ON auditoria_conocimiento BEGIN SELECT RAISE(ABORT, 'La auditoría no se elimina.'); END;

-- Registros que solo se insertan.
CREATE TRIGGER tr_bitacora_solo_insertar BEFORE UPDATE ON bitacora_acceso BEGIN SELECT RAISE(ABORT, 'La bitácora de acceso no se modifica.'); END;
CREATE TRIGGER tr_historial_solo_insertar BEFORE UPDATE ON incidente_historial BEGIN SELECT RAISE(ABORT, 'El historial de un incidente no se modifica.'); END;
CREATE TRIGGER tr_intervencion_solo_insertar BEFORE UPDATE ON intervencion BEGIN SELECT RAISE(ABORT, 'Una intervención registrada no se modifica.'); END;
CREATE TRIGGER tr_escalamiento_solo_insertar BEFORE UPDATE ON escalamiento BEGIN SELECT RAISE(ABORT, 'Un escalamiento registrado no se modifica.'); END;
CREATE TRIGGER tr_auditoria_solo_insertar BEFORE UPDATE ON auditoria_conocimiento BEGIN SELECT RAISE(ABORT, 'La auditoría no se modifica.'); END;

-- Códigos que no cambian.
CREATE TRIGGER tr_equipo_inventario_fijo BEFORE UPDATE OF inventario ON equipo WHEN NEW.inventario <> OLD.inventario
BEGIN SELECT RAISE(ABORT, 'El código de inventario no se puede modificar.'); END;

-- Un incidente nuevo nace ABIERTO y su primer estado queda en el historial.
CREATE TRIGGER tr_incidente_nuevo BEFORE INSERT ON incidente WHEN NEW.estado <> 'ABIERTO' OR NEW.fecha_cierre IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'Un incidente nuevo siempre nace ABIERTO.'); END;
CREATE TRIGGER tr_incidente_historial_inicial AFTER INSERT ON incidente
BEGIN
    INSERT INTO incidente_historial (incidente_id, estado_anterior, estado_nuevo, usuario_id, cambiado_en)
    VALUES (NEW.id, NULL, NEW.estado, NEW.solicitante_id, NEW.fecha_apertura);
END;

-- Un incidente cerrado o escalado no se modifica; el cierre exige una intervención SOLUCIONADO
-- y el escalamiento un registro con motivo y destino.
CREATE TRIGGER tr_incidente_codigo_fijo BEFORE UPDATE OF codigo ON incidente
WHEN OLD.codigo IS NOT NULL AND (NEW.codigo IS NULL OR NEW.codigo <> OLD.codigo)
BEGIN SELECT RAISE(ABORT, 'El consecutivo del incidente no se puede modificar.'); END;
CREATE TRIGGER tr_incidente_cerrado BEFORE UPDATE ON incidente WHEN OLD.estado = 'CERRADO'
BEGIN SELECT RAISE(ABORT, 'Un incidente cerrado no admite cambios.'); END;
CREATE TRIGGER tr_incidente_escalado BEFORE UPDATE ON incidente WHEN OLD.estado = 'ESCALADO'
BEGIN SELECT RAISE(ABORT, 'Un incidente escalado no admite cambios en este nivel.'); END;
CREATE TRIGGER tr_incidente_cierre BEFORE UPDATE OF estado ON incidente
WHEN NEW.estado = 'CERRADO' AND OLD.estado <> 'CERRADO' AND NOT EXISTS (
    SELECT 1 FROM intervencion i
      JOIN diagnostico_hipotesis dh ON dh.id = i.diagnostico_hipotesis_id
      JOIN diagnostico d ON d.id = dh.diagnostico_id
     WHERE d.incidente_id = OLD.id AND i.resultado = 'SOLUCIONADO')
BEGIN SELECT RAISE(ABORT, 'Un incidente solo se cierra con una intervención SOLUCIONADO.'); END;
CREATE TRIGGER tr_incidente_escalamiento BEFORE UPDATE OF estado ON incidente
WHEN NEW.estado = 'ESCALADO' AND OLD.estado <> 'ESCALADO'
 AND NOT EXISTS (SELECT 1 FROM escalamiento e WHERE e.incidente_id = OLD.id)
BEGIN SELECT RAISE(ABORT, 'Un incidente escalado debe tener motivo y destino registrados.'); END;
CREATE TRIGGER tr_incidente_historial AFTER UPDATE OF estado ON incidente WHEN NEW.estado <> OLD.estado
BEGIN
    INSERT INTO incidente_historial (incidente_id, estado_anterior, estado_nuevo, usuario_id, cambiado_en)
    VALUES (NEW.id, OLD.estado, NEW.estado, NEW.actualizado_por, COALESCE(NEW.actualizado_en, CURRENT_TIMESTAMP));
END;

-- Un administrador no puede tener dos citas programadas que se solapen.
CREATE TRIGGER tr_cita_solape_insertar BEFORE INSERT ON cita
WHEN NEW.estado = 'PROGRAMADA' AND EXISTS (
    SELECT 1 FROM cita c WHERE c.administrador_id = NEW.administrador_id AND c.estado = 'PROGRAMADA'
       AND c.inicio < NEW.fin AND NEW.inicio < c.fin)
BEGIN SELECT RAISE(ABORT, 'El administrador ya tiene una cita en ese horario.'); END;
CREATE TRIGGER tr_cita_incidente_abierto BEFORE INSERT ON cita
WHEN (SELECT estado FROM incidente WHERE id = NEW.incidente_id) IN ('CERRADO', 'ESCALADO')
BEGIN SELECT RAISE(ABORT, 'No se programan citas sobre un incidente cerrado o escalado.'); END;
CREATE TRIGGER tr_cita_solo_programada BEFORE UPDATE ON cita WHEN OLD.estado <> 'PROGRAMADA'
BEGIN SELECT RAISE(ABORT, 'Solo se modifica una cita PROGRAMADA.'); END;
CREATE TRIGGER tr_cita_solape_modificar BEFORE UPDATE ON cita
WHEN NEW.estado = 'PROGRAMADA' AND EXISTS (
    SELECT 1 FROM cita c WHERE c.id <> OLD.id AND c.administrador_id = NEW.administrador_id
       AND c.estado = 'PROGRAMADA' AND c.inicio < NEW.fin AND NEW.inicio < c.fin)
BEGIN SELECT RAISE(ABORT, 'El administrador ya tiene una cita en ese horario.'); END;

-- La ronda de un diagnóstico es la siguiente del incidente; no se diagnostica un incidente cerrado o escalado.
CREATE TRIGGER tr_diagnostico_incidente_abierto BEFORE INSERT ON diagnostico
WHEN NEW.incidente_id IS NOT NULL AND (SELECT estado FROM incidente WHERE id = NEW.incidente_id) IN ('CERRADO', 'ESCALADO')
BEGIN SELECT RAISE(ABORT, 'Un incidente cerrado o escalado no admite diagnósticos nuevos.'); END;
CREATE TRIGGER tr_diagnostico_ronda BEFORE INSERT ON diagnostico
WHEN NEW.incidente_id IS NOT NULL
 AND NEW.ronda <> (SELECT COALESCE(MAX(ronda), 0) + 1 FROM diagnostico WHERE incidente_id = NEW.incidente_id)
BEGIN SELECT RAISE(ABORT, 'La ronda del diagnóstico debe ser la siguiente del incidente.'); END;

-- Un diagnóstico tiene a lo sumo una hipótesis CONFIRMADA y lo que propuso el motor no cambia.
CREATE TRIGGER tr_dh_una_confirmada BEFORE UPDATE OF estado ON diagnostico_hipotesis
WHEN NEW.estado = 'CONFIRMADA' AND OLD.estado <> 'CONFIRMADA' AND EXISTS (
    SELECT 1 FROM diagnostico_hipotesis WHERE diagnostico_id = NEW.diagnostico_id AND estado = 'CONFIRMADA' AND id <> OLD.id)
BEGIN SELECT RAISE(ABORT, 'El diagnóstico ya tiene una hipótesis confirmada.'); END;
CREATE TRIGGER tr_dh_propuesta_fija BEFORE UPDATE ON diagnostico_hipotesis
WHEN NEW.hipotesis_codigo <> OLD.hipotesis_codigo OR NEW.probabilidad <> OLD.probabilidad OR NEW.certeza <> OLD.certeza
  OR COALESCE(NEW.granulo_codigo, '') <> COALESCE(OLD.granulo_codigo, '')
BEGIN SELECT RAISE(ABORT, 'Lo que propuso el motor no se modifica; solo cambia la decisión.'); END;

-- La intervención solo se registra sobre la hipótesis confirmada.
CREATE TRIGGER tr_intervencion_confirmada BEFORE INSERT ON intervencion
WHEN (SELECT estado FROM diagnostico_hipotesis WHERE id = NEW.diagnostico_hipotesis_id) <> 'CONFIRMADA'
BEGIN SELECT RAISE(ABORT, 'La intervención solo se registra sobre la hipótesis confirmada.'); END;
