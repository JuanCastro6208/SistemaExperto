-- =====================================================================
-- SEDATI - Base transaccional (sedati_trx) para MySQL 8.0 (InnoDB, utf8mb4)
--
-- Registra la atención de los usuarios: cuentas y roles, equipos, incidentes, citas,
-- diagnósticos del motor de inferencia, intervenciones, escalamientos y auditoría.
-- No tiene llaves foráneas hacia sedati_kb: la une por los códigos estables HIP-, E-, R-
-- y la letra de la categoría, que la base de conocimiento nunca modifica.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS sedati_trx CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE sedati_trx;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS auditoria_conocimiento;
DROP TABLE IF EXISTS escalamiento;
DROP TABLE IF EXISTS intervencion;
DROP TABLE IF EXISTS diagnostico_hipotesis;
DROP TABLE IF EXISTS incidente_evidencia;
DROP TABLE IF EXISTS diagnostico;
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
DROP TABLE IF EXISTS escala_respuesta;
SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------
-- Seguridad (RF-01)
-- ---------------------------------------------------------------------
CREATE TABLE rol (
    id          TINYINT UNSIGNED NOT NULL,
    codigo      VARCHAR(20)      NOT NULL COMMENT 'ADMINISTRADOR o SOLICITANTE, no cambia',
    nombre      VARCHAR(40)      NOT NULL,
    descripcion VARCHAR(250)     NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_rol_codigo (codigo),
    UNIQUE KEY uk_rol_nombre (nombre)
) ENGINE = InnoDB COMMENT = 'Roles del sistema';

CREATE TABLE modulo (
    id     TINYINT UNSIGNED NOT NULL,
    codigo VARCHAR(20)      NOT NULL,
    nombre VARCHAR(60)      NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_modulo_codigo (codigo)
) ENGINE = InnoDB COMMENT = 'Módulos de la aplicación sobre los que se otorgan permisos';

CREATE TABLE rol_permiso (
    rol_id          TINYINT UNSIGNED NOT NULL,
    modulo_id       TINYINT UNSIGNED NOT NULL,
    puede_consultar TINYINT(1)       NOT NULL DEFAULT 0,
    puede_crear     TINYINT(1)       NOT NULL DEFAULT 0,
    puede_modificar TINYINT(1)       NOT NULL DEFAULT 0,
    PRIMARY KEY (rol_id, modulo_id),
    CONSTRAINT fk_permiso_rol    FOREIGN KEY (rol_id)    REFERENCES rol (id),
    CONSTRAINT fk_permiso_modulo FOREIGN KEY (modulo_id) REFERENCES modulo (id),
    CONSTRAINT ck_permiso_crear     CHECK (puede_crear = 0 OR puede_consultar = 1),
    CONSTRAINT ck_permiso_modificar CHECK (puede_modificar = 0 OR puede_consultar = 1)
) ENGINE = InnoDB COMMENT = 'Matriz de permisos (capítulo de roles)';

CREATE TABLE dependencia (
    id     SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre VARCHAR(100)      NOT NULL,
    activo TINYINT(1)        NOT NULL DEFAULT 1,
    PRIMARY KEY (id),
    UNIQUE KEY uk_dependencia_nombre (nombre)
) ENGINE = InnoDB;

CREATE TABLE usuario (
    id                      INT UNSIGNED      NOT NULL AUTO_INCREMENT,
    rol_id                  TINYINT UNSIGNED  NOT NULL,
    dependencia_id          SMALLINT UNSIGNED NULL,
    documento               VARCHAR(20)       NOT NULL,
    nombre                  VARCHAR(120)      NOT NULL,
    correo                  VARCHAR(120)      NOT NULL COMMENT 'Se usa para ingresar',
    contrasena_hash         VARCHAR(255)      NOT NULL COMMENT 'PBKDF2-HMAC-SHA256 con sal; nunca texto plano',
    debe_cambiar_contrasena TINYINT(1)        NOT NULL DEFAULT 1,
    activo                  TINYINT(1)        NOT NULL DEFAULT 1,
    intentos_fallidos       TINYINT UNSIGNED  NOT NULL DEFAULT 0,
    bloqueado_hasta         DATETIME          NULL,
    ultimo_ingreso          DATETIME          NULL,
    creado_en               DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_usuario_documento (documento),
    UNIQUE KEY uk_usuario_correo (correo),
    CONSTRAINT fk_usuario_rol         FOREIGN KEY (rol_id)         REFERENCES rol (id),
    CONSTRAINT fk_usuario_dependencia FOREIGN KEY (dependencia_id) REFERENCES dependencia (id),
    CONSTRAINT ck_usuario_hash CHECK (contrasena_hash LIKE 'pbkdf2_sha256$%')
) ENGINE = InnoDB COMMENT = 'Cuentas de usuario';

