-- =====================================================================
-- SEDATI - Base de conocimiento (sedati_kb) para SQLite
-- Equivalente a bd/mysql/01_kb_esquema.sql: mismas tablas, columnas, restricciones y disparadores.
-- Se usa cuando no hay un servidor MySQL disponible (archivo bd/sedati_kb.db).
-- =====================================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS granulo;
DROP TABLE IF EXISTS evidencia;
DROP TABLE IF EXISTS hipotesis;

CREATE TABLE hipotesis (
    id                  INTEGER      NOT NULL PRIMARY KEY,
    codigo              CHAR(6)      NOT NULL UNIQUE,
    nombre              VARCHAR(120) NOT NULL UNIQUE,
    dominio             VARCHAR(20)  NOT NULL CHECK (dominio IN ('Hardware','Sistema operativo','Periféricos','Red','Software','Accesos')),
    probabilidad_previa DECIMAL(7,5) NOT NULL CHECK (probabilidad_previa > 0 AND probabilidad_previa <= 1),
    activo              INTEGER      NOT NULL DEFAULT 1
);

CREATE TABLE evidencia (
    id         INTEGER      NOT NULL PRIMARY KEY,
    codigo     CHAR(5)      NOT NULL UNIQUE,
    tipo       VARCHAR(7)   NOT NULL CHECK (tipo IN ('SINTOMA','PRUEBA')),
    enunciado  VARCHAR(250) NOT NULL UNIQUE,
    pregunta   VARCHAR(300) NOT NULL,
    variable   VARCHAR(40)  NULL,
    polaridad  INTEGER      NOT NULL DEFAULT 1 CHECK (polaridad IN (-1, 1)),
    activo     INTEGER      NOT NULL DEFAULT 1
);
CREATE INDEX ix_evidencia_variable ON evidencia (variable);

CREATE TABLE granulo (
    id                   INTEGER      NOT NULL PRIMARY KEY,
    regla                VARCHAR(6)   NOT NULL,
    hipotesis_id         INTEGER      NOT NULL REFERENCES hipotesis (id),
    evidencia_id         INTEGER      NOT NULL REFERENCES evidencia (id),
    orden                INTEGER      NOT NULL,
    conector             VARCHAR(3)   NOT NULL,
    peso                 DECIMAL(4,2) NOT NULL DEFAULT 1.00 CHECK (peso > 0),
    categoria_codigo     CHAR(1)      NOT NULL,
    categoria_nombre     VARCHAR(60)  NOT NULL,
    rama_codigo          CHAR(2)      NOT NULL,
    rama_nombre          VARCHAR(80)  NOT NULL,
    procesos             VARCHAR(20)  NOT NULL,
    conclusion           VARCHAR(250) NOT NULL,
    accion               VARCHAR(500) NOT NULL,
    factor_certeza       DECIMAL(5,2) NOT NULL CHECK (factor_certeza BETWEEN 0 AND 100),
    riesgo_perdida_datos INTEGER      NOT NULL DEFAULT 0,
    fuente               VARCHAR(160) NOT NULL,
    version              INTEGER      NOT NULL DEFAULT 1,
    activo               INTEGER      NOT NULL DEFAULT 1,
    creado_en            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (regla, orden),
    UNIQUE (regla, evidencia_id),
    CHECK ((orden = 1 AND conector = 'If') OR (orden > 1 AND conector = 'And'))
);
CREATE INDEX ix_granulo_evidencia ON granulo (evidencia_id);
CREATE INDEX ix_granulo_hipotesis ON granulo (hipotesis_id);
CREATE INDEX ix_granulo_categoria ON granulo (categoria_codigo);

-- Nada se elimina (se desactiva) y los códigos no cambian.
CREATE TRIGGER tr_hipotesis_no_borrar BEFORE DELETE ON hipotesis
BEGIN SELECT RAISE(ABORT, 'Las hipótesis no se eliminan: desactívelas (activo = 0).'); END;
CREATE TRIGGER tr_hipotesis_codigo_fijo BEFORE UPDATE OF codigo ON hipotesis WHEN NEW.codigo <> OLD.codigo
BEGIN SELECT RAISE(ABORT, 'El código de una hipótesis no se puede modificar.'); END;
CREATE TRIGGER tr_evidencia_no_borrar BEFORE DELETE ON evidencia
BEGIN SELECT RAISE(ABORT, 'Las evidencias no se eliminan: desactívelas (activo = 0).'); END;
CREATE TRIGGER tr_evidencia_codigo_fijo BEFORE UPDATE OF codigo ON evidencia WHEN NEW.codigo <> OLD.codigo
BEGIN SELECT RAISE(ABORT, 'El código de una evidencia no se puede modificar.'); END;
CREATE TRIGGER tr_granulo_no_borrar BEFORE DELETE ON granulo
BEGIN SELECT RAISE(ABORT, 'Los gránulos no se eliminan: desactívelos (activo = 0).'); END;
CREATE TRIGGER tr_granulo_regla_fija BEFORE UPDATE ON granulo
WHEN NEW.regla <> OLD.regla OR NEW.evidencia_id <> OLD.evidencia_id OR NEW.orden <> OLD.orden
  OR NEW.hipotesis_id <> OLD.hipotesis_id
BEGIN SELECT RAISE(ABORT, 'La regla, la hipótesis, el orden y la evidencia de una condición no cambian: cree un gránulo nuevo.'); END;
