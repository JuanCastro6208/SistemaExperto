-- =====================================================================
-- SEDATI - Base de conocimiento (sedati_kb) para MySQL 8.0 (InnoDB, utf8mb4)
--
-- Exactamente tres tablas: hipotesis, evidencia y granulo.
-- Cada fila de granulo es una condición de una regla If / And / Then del experto.
--
-- Orden de ejecución de los scripts:
--   01_kb_esquema.sql -> ../02_kb_datos.sql -> 03_trx_esquema.sql -> ../04_trx_datos.sql
--   -> 05_roles_permisos.sql -> 06_consultas_granulos_por_hipotesis.sql
-- =====================================================================

CREATE DATABASE IF NOT EXISTS sedati_kb CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE sedati_kb;

DROP TRIGGER IF EXISTS tr_hipotesis_no_borrar;
DROP TRIGGER IF EXISTS tr_hipotesis_codigo_fijo;
DROP TRIGGER IF EXISTS tr_evidencia_no_borrar;
DROP TRIGGER IF EXISTS tr_evidencia_codigo_fijo;
DROP TRIGGER IF EXISTS tr_granulo_no_borrar;
DROP TRIGGER IF EXISTS tr_granulo_regla_fija;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS granulo;
DROP TABLE IF EXISTS evidencia;
DROP TABLE IF EXISTS hipotesis;
SET FOREIGN_KEY_CHECKS = 1;

-- Familias de falla que el motor puede proponer.
CREATE TABLE hipotesis (
    id                  SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    codigo              CHAR(6)           NOT NULL COMMENT 'HIP-NN, no cambia',
    nombre              VARCHAR(120)      NOT NULL,
    dominio             ENUM('Hardware','Sistema operativo','Periféricos','Red','Software','Accesos') NOT NULL,
    probabilidad_previa DECIMAL(7,5)      NOT NULL COMMENT 'P(h) antes de cualquier evidencia (revisión documental)',
    activo              TINYINT(1)        NOT NULL DEFAULT 1,
    PRIMARY KEY (id),
    UNIQUE KEY uk_hipotesis_codigo (codigo),
    UNIQUE KEY uk_hipotesis_nombre (nombre),
    CONSTRAINT ck_hipotesis_previa CHECK (probabilidad_previa > 0 AND probabilidad_previa <= 1)
) ENGINE = InnoDB COMMENT = 'Hipótesis (familias de falla)';

-- Síntomas y resultados de pruebas. Las evidencias que describen la misma observación
-- comparten "variable"; "polaridad" indica si la afirman (+1) o la niegan (-1).
CREATE TABLE evidencia (
    id         SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    codigo     CHAR(5)           NOT NULL COMMENT 'E-NNN, no cambia',
    tipo       ENUM('SINTOMA','PRUEBA') NOT NULL,
    enunciado  VARCHAR(250)      NOT NULL COMMENT 'Texto tal como aparece en la regla',
    pregunta   VARCHAR(300)      NOT NULL COMMENT 'Cómo se le pregunta al usuario',
    variable   VARCHAR(40)       NULL     COMMENT 'Observación de la que es parte',
    polaridad  TINYINT           NOT NULL DEFAULT 1,
    activo     TINYINT(1)        NOT NULL DEFAULT 1,
    PRIMARY KEY (id),
    UNIQUE KEY uk_evidencia_codigo (codigo),
    UNIQUE KEY uk_evidencia_enunciado (enunciado),
    KEY ix_evidencia_variable (variable),
    CONSTRAINT ck_evidencia_polaridad CHECK (polaridad IN (-1, 1))
) ENGINE = InnoDB COMMENT = 'Evidencias (síntomas y pruebas)';

