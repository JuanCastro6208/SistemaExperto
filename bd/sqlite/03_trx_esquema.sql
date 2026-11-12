-- =====================================================================
-- SEDATI - Base transaccional (sedati_trx) para SQLite
-- Equivalente a bd/mysql/03_trx_esquema.sql (archivo bd/sedati_trx.db).
--
-- Registra cada consulta al sistema experto: quién consultó (solo su nombre, no hay cuentas
-- ni roles), lo que respondió y las hipótesis que propuso el motor de inferencia.
-- No tiene llaves foráneas hacia sedati_kb: la une por los códigos estables HIP-, E-, R-
-- y la letra de la categoría, que la base de conocimiento nunca modifica.
-- =====================================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS diagnostico_hipotesis;
DROP TABLE IF EXISTS incidente_evidencia;
DROP TABLE IF EXISTS diagnostico;
DROP TABLE IF EXISTS escala_respuesta;

-- Respuestas graduadas: la persona no responde solo "sí" o "no", indica qué tan segura está.
CREATE TABLE escala_respuesta (
    codigo   VARCHAR(10)  NOT NULL PRIMARY KEY,
    etiqueta VARCHAR(40)  NOT NULL,
    valor    DECIMAL(3,2) NOT NULL CHECK (valor BETWEEN -1 AND 1),
    orden    INTEGER      NOT NULL,
    color    CHAR(7)      NOT NULL
);

-- Cada ejecución del motor de inferencia.
CREATE TABLE diagnostico (
    id               INTEGER      NOT NULL PRIMARY KEY,
    nombre_usuario   VARCHAR(80)  NOT NULL CHECK (length(trim(nombre_usuario)) > 0),
    categoria_codigo CHAR(1)      NULL CHECK (categoria_codigo IS NULL OR categoria_codigo BETWEEN 'A' AND 'G'),
    estado           VARCHAR(10)  NOT NULL DEFAULT 'EN_CURSO' CHECK (estado IN ('EN_CURSO','FINALIZADO','CANCELADO')),
    total_preguntas  INTEGER      NOT NULL DEFAULT 0,
    parametros       VARCHAR(200) NULL,
    equipo_texto     VARCHAR(40)  NULL,
    ubicacion_texto  VARCHAR(100) NULL,
    descripcion      TEXT         NULL,
    fecha_inicio     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_fin        DATETIME     NULL
);

-- Síntomas y resultados de pruebas observados en cada diagnóstico.
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

-- Hipótesis que propuso el motor (las 5 más probables con su peso).
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
    UNIQUE (diagnostico_id, posicion)
);

-- =====================================================================
-- Disparadores de integridad
-- =====================================================================

-- Nada se elimina.
CREATE TRIGGER tr_escala_no_borrar BEFORE DELETE ON escala_respuesta BEGIN SELECT RAISE(ABORT, 'Los registros no se eliminan.'); END;
CREATE TRIGGER tr_diagnostico_no_borrar BEFORE DELETE ON diagnostico BEGIN SELECT RAISE(ABORT, 'Los diagnósticos no se eliminan.'); END;
CREATE TRIGGER tr_ie_no_borrar BEFORE DELETE ON incidente_evidencia BEGIN SELECT RAISE(ABORT, 'Las evidencias registradas no se eliminan.'); END;
CREATE TRIGGER tr_dh_no_borrar BEFORE DELETE ON diagnostico_hipotesis BEGIN SELECT RAISE(ABORT, 'Las hipótesis de un diagnóstico no se eliminan.'); END;

-- Lo que propuso el motor no cambia.
CREATE TRIGGER tr_dh_solo_insertar BEFORE UPDATE ON diagnostico_hipotesis
BEGIN SELECT RAISE(ABORT, 'Lo que propuso el motor no se modifica.'); END;
