-- =====================================================================
-- SEDATI - Permisos en el motor de base de datos (MySQL 8.0)
--
-- El sistema no tiene cuentas ni roles de usuario: la persona entra escribiendo su nombre.
-- Solo existe la cuenta con la que se conecta el servicio web (AWS Lambda o servidor local),
-- y recibe el rol sedati_aplicacion. Ningún permiso incluye DELETE (los disparadores también
-- rechazan el borrado).
--
--   sedati_aplicacion  lee la base de conocimiento y registra los diagnósticos
-- =====================================================================

DROP ROLE IF EXISTS sedati_solicitante, sedati_administrador, sedati_aplicacion;
CREATE ROLE sedati_aplicacion;

GRANT SELECT, INSERT, UPDATE ON sedati_trx.* TO sedati_aplicacion;
GRANT SELECT ON sedati_kb.*                  TO sedati_aplicacion;
GRANT EXECUTE ON sedati_kb.*                 TO sedati_aplicacion;