-- Gránulo de conocimiento: una regla If / And / Then del experto, con una fila por condición.
-- Todas las filas de una regla comparten hipótesis, conclusión, acción y factor de certeza.
CREATE TABLE granulo (
    id                   SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    regla                VARCHAR(6)        NOT NULL COMMENT 'R-NN',
    hipotesis_id         SMALLINT UNSIGNED NOT NULL,
    evidencia_id         SMALLINT UNSIGNED NOT NULL,
    orden                TINYINT UNSIGNED  NOT NULL,
    conector             ENUM('If','And')  NOT NULL,
    peso                 DECIMAL(4,2)      NOT NULL DEFAULT 1.00 COMMENT 'Importancia de la condición dentro de la regla',
    categoria_codigo     CHAR(1)           NOT NULL,
    categoria_nombre     VARCHAR(60)       NOT NULL,
    rama_codigo          CHAR(2)           NOT NULL,
    rama_nombre          VARCHAR(80)       NOT NULL,
    procesos             VARCHAR(20)       NOT NULL,
    conclusion           VARCHAR(250)      NOT NULL,
    accion               VARCHAR(500)      NOT NULL,
    factor_certeza       DECIMAL(5,2)      NOT NULL,
    riesgo_perdida_datos TINYINT(1)        NOT NULL DEFAULT 0,
    fuente               VARCHAR(160)      NOT NULL,
    version              INT UNSIGNED      NOT NULL DEFAULT 1,
    activo               TINYINT(1)        NOT NULL DEFAULT 1,
    creado_en            DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en       DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_granulo_regla_orden (regla, orden),
    UNIQUE KEY uk_granulo_regla_evidencia (regla, evidencia_id),
    KEY ix_granulo_evidencia (evidencia_id),
    KEY ix_granulo_hipotesis (hipotesis_id),
    KEY ix_granulo_categoria (categoria_codigo),
    CONSTRAINT fk_granulo_hipotesis FOREIGN KEY (hipotesis_id) REFERENCES hipotesis (id),
    CONSTRAINT fk_granulo_evidencia FOREIGN KEY (evidencia_id) REFERENCES evidencia (id),
    CONSTRAINT ck_granulo_conector CHECK ((orden = 1 AND conector = 'If') OR (orden > 1 AND conector = 'And')),
    CONSTRAINT ck_granulo_factor CHECK (factor_certeza BETWEEN 0 AND 100),
    CONSTRAINT ck_granulo_peso CHECK (peso > 0)
) ENGINE = InnoDB COMMENT = 'Gránulos de conocimiento (reglas If / And / Then)';

-- ---------------------------------------------------------------------
-- Disparadores: nada se elimina (se desactiva) y los códigos no cambian.
-- ---------------------------------------------------------------------
DELIMITER $$
CREATE TRIGGER tr_hipotesis_no_borrar BEFORE DELETE ON hipotesis FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Las hipótesis no se eliminan: desactívelas (activo = 0).';
END$$
CREATE TRIGGER tr_hipotesis_codigo_fijo BEFORE UPDATE ON hipotesis FOR EACH ROW
BEGIN
    IF NEW.codigo <> OLD.codigo THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El código de una hipótesis no se puede modificar.';
    END IF;
END$$
CREATE TRIGGER tr_evidencia_no_borrar BEFORE DELETE ON evidencia FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Las evidencias no se eliminan: desactívelas (activo = 0).';
END$$
CREATE TRIGGER tr_evidencia_codigo_fijo BEFORE UPDATE ON evidencia FOR EACH ROW
BEGIN
    IF NEW.codigo <> OLD.codigo THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El código de una evidencia no se puede modificar.';
    END IF;
END$$
CREATE TRIGGER tr_granulo_no_borrar BEFORE DELETE ON granulo FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Los gránulos no se eliminan: desactívelos (activo = 0).';
END$$
CREATE TRIGGER tr_granulo_regla_fija BEFORE UPDATE ON granulo FOR EACH ROW
BEGIN
    IF NEW.regla <> OLD.regla OR NEW.evidencia_id <> OLD.evidencia_id OR NEW.orden <> OLD.orden THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La regla, el orden y la evidencia de una condición no cambian: cree un gránulo nuevo.';
    END IF;
    IF NEW.hipotesis_id <> OLD.hipotesis_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La hipótesis que concluye un gránulo no cambia: cree un gránulo nuevo.';
    END IF;
END$$
DELIMITER ;