CREATE TABLE bitacora_acceso (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    usuario_id       INT UNSIGNED    NULL COMMENT 'Nulo si el correo no existe',
    correo_intentado VARCHAR(120)    NOT NULL,
    exitoso          TINYINT(1)      NOT NULL,
    motivo           VARCHAR(40)     NOT NULL COMMENT 'OK, CREDENCIALES, BLOQUEADA, INACTIVA',
    ip               VARCHAR(45)     NULL,
    fecha            DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY ix_bitacora_usuario (usuario_id),
    CONSTRAINT fk_bitacora_usuario FOREIGN KEY (usuario_id) REFERENCES usuario (id)
) ENGINE = InnoDB COMMENT = 'Intentos de ingreso; solo se inserta';

-- ---------------------------------------------------------------------
-- Equipos (RF-02)
-- ---------------------------------------------------------------------
CREATE TABLE tipo_equipo (
    id     TINYINT UNSIGNED NOT NULL,
    codigo VARCHAR(20)      NOT NULL,
    nombre VARCHAR(60)      NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_tipo_equipo_codigo (codigo)
) ENGINE = InnoDB;

CREATE TABLE equipo (
    id             INT UNSIGNED      NOT NULL AUTO_INCREMENT,
    inventario     VARCHAR(20)       NOT NULL COMMENT 'Código de inventario, no cambia',
    tipo_equipo_id TINYINT UNSIGNED  NOT NULL,
    dependencia_id SMALLINT UNSIGNED NULL,
    marca          VARCHAR(60)       NULL,
    modelo         VARCHAR(60)       NULL,
    ubicacion      VARCHAR(100)      NOT NULL,
    activo         TINYINT(1)        NOT NULL DEFAULT 1,
    PRIMARY KEY (id),
    UNIQUE KEY uk_equipo_inventario (inventario),
    CONSTRAINT fk_equipo_tipo        FOREIGN KEY (tipo_equipo_id) REFERENCES tipo_equipo (id),
    CONSTRAINT fk_equipo_dependencia FOREIGN KEY (dependencia_id) REFERENCES dependencia (id)
) ENGINE = InnoDB COMMENT = 'Inventario de equipos';

-- ---------------------------------------------------------------------
-- Atención del incidente (RF-02)
-- ---------------------------------------------------------------------
CREATE TABLE incidente (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    codigo           CHAR(15)        NULL COMMENT 'INC-AAAA-NNNNNN, lo asigna la capa DAO al crear el incidente',
    solicitante_id   INT UNSIGNED    NOT NULL,
    administrador_id INT UNSIGNED    NULL COMMENT 'Responsable de la atención',
    equipo_id        INT UNSIGNED    NOT NULL,
    ubicacion        VARCHAR(100)    NOT NULL,
    descripcion      TEXT            NOT NULL,
    categoria_codigo CHAR(1)         NULL COMMENT 'Categoría del árbol (A a G) de sedati_kb',
    estado           ENUM('ABIERTO','EN_DIAGNOSTICO','ESCALADO','CERRADO') NOT NULL DEFAULT 'ABIERTO',
    fecha_apertura   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_cierre     DATETIME        NULL,
    actualizado_por  INT UNSIGNED    NULL COMMENT 'Último usuario que lo modificó (lo usa el historial)',
    actualizado_en   DATETIME        NULL COMMENT 'Hora local del último cambio (la envía la aplicación)',
    PRIMARY KEY (id),
    UNIQUE KEY uk_incidente_codigo (codigo),
    KEY ix_incidente_estado (estado),
    KEY ix_incidente_equipo (equipo_id),
    CONSTRAINT fk_incidente_solicitante   FOREIGN KEY (solicitante_id)   REFERENCES usuario (id),
    CONSTRAINT fk_incidente_administrador FOREIGN KEY (administrador_id) REFERENCES usuario (id),
    CONSTRAINT fk_incidente_equipo        FOREIGN KEY (equipo_id)        REFERENCES equipo (id),
    CONSTRAINT fk_incidente_actualizado   FOREIGN KEY (actualizado_por)  REFERENCES usuario (id),
    CONSTRAINT ck_incidente_categoria CHECK (categoria_codigo IS NULL OR categoria_codigo BETWEEN 'A' AND 'G'),
    CONSTRAINT ck_incidente_cierre CHECK ((estado = 'CERRADO') = (fecha_cierre IS NOT NULL))
) ENGINE = InnoDB COMMENT = 'Reporte de falla sobre un equipo';

