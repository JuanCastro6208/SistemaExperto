-- =====================================================================
-- SEDATI - Sistema de inferencia
-- Esquema equivalente para SQLite (se usa cuando no hay servidor MySQL disponible).
-- Mismas tablas, columnas y restricciones que bd/mysql/01_esquema.sql.
-- =====================================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS consulta_hipotesis;
DROP TABLE IF EXISTS consulta_respuesta;
DROP TABLE IF EXISTS consulta;
DROP TABLE IF EXISTS escala_respuesta;
DROP TABLE IF EXISTS granulo;
DROP TABLE IF EXISTS evidencia;
DROP TABLE IF EXISTS hipotesis;

-- ---------------------------------------------------------------------
-- BASE DE CONOCIMIENTO
-- ---------------------------------------------------------------------

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

-- ---------------------------------------------------------------------
-- OPERACIÓN DEL MOTOR DE INFERENCIA
-- ---------------------------------------------------------------------

CREATE TABLE escala_respuesta (
    codigo   VARCHAR(10)  NOT NULL PRIMARY KEY,
    etiqueta VARCHAR(40)  NOT NULL,
    valor    DECIMAL(3,2) NOT NULL CHECK (valor BETWEEN -1 AND 1),
    orden    INTEGER      NOT NULL,
    color    CHAR(7)      NOT NULL
);

CREATE TABLE consulta (
    id              INTEGER      NOT NULL PRIMARY KEY AUTOINCREMENT,
    fecha_inicio    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_fin       DATETIME     NULL,
    equipo          VARCHAR(40)  NULL,
    ubicacion       VARCHAR(100) NULL,
    descripcion     TEXT         NULL,
    estado          VARCHAR(10)  NOT NULL DEFAULT 'EN_CURSO' CHECK (estado IN ('EN_CURSO','FINALIZADA','CANCELADA')),
    total_preguntas INTEGER      NOT NULL DEFAULT 0,
    parametros      VARCHAR(200) NULL
);

CREATE TABLE consulta_respuesta (
    id            INTEGER      NOT NULL PRIMARY KEY AUTOINCREMENT,
    consulta_id   INTEGER      NOT NULL REFERENCES consulta (id),
    orden         INTEGER      NOT NULL,
    evidencia_id  INTEGER      NOT NULL REFERENCES evidencia (id),
    escala_codigo VARCHAR(10)  NOT NULL REFERENCES escala_respuesta (codigo),
    valor         DECIMAL(3,2) NOT NULL CHECK (valor BETWEEN -1 AND 1),
    origen        VARCHAR(15)  NOT NULL CHECK (origen IN ('SINTOMA_INICIAL','PREGUNTA')),
    registrado_en DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (consulta_id, evidencia_id)
);

CREATE TABLE consulta_hipotesis (
    consulta_id     INTEGER      NOT NULL REFERENCES consulta (id),
    posicion        INTEGER      NOT NULL CHECK (posicion BETWEEN 1 AND 5),
    hipotesis_id    INTEGER      NOT NULL REFERENCES hipotesis (id),
    probabilidad    DECIMAL(6,5) NOT NULL CHECK (probabilidad BETWEEN 0 AND 1),
    certeza         DECIMAL(6,4) NOT NULL,
    regla_principal VARCHAR(6)   NULL,
    PRIMARY KEY (consulta_id, posicion)
);
