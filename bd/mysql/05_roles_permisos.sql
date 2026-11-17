-- =====================================================================
-- SEDATI - Permisos en el motor de base de datos (MySQL 8.0)
--
-- Las cuentas de los usuarios del sistema viven en la tabla sedati_trx.usuario (no son usuarios de
-- MySQL). En el motor solo existe la cuenta con la que se conecta el servicio web (AWS Lambda o
-- servidor local), y recibe el rol sedati_aplicacion. Ningún permiso incluye DELETE (los disparadores también
-- rechazan el borrado).
--
--   sedati_aplicacion  lee la base de conocimiento, registra las cuentas y los diagnósticos
-- =====================================================================

-- Roles de versiones anteriores. sedati_aplicacion no se borra: si ya existe, se conserva para que
-- la cuenta del servicio no pierda sus permisos al reinstalar las bases.
DROP ROLE IF EXISTS sedati_solicitante, sedati_administrador;
CREATE ROLE IF NOT EXISTS sedati_aplicacion;

GRANT SELECT, INSERT, UPDATE ON sedati_trx.* TO sedati_aplicacion;
GRANT SELECT ON sedati_kb.*                  TO sedati_aplicacion;
GRANT EXECUTE ON sedati_kb.*                 TO sedati_aplicacion;