CREATE TABLE incidente_historial (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    incidente_id    BIGINT UNSIGNED NOT NULL,
    estado_anterior ENUM('ABIERTO','EN_DIAGNOSTICO','ESCALADO','CERRADO') NULL,
    estado_nuevo    ENUM('ABIERTO','EN_DIAGNOSTICO','ESCALADO','CERRADO') NOT NULL,
    usuario_id      INT UNSIGNED    NULL,
    cambiado_en     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY ix_historial_incidente (incidente_id),
    CONSTRAINT fk_historial_incidente FOREIGN KEY (incidente_id) REFERENCES incidente (id),
    CONSTRAINT fk_historial_usuario   FOREIGN KEY (usuario_id)   REFERENCES usuario (id)
) ENGINE = InnoDB COMMENT = 'Cambios de estado; lo llena un disparador';

CREATE TABLE cita (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    incidente_id     BIGINT UNSIGNED NOT NULL,
    administrador_id INT UNSIGNED    NOT NULL,
    inicio           DATETIME        NOT NULL,
    fin              DATETIME        NOT NULL,
    lugar            VARCHAR(100)    NOT NULL,
    estado           ENUM('PROGRAMADA','ATENDIDA','CANCELADA','NO_ASISTIO') NOT NULL DEFAULT 'PROGRAMADA',
    creado_por       INT UNSIGNED    NOT NULL,
    creado_en        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY ix_cita_administrador (administrador_id, inicio),
    CONSTRAINT fk_cita_incidente     FOREIGN KEY (incidente_id)     REFERENCES incidente (id),
    CONSTRAINT fk_cita_administrador FOREIGN KEY (administrador_id) REFERENCES usuario (id),
    CONSTRAINT fk_cita_creador       FOREIGN KEY (creado_por)       REFERENCES usuario (id),
    CONSTRAINT ck_cita_horario CHECK (fin > inicio)
) ENGINE = InnoDB COMMENT = 'Visitas para atender un incidente';

CREATE TABLE escalamiento (
    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    incidente_id BIGINT UNSIGNED NOT NULL,
    motivo       TEXT            NOT NULL,
    destino      VARCHAR(100)    NOT NULL,
    escalado_por INT UNSIGNED    NOT NULL,
    escalado_en  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_escalamiento_incidente FOREIGN KEY (incidente_id) REFERENCES incidente (id),
    CONSTRAINT fk_escalamiento_usuario   FOREIGN KEY (escalado_por) REFERENCES usuario (id)
) ENGINE = InnoDB COMMENT = 'Incidentes que pasaron a otra área';

-- ---------------------------------------------------------------------
-- Diagnóstico y solución (RF-02)
-- ---------------------------------------------------------------------
CREATE TABLE escala_respuesta (
    codigo   VARCHAR(10)  NOT NULL,
    etiqueta VARCHAR(40)  NOT NULL,
    valor    DECIMAL(3,2) NOT NULL COMMENT 'Certeza de la observación, de -1 (falsa) a +1 (verdadera)',
    orden    TINYINT      NOT NULL,
    color    CHAR(7)      NOT NULL,
    PRIMARY KEY (codigo),
    CONSTRAINT ck_escala_valor CHECK (valor BETWEEN -1 AND 1)
) ENGINE = InnoDB COMMENT = 'Respuestas graduadas (no solo sí / no)';

