-- =====================================================================
-- SEDATI - Sistema de inferencia
-- Esquema para MySQL 8.0 (InnoDB, utf8mb4)
--
-- Base de conocimiento (exactamente 3 tablas): hipotesis, evidencia, granulo
-- Operación del motor: escala_respuesta, consulta, consulta_respuesta, consulta_hipotesis
--
-- Orden de ejecución: 01_esquema.sql -> ../02_datos_conocimiento.sql -> ../03_datos_operacion.sql
-- =====================================================================

CREATE DATABASE IF NOT EXISTS sedati CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE sedati;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS consulta_hipotesis;
DROP TABLE IF EXISTS consulta_respuesta;
DROP TABLE IF EXISTS consulta;
DROP TABLE IF EXISTS escala_respuesta;
DROP TABLE IF EXISTS granulo;
DROP TABLE IF EXISTS evidencia;
DROP TABLE IF EXISTS hipotesis;
SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------
-- BASE DE CONOCIMIENTO
-- ---------------------------------------------------------------------

-- Familias de falla que el motor puede proponer.
CREATE TABLE hipotesis (
    id                  SMALLINT UNSIGNED NOT NULL,
    codigo              CHAR(6)           NOT NULL COMMENT 'HIP-NN, no cambia',
    nombre              VARCHAR(120)      NOT NULL,
    dominio             ENUM('Hardware','Sistema operativo','Periféricos','Red','Software','Accesos') NOT NULL,
    probabilidad_previa DECIMAL(7,5)      NOT NULL COMMENT 'P(h) antes de cualquier evidencia (sección 9.5)',
    activo              TINYINT(1)        NOT NULL DEFAULT 1,
    PRIMARY KEY (id),
    UNIQUE KEY uk_hipotesis_codigo (codigo),
    UNIQUE KEY uk_hipotesis_nombre (nombre),
    CONSTRAINT ck_hipotesis_previa CHECK (probabilidad_previa > 0 AND probabilidad_previa <= 1)
) ENGINE = InnoDB COMMENT = 'Hipótesis (familias de falla)';

-- Síntomas y resultados de pruebas. Las evidencias que describen la misma observación
-- comparten "variable"; "polaridad" indica si la afirman (+1) o la niegan (-1).
CREATE TABLE evidencia (
    id         SMALLINT UNSIGNED NOT NULL,
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
    id                   SMALLINT UNSIGNED NOT NULL,
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
-- OPERACIÓN DEL MOTOR DE INFERENCIA
-- ---------------------------------------------------------------------

-- Respuestas graduadas que puede dar el usuario (no solo sí / no).
CREATE TABLE escala_respuesta (
    codigo   VARCHAR(10)  NOT NULL,
    etiqueta VARCHAR(40)  NOT NULL,
    valor    DECIMAL(3,2) NOT NULL COMMENT 'Certeza de la observación, de -1 (falsa) a +1 (verdadera)',
    orden    TINYINT      NOT NULL,
    color    CHAR(7)      NOT NULL,
    PRIMARY KEY (codigo),
    CONSTRAINT ck_escala_valor CHECK (valor BETWEEN -1 AND 1)
) ENGINE = InnoDB;

-- Una sesión de diagnóstico.
CREATE TABLE consulta (
    id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
    fecha_inicio    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_fin       DATETIME     NULL,
    equipo          VARCHAR(40)  NULL COMMENT 'Código de inventario del equipo',
    ubicacion       VARCHAR(100) NULL,
    descripcion     TEXT         NULL,
    estado          ENUM('EN_CURSO','FINALIZADA','CANCELADA') NOT NULL DEFAULT 'EN_CURSO',
    total_preguntas SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    parametros      VARCHAR(200) NULL COMMENT 'Parámetros del motor usados',
    PRIMARY KEY (id)
) ENGINE = InnoDB;

-- Lo que el usuario respondió (síntomas iniciales y respuestas a cada pregunta).
CREATE TABLE consulta_respuesta (
    id            INT UNSIGNED      NOT NULL AUTO_INCREMENT,
    consulta_id   INT UNSIGNED      NOT NULL,
    orden         SMALLINT UNSIGNED NOT NULL,
    evidencia_id  SMALLINT UNSIGNED NOT NULL,
    escala_codigo VARCHAR(10)       NOT NULL,
    valor         DECIMAL(3,2)      NOT NULL,
    origen        ENUM('SINTOMA_INICIAL','PREGUNTA') NOT NULL,
    registrado_en DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_respuesta (consulta_id, evidencia_id),
    CONSTRAINT fk_respuesta_consulta  FOREIGN KEY (consulta_id)   REFERENCES consulta (id),
    CONSTRAINT fk_respuesta_evidencia FOREIGN KEY (evidencia_id)  REFERENCES evidencia (id),
    CONSTRAINT fk_respuesta_escala    FOREIGN KEY (escala_codigo) REFERENCES escala_respuesta (codigo),
    CONSTRAINT ck_respuesta_valor CHECK (valor BETWEEN -1 AND 1)
) ENGINE = InnoDB;

-- Las 5 hipótesis que entrega el motor al cerrar la consulta, con su peso probabilístico.
CREATE TABLE consulta_hipotesis (
    consulta_id     INT UNSIGNED      NOT NULL,
    posicion        TINYINT UNSIGNED  NOT NULL,
    hipotesis_id    SMALLINT UNSIGNED NOT NULL,
    probabilidad    DECIMAL(6,5)      NOT NULL,
    certeza         DECIMAL(6,4)      NOT NULL COMMENT 'Factor de certeza combinado, de -1 a 1',
    regla_principal VARCHAR(6)        NULL,
    PRIMARY KEY (consulta_id, posicion),
    CONSTRAINT fk_ch_consulta  FOREIGN KEY (consulta_id)  REFERENCES consulta (id),
    CONSTRAINT fk_ch_hipotesis FOREIGN KEY (hipotesis_id) REFERENCES hipotesis (id),
    CONSTRAINT ck_ch_probabilidad CHECK (probabilidad BETWEEN 0 AND 1),
    CONSTRAINT ck_ch_posicion CHECK (posicion BETWEEN 1 AND 5)
) ENGINE = InnoDB;
