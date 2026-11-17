-- =====================================================================
-- SEDATI - Base transaccional (sedati_trx) para MySQL 8.0 (InnoDB, utf8mb4)
--
-- Registra las cuentas de usuario (un solo tipo de cuenta, sin roles) y cada consulta al sistema
-- experto: quién consultó, lo que respondió y las hipótesis que propuso el motor de inferencia.
-- No tiene llaves foráneas hacia sedati_kb: la une por los códigos estables HIP-, E-, R-
-- y la letra de la categoría, que la base de conocimiento nunca modifica.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS sedati_trx CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE sedati_trx;

SET FOREIGN_KEY_CHECKS = 0;
-- Tablas de versiones anteriores (roles, incidentes, citas…), por si la base ya existía.
DROP TABLE IF EXISTS auditoria_conocimiento;
DROP TABLE IF EXISTS escalamiento;
DROP TABLE IF EXISTS intervencion;
DROP TABLE IF EXISTS cita;
DROP TABLE IF EXISTS incidente_historial;
DROP TABLE IF EXISTS incidente;
DROP TABLE IF EXISTS equipo;
DROP TABLE IF EXISTS tipo_equipo;
DROP TABLE IF EXISTS bitacora_acceso;
DROP TABLE IF EXISTS dependencia;
DROP TABLE IF EXISTS rol_permiso;
DROP TABLE IF EXISTS modulo;
DROP TABLE IF EXISTS rol;
-- Tablas actuales.
DROP TABLE IF EXISTS diagnostico_hipotesis;
DROP TABLE IF EXISTS incidente_evidencia;
DROP TABLE IF EXISTS diagnostico;
DROP TABLE IF EXISTS usuario;
DROP TABLE IF EXISTS escala_respuesta;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE escala_respuesta (
    codigo   VARCHAR(10)  NOT NULL,
    etiqueta VARCHAR(40)  NOT NULL,
    valor    DECIMAL(3,2) NOT NULL COMMENT 'Certeza de la observación, de -1 (falsa) a +1 (verdadera)',
    orden    TINYINT      NOT NULL,
    color    CHAR(7)      NOT NULL,
    PRIMARY KEY (codigo),
    CONSTRAINT ck_escala_valor CHECK (valor BETWEEN -1 AND 1)
) ENGINE = InnoDB COMMENT = 'Respuestas graduadas (no solo sí / no)';

CREATE TABLE usuario (
    id                BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    nombre            VARCHAR(80)      NOT NULL,
    correo            VARCHAR(120)     NOT NULL COMMENT 'Se guarda en minúsculas; con él se inicia sesión',
    contrasena_hash   VARCHAR(255)     NOT NULL COMMENT 'PBKDF2-HMAC-SHA256 con sal; nunca la contraseña',
    intentos_fallidos TINYINT UNSIGNED NOT NULL DEFAULT 0,
    bloqueado_hasta   DATETIME         NULL COMMENT 'Bloqueo temporal tras 5 intentos fallidos',
    ultimo_ingreso    DATETIME         NULL,
    creado_en         DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_usuario_correo (correo),
    CONSTRAINT ck_usuario_nombre CHECK (CHAR_LENGTH(TRIM(nombre)) > 1),
    CONSTRAINT ck_usuario_hash CHECK (contrasena_hash LIKE 'pbkdf2_sha256$%')
) ENGINE = InnoDB COMMENT = 'Cuentas de usuario (un solo tipo de cuenta, sin roles)';

CREATE TABLE diagnostico (
    id               BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
    usuario_id       BIGINT UNSIGNED   NULL     COMMENT 'Cuenta con la que se inició sesión',
    nombre_usuario   VARCHAR(80)       NOT NULL COMMENT 'Nombre de la cuenta al momento del diagnóstico',
    categoria_codigo CHAR(1)           NULL     COMMENT 'Categoría del árbol que eligió (A a G)',
    estado           ENUM('EN_CURSO','FINALIZADO','CANCELADO') NOT NULL DEFAULT 'EN_CURSO',
    total_preguntas  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    parametros       VARCHAR(200)      NULL COMMENT 'Parámetros del motor usados',
    equipo_texto     VARCHAR(40)       NULL,
    ubicacion_texto  VARCHAR(100)      NULL,
    descripcion      TEXT              NULL,
    fecha_inicio     DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_fin        DATETIME          NULL,
    PRIMARY KEY (id),
    KEY ix_diagnostico_nombre (nombre_usuario),
    KEY ix_diagnostico_usuario (usuario_id),
    CONSTRAINT fk_diagnostico_usuario FOREIGN KEY (usuario_id) REFERENCES usuario (id),
    CONSTRAINT ck_diagnostico_nombre CHECK (CHAR_LENGTH(TRIM(nombre_usuario)) > 0),
    CONSTRAINT ck_diagnostico_categoria CHECK (categoria_codigo IS NULL OR categoria_codigo BETWEEN 'A' AND 'G')
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
) ENGINE = InnoDB COMMENT = 'Síntomas y resultados de pruebas observados en cada diagnóstico';

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
    PRIMARY KEY (id),
    UNIQUE KEY uk_dh_posicion (diagnostico_id, posicion),
    CONSTRAINT fk_dh_diagnostico FOREIGN KEY (diagnostico_id) REFERENCES diagnostico (id),
    CONSTRAINT ck_dh_probabilidad CHECK (probabilidad BETWEEN 0 AND 1),
    CONSTRAINT ck_dh_certeza CHECK (certeza BETWEEN -1 AND 1),
    CONSTRAINT ck_dh_posicion CHECK (posicion BETWEEN 1 AND 10)
) ENGINE = InnoDB COMMENT = 'Hipótesis que propuso el motor en cada diagnóstico';

-- =====================================================================
-- Disparadores de integridad
-- =====================================================================
DELIMITER $$

-- Nada se elimina: el DELETE se rechaza en todas las tablas.
CREATE TRIGGER tr_escala_no_borrar BEFORE DELETE ON escala_respuesta FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Los registros no se eliminan.'$$
CREATE TRIGGER tr_usuario_no_borrar BEFORE DELETE ON usuario FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Las cuentas no se eliminan.'$$
CREATE TRIGGER tr_diagnostico_no_borrar BEFORE DELETE ON diagnostico FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Los diagnósticos no se eliminan.'$$
CREATE TRIGGER tr_ie_no_borrar BEFORE DELETE ON incidente_evidencia FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Las evidencias registradas no se eliminan.'$$
CREATE TRIGGER tr_dh_no_borrar BEFORE DELETE ON diagnostico_hipotesis FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Las hipótesis de un diagnóstico no se eliminan.'$$

-- Lo que propuso el motor no cambia.
CREATE TRIGGER tr_dh_solo_insertar BEFORE UPDATE ON diagnostico_hipotesis FOR EACH ROW
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Lo que propuso el motor no se modifica.'$$

DELIMITER ;