CREATE TABLE diagnostico (
    id              BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
    incidente_id    BIGINT UNSIGNED   NULL COMMENT 'Nulo en una consulta libre (sin incidente)',
    ronda           TINYINT UNSIGNED  NOT NULL DEFAULT 1,
    registrado_por  INT UNSIGNED      NULL COMMENT 'Administrador que ejecutó el motor',
    estado          ENUM('EN_CURSO','FINALIZADO','CANCELADO') NOT NULL DEFAULT 'EN_CURSO',
    total_preguntas SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    parametros      VARCHAR(200)      NULL COMMENT 'Parámetros del motor usados',
    equipo_texto    VARCHAR(40)       NULL COMMENT 'Equipo escrito en una consulta libre',
    ubicacion_texto VARCHAR(100)      NULL,
    descripcion     TEXT              NULL,
    fecha_inicio    DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_fin       DATETIME          NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_diagnostico_ronda (incidente_id, ronda),
    CONSTRAINT fk_diagnostico_incidente FOREIGN KEY (incidente_id)   REFERENCES incidente (id),
    CONSTRAINT fk_diagnostico_usuario   FOREIGN KEY (registrado_por) REFERENCES usuario (id)
) ENGINE = InnoDB COMMENT = 'Cada ejecución del motor de inferencia';

CREATE TABLE incidente_evidencia (
    id               BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
    diagnostico_id   BIGINT UNSIGNED   NOT NULL,
    orden            SMALLINT UNSIGNED NOT NULL,
    evidencia_codigo CHAR(5)           NOT NULL COMMENT 'E-NNN de sedati_kb',
    escala_codigo    VARCHAR(10)       NOT NULL,
    valor            DECIMAL(3,2)      NOT NULL,
    origen           ENUM('SINTOMA_INICIAL','PREGUNTA') NOT NULL,
    registrado_en    DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_evidencia_diagnostico (diagnostico_id, evidencia_codigo),
    CONSTRAINT fk_ie_diagnostico FOREIGN KEY (diagnostico_id) REFERENCES diagnostico (id),
    CONSTRAINT fk_ie_escala      FOREIGN KEY (escala_codigo)  REFERENCES escala_respuesta (codigo),
    CONSTRAINT ck_ie_valor CHECK (valor BETWEEN -1 AND 1)
) ENGINE = InnoDB COMMENT = 'Síntomas y resultados de pruebas observados en cada ronda';

CREATE TABLE diagnostico_hipotesis (
    id               BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    diagnostico_id   BIGINT UNSIGNED  NOT NULL,
    posicion         TINYINT UNSIGNED NOT NULL,
    hipotesis_codigo CHAR(6)          NOT NULL COMMENT 'HIP-NN de sedati_kb',
    hipotesis_nombre VARCHAR(120)     NOT NULL COMMENT 'Copiado al momento del diagnóstico',
    granulo_codigo   VARCHAR(6)       NULL     COMMENT 'Regla R-NN que más la sostiene',
    granulo_version  INT UNSIGNED     NULL,
    conclusion       VARCHAR(250)     NULL,
    accion           VARCHAR(500)     NULL,
    probabilidad     DECIMAL(6,5)     NOT NULL COMMENT 'Peso probabilístico (0 a 1)',
    certeza          DECIMAL(6,4)     NOT NULL COMMENT 'Factor de certeza combinado (-1 a 1)',
    estado           ENUM('PROPUESTA','CONFIRMADA','DESCARTADA') NOT NULL DEFAULT 'PROPUESTA',
    PRIMARY KEY (id),
    UNIQUE KEY uk_dh_posicion (diagnostico_id, posicion),
    CONSTRAINT fk_dh_diagnostico FOREIGN KEY (diagnostico_id) REFERENCES diagnostico (id),
    CONSTRAINT ck_dh_probabilidad CHECK (probabilidad BETWEEN 0 AND 1),
    CONSTRAINT ck_dh_certeza CHECK (certeza BETWEEN -1 AND 1),
    CONSTRAINT ck_dh_posicion CHECK (posicion BETWEEN 1 AND 10)
) ENGINE = InnoDB COMMENT = 'Hipótesis que propuso el motor en cada ronda';

