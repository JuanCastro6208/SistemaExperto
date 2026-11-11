-- =====================================================================
-- SEDATI - Roles del motor de base de datos (MySQL 8.0)
--
-- Cada rol del sistema tiene un rol equivalente en MySQL. Ningún rol recibe DELETE:
-- lo que sale de uso se desactiva (los disparadores también rechazan el borrado).
--
--   sedati_solicitante    lo que puede hacer una persona que reporta fallas
--   sedati_administrador  lo que puede hacer el personal de soporte
--   sedati_aplicacion     la cuenta con la que se conecta el servicio web (AWS Lambda o servidor
--                         local); recibe los permisos del administrador porque el servicio atiende a
--                         los dos roles y aplica en la capa de negocio el filtro por fila
--                         (el solicitante solo ve sus incidentes y citas).
-- =====================================================================

DROP ROLE IF EXISTS sedati_solicitante, sedati_administrador, sedati_aplicacion;
CREATE ROLE sedati_solicitante, sedati_administrador, sedati_aplicacion;

-- ------------------------------------------------------------- solicitante
GRANT SELECT, INSERT ON sedati_trx.incidente           TO sedati_solicitante;
GRANT SELECT, INSERT ON sedati_trx.equipo              TO sedati_solicitante;
GRANT SELECT, INSERT, UPDATE ON sedati_trx.cita        TO sedati_solicitante;
GRANT SELECT ON sedati_trx.incidente_historial         TO sedati_solicitante;
GRANT SELECT ON sedati_trx.tipo_equipo                 TO sedati_solicitante;
GRANT SELECT ON sedati_trx.dependencia                 TO sedati_solicitante;
GRANT SELECT (id, nombre, rol_id, activo) ON sedati_trx.usuario TO sedati_solicitante;

-- ------------------------------------------------------------- administrador
GRANT SELECT, INSERT, UPDATE ON sedati_trx.* TO sedati_administrador;
GRANT SELECT, INSERT, UPDATE ON sedati_kb.*  TO sedati_administrador;
GRANT EXECUTE ON sedati_kb.*                 TO sedati_administrador;

-- ------------------------------------------------------------- cuenta de la aplicación
GRANT sedati_administrador TO sedati_aplicacion;