CREATE TABLE intervencion (
    id                       BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
    diagnostico_hipotesis_id BIGINT UNSIGNED   NOT NULL,
    administrador_id         INT UNSIGNED      NOT NULL,
    accion_aplicada          VARCHAR(500)      NOT NULL,
    resultado                ENUM('SOLUCIONADO','NO_SOLUCIONADO') NOT NULL,
    tiempo_min               SMALLINT UNSIGNED NULL,
    observaciones            TEXT              NULL,
    registrado_en            DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_intervencion_hipotesis (diagnostico_hipotesis_id),
    CONSTRAINT fk_intervencion_dh      FOREIGN KEY (diagnostico_hipotesis_id) REFERENCES diagnostico_hipotesis (id),
    CONSTRAINT fk_intervencion_usuario FOREIGN KEY (administrador_id)         REFERENCES usuario (id)
) ENGINE = InnoDB COMMENT = 'Solución aplicada y su resultado';

-- ---------------------------------------------------------------------
-- Conocimiento (RF-03)
-- ---------------------------------------------------------------------
CREATE TABLE auditoria_conocimiento (
    id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    entidad    ENUM('HIPOTESIS','EVIDENCIA','GRANULO') NOT NULL,
    codigo     VARCHAR(6)      NULL COMMENT 'HIP-, E- o R-; nulo en una carga masiva',
    version    INT UNSIGNED    NULL,
    accion     ENUM('CREAR','MODIFICAR','ACTIVAR','DESACTIVAR','CARGA_INICIAL') NOT NULL,
    usuario_id INT UNSIGNED    NULL COMMENT 'Administrador que hizo el cambio',
    fecha      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    detalle    TEXT            NULL COMMENT 'Valores anterior y nuevo (JSON)',
    PRIMARY KEY (id),
    KEY ix_auditoria_codigo (codigo),
    CONSTRAINT fk_auditoria_usuario FOREIGN KEY (usuario_id) REFERENCES usuario (id)
) ENGINE = InnoDB COMMENT = 'Quién cambió el conocimiento y cuándo';

-- =====================================================================
-- Disparadores de integridad
-- =====================================================================
DELIMITER $$

-- Nada se elimina: el DELETE se rechaza en todas las tablas.
CREATE TRIGGER tr_rol_no_borrar BEFORE DELETE ON rol FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Los registros no se eliminan.'$$
CREATE TRIGGER tr_modulo_no_borrar BEFORE DELETE ON modulo FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Los registros no se eliminan.'$$
CREATE TRIGGER tr_rol_permiso_no_borrar BEFORE DELETE ON rol_permiso FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Los registros no se eliminan.'$$
CREATE TRIGGER tr_dependencia_no_borrar BEFORE DELETE ON dependencia FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Las dependencias no se eliminan: desactívelas.'$$
CREATE TRIGGER tr_usuario_no_borrar BEFORE DELETE ON usuario FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Las cuentas no se eliminan: desactívelas.'$$
CREATE TRIGGER tr_bitacora_no_borrar BEFORE DELETE ON bitacora_acceso FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La bitácora de acceso no se elimina.'$$
CREATE TRIGGER tr_tipo_equipo_no_borrar BEFORE DELETE ON tipo_equipo FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Los registros no se eliminan.'$$
CREATE TRIGGER tr_equipo_no_borrar BEFORE DELETE ON equipo FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Los equipos no se eliminan: desactívelos.'$$
CREATE TRIGGER tr_incidente_no_borrar BEFORE DELETE ON incidente FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Los incidentes no se eliminan.'$$
CREATE TRIGGER tr_historial_no_borrar BEFORE DELETE ON incidente_historial FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El historial no se elimina.'$$
CREATE TRIGGER tr_cita_no_borrar BEFORE DELETE ON cita FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Las citas no se eliminan: cancélelas.'$$
CREATE TRIGGER tr_escalamiento_no_borrar BEFORE DELETE ON escalamiento FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Los escalamientos no se eliminan.'$$
CREATE TRIGGER tr_escala_no_borrar BEFORE DELETE ON escala_respuesta FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Los registros no se eliminan.'$$
CREATE TRIGGER tr_diagnostico_no_borrar BEFORE DELETE ON diagnostico FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Los diagnósticos no se eliminan.'$$
CREATE TRIGGER tr_ie_no_borrar BEFORE DELETE ON incidente_evidencia FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Las evidencias registradas no se eliminan.'$$
CREATE TRIGGER tr_dh_no_borrar BEFORE DELETE ON diagnostico_hipotesis FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Las hipótesis de un diagnóstico no se eliminan.'$$
CREATE TRIGGER tr_intervencion_no_borrar BEFORE DELETE ON intervencion FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Las intervenciones no se eliminan.'$$
CREATE TRIGGER tr_auditoria_no_borrar BEFORE DELETE ON auditoria_conocimiento FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La auditoría no se elimina.'$$

-- Registros que solo se insertan.
CREATE TRIGGER tr_bitacora_solo_insertar BEFORE UPDATE ON bitacora_acceso FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La bitácora de acceso no se modifica.'$$
CREATE TRIGGER tr_historial_solo_insertar BEFORE UPDATE ON incidente_historial FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El historial de un incidente no se modifica.'$$
CREATE TRIGGER tr_intervencion_solo_insertar BEFORE UPDATE ON intervencion FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Una intervención registrada no se modifica.'$$
CREATE TRIGGER tr_escalamiento_solo_insertar BEFORE UPDATE ON escalamiento FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Un escalamiento registrado no se modifica.'$$
CREATE TRIGGER tr_auditoria_solo_insertar BEFORE UPDATE ON auditoria_conocimiento FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La auditoría no se modifica.'$$

-- Códigos que no cambian.
CREATE TRIGGER tr_equipo_inventario_fijo BEFORE UPDATE ON equipo FOR EACH ROW
BEGIN
    IF NEW.inventario <> OLD.inventario THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El código de inventario no se puede modificar.';
    END IF;
END$$

-- Un incidente nuevo siempre nace ABIERTO y su primer estado queda en el historial.
CREATE TRIGGER tr_incidente_nuevo BEFORE INSERT ON incidente FOR EACH ROW
BEGIN
    SET NEW.estado = 'ABIERTO', NEW.fecha_cierre = NULL;
END$$
CREATE TRIGGER tr_incidente_historial_inicial AFTER INSERT ON incidente FOR EACH ROW
BEGIN
    INSERT INTO incidente_historial (incidente_id, estado_anterior, estado_nuevo, usuario_id, cambiado_en)
    VALUES (NEW.id, NULL, NEW.estado, NEW.solicitante_id, NEW.fecha_apertura);
END$$

-- Un incidente cerrado o escalado no se modifica; cada cambio de estado queda en el historial.
CREATE TRIGGER tr_incidente_cambio BEFORE UPDATE ON incidente FOR EACH ROW
BEGIN
    IF OLD.codigo IS NOT NULL AND NOT (NEW.codigo <=> OLD.codigo) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El consecutivo del incidente no se puede modificar.';
    END IF;
    IF OLD.estado = 'CERRADO' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Un incidente cerrado no admite cambios.';
    END IF;
    IF OLD.estado = 'ESCALADO' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Un incidente escalado no admite cambios en este nivel.';
    END IF;
    IF NEW.estado = 'CERRADO' AND OLD.estado <> 'CERRADO' AND NOT EXISTS (
        SELECT 1 FROM intervencion i
          JOIN diagnostico_hipotesis dh ON dh.id = i.diagnostico_hipotesis_id
          JOIN diagnostico d ON d.id = dh.diagnostico_id
         WHERE d.incidente_id = OLD.id AND i.resultado = 'SOLUCIONADO') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Un incidente solo se cierra con una intervención SOLUCIONADO.';
    END IF;
    IF NEW.estado = 'ESCALADO' AND OLD.estado <> 'ESCALADO' AND NOT EXISTS (
        SELECT 1 FROM escalamiento e WHERE e.incidente_id = OLD.id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Un incidente escalado debe tener motivo y destino registrados.';
    END IF;
END$$
CREATE TRIGGER tr_incidente_historial AFTER UPDATE ON incidente FOR EACH ROW
BEGIN
    IF NEW.estado <> OLD.estado THEN
        INSERT INTO incidente_historial (incidente_id, estado_anterior, estado_nuevo, usuario_id, cambiado_en)
        VALUES (NEW.id, OLD.estado, NEW.estado, NEW.actualizado_por, COALESCE(NEW.actualizado_en, CURRENT_TIMESTAMP));
    END IF;
END$$

-- Un administrador no puede tener dos citas programadas que se solapen.
CREATE TRIGGER tr_cita_solape_insertar BEFORE INSERT ON cita FOR EACH ROW
BEGIN
    IF EXISTS (SELECT 1 FROM cita c
                WHERE c.administrador_id = NEW.administrador_id AND c.estado = 'PROGRAMADA'
                  AND NEW.estado = 'PROGRAMADA' AND c.inicio < NEW.fin AND NEW.inicio < c.fin) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El administrador ya tiene una cita en ese horario.';
    END IF;
    IF (SELECT estado FROM incidente WHERE id = NEW.incidente_id) IN ('CERRADO', 'ESCALADO') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No se programan citas sobre un incidente cerrado o escalado.';
    END IF;
END$$
CREATE TRIGGER tr_cita_solape_modificar BEFORE UPDATE ON cita FOR EACH ROW
BEGIN
    IF OLD.estado <> 'PROGRAMADA' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Solo se modifica una cita PROGRAMADA.';
    END IF;
    IF NEW.estado = 'PROGRAMADA' AND EXISTS (
        SELECT 1 FROM cita c
         WHERE c.id <> OLD.id AND c.administrador_id = NEW.administrador_id AND c.estado = 'PROGRAMADA'
           AND c.inicio < NEW.fin AND NEW.inicio < c.fin) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El administrador ya tiene una cita en ese horario.';
    END IF;
END$$

-- Cada diagnóstico de un incidente recibe la ronda siguiente y no se agrega a un incidente cerrado.
CREATE TRIGGER tr_diagnostico_ronda BEFORE INSERT ON diagnostico FOR EACH ROW
BEGIN
    IF NEW.incidente_id IS NOT NULL THEN
        IF (SELECT estado FROM incidente WHERE id = NEW.incidente_id) IN ('CERRADO', 'ESCALADO') THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Un incidente cerrado o escalado no admite diagnósticos nuevos.';
        END IF;
        SET NEW.ronda = (SELECT COALESCE(MAX(ronda), 0) + 1 FROM diagnostico WHERE incidente_id = NEW.incidente_id);
    END IF;
END$$

-- Un diagnóstico tiene a lo sumo una hipótesis CONFIRMADA.
CREATE TRIGGER tr_dh_una_confirmada BEFORE UPDATE ON diagnostico_hipotesis FOR EACH ROW
BEGIN
    IF NEW.estado = 'CONFIRMADA' AND OLD.estado <> 'CONFIRMADA' AND EXISTS (
        SELECT 1 FROM diagnostico_hipotesis
         WHERE diagnostico_id = NEW.diagnostico_id AND estado = 'CONFIRMADA' AND id <> OLD.id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El diagnóstico ya tiene una hipótesis confirmada.';
    END IF;
    IF NEW.hipotesis_codigo <> OLD.hipotesis_codigo OR NEW.probabilidad <> OLD.probabilidad
       OR NEW.certeza <> OLD.certeza OR NOT (NEW.granulo_codigo <=> OLD.granulo_codigo) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Lo que propuso el motor no se modifica; solo cambia la decisión.';
    END IF;
END$$

-- La intervención solo se registra sobre la hipótesis confirmada.
CREATE TRIGGER tr_intervencion_confirmada BEFORE INSERT ON intervencion FOR EACH ROW
BEGIN
    IF (SELECT estado FROM diagnostico_hipotesis WHERE id = NEW.diagnostico_hipotesis_id) <> 'CONFIRMADA' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La intervención solo se registra sobre la hipótesis confirmada.';
    END IF;
END$$

DELIMITER ;
