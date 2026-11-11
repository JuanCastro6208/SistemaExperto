-- =====================================================================
-- SEDATI - Consultas de los gránulos de conocimiento por hipótesis (MySQL 8.0, base sedati_kb)
--
-- Primero crea dos vistas y dos procedimientos; después vienen las consultas C1 a C11 del
-- manual técnico, listas para ejecutarse una por una en MySQL Workbench.
--
-- Los procedimientos sp_inferir_* hacen una inferencia sencilla en SQL, útil para revisar la base
-- desde Workbench: certeza de un gránulo = factor del experto × condiciones cumplidas / condiciones
-- totales. El motor de la aplicación (Python) usa además respuestas graduadas, la probabilidad
-- previa y la combinación MYCIN; ver el capítulo del motor de inferencia en el manual.
-- =====================================================================

USE sedati_kb;

-- ------------------------------------------------------------- vistas
CREATE OR REPLACE VIEW v_hipotesis_resumen AS
SELECT h.id, h.codigo, h.nombre, h.dominio, h.probabilidad_previa,
       COUNT(DISTINCT g.regla)                                              AS granulos,
       MIN(g.factor_certeza)                                                AS certeza_min,
       MAX(g.factor_certeza)                                                AS certeza_max,
       ROUND(AVG(g.factor_certeza), 2)                                      AS certeza_prom,
       GROUP_CONCAT(DISTINCT g.rama_codigo ORDER BY g.rama_codigo SEPARATOR ', ') AS ramas
  FROM hipotesis h
  LEFT JOIN granulo g ON g.hipotesis_id = h.id AND g.activo = 1
 WHERE h.activo = 1
 GROUP BY h.id, h.codigo, h.nombre, h.dominio, h.probabilidad_previa;

CREATE OR REPLACE VIEW v_granulo_texto AS
SELECT g.regla                                  AS granulo,
       h.codigo                                 AS hipotesis_codigo,
       h.nombre                                 AS hipotesis,
       MIN(g.categoria_codigo)                  AS categoria_codigo,
       MIN(g.rama_codigo)                       AS rama_codigo,
       MIN(g.factor_certeza)                    AS factor_certeza,
       MAX(g.version)                           AS version,
       COUNT(*)                                 AS condiciones,
       CONCAT(GROUP_CONCAT(CONCAT(g.conector, ' ', e.enunciado) ORDER BY g.orden SEPARATOR ' '),
              ' Then ', MIN(g.conclusion))      AS regla
  FROM granulo g
  JOIN hipotesis h ON h.id = g.hipotesis_id
  JOIN evidencia e ON e.id = g.evidencia_id
 WHERE g.activo = 1
 GROUP BY g.regla, h.codigo, h.nombre;

-- ------------------------------------------------------------- procedimientos de inferencia
DROP PROCEDURE IF EXISTS sp_inferir_granulos;
DROP PROCEDURE IF EXISTS sp_inferir_hipotesis;

DELIMITER $$
-- Cada gránulo con al menos una condición cumplida, con su certeza proporcional.
--   p_evidencias: arreglo JSON de códigos, por ejemplo '["E-079","E-083"]'
CREATE PROCEDURE sp_inferir_granulos(IN p_evidencias JSON)
BEGIN
    SELECT g.regla AS granulo, h.codigo AS hipotesis_codigo, h.nombre AS hipotesis,
           SUM(o.codigo IS NOT NULL) AS cumplidas, COUNT(*) AS total,
           SUM(o.codigo IS NOT NULL) = COUNT(*) AS completo,
           ROUND(MIN(g.factor_certeza) * SUM(o.codigo IS NOT NULL) / COUNT(*), 2) AS certeza,
           MIN(g.conclusion) AS conclusion
      FROM granulo g
      JOIN hipotesis h ON h.id = g.hipotesis_id AND h.activo = 1
      JOIN evidencia e ON e.id = g.evidencia_id
      LEFT JOIN JSON_TABLE(p_evidencias, '$[*]' COLUMNS (codigo CHAR(5) PATH '$')) o ON o.codigo = e.codigo
     WHERE g.activo = 1
     GROUP BY g.regla, h.codigo, h.nombre
    HAVING cumplidas > 0
     ORDER BY certeza DESC, granulo;
END$$

-- La mejor certeza de cada hipótesis, sin las hipótesis descartadas en rondas anteriores.
--   p_descartadas: arreglo JSON de códigos HIP-NN o NULL
CREATE PROCEDURE sp_inferir_hipotesis(IN p_evidencias JSON, IN p_descartadas JSON)
BEGIN
    WITH evaluacion AS (
        SELECT g.regla, g.hipotesis_id,
               SUM(o.codigo IS NOT NULL) AS cumplidas, COUNT(*) AS total,
               MIN(g.factor_certeza) * SUM(o.codigo IS NOT NULL) / COUNT(*) AS certeza,
               MIN(g.conclusion) AS conclusion
          FROM granulo g
          JOIN evidencia e ON e.id = g.evidencia_id
          LEFT JOIN JSON_TABLE(p_evidencias, '$[*]' COLUMNS (codigo CHAR(5) PATH '$')) o ON o.codigo = e.codigo
         WHERE g.activo = 1
         GROUP BY g.regla, g.hipotesis_id
        HAVING cumplidas > 0
    ), ordenada AS (
        SELECT ev.*, ROW_NUMBER() OVER (PARTITION BY ev.hipotesis_id ORDER BY ev.certeza DESC, ev.regla) AS n
          FROM evaluacion ev
    )
    SELECT h.codigo AS hipotesis_codigo, h.nombre AS hipotesis, o.regla AS granulo,
           o.cumplidas, o.total, o.cumplidas = o.total AS completo, ROUND(o.certeza, 2) AS certeza, o.conclusion
      FROM ordenada o
      JOIN hipotesis h ON h.id = o.hipotesis_id AND h.activo = 1
     WHERE o.n = 1
       AND h.codigo NOT IN (SELECT d.codigo FROM JSON_TABLE(COALESCE(p_descartadas, JSON_ARRAY()), '$[*]'
                                                          COLUMNS (codigo CHAR(6) PATH '$')) d)
     ORDER BY certeza DESC, hipotesis_codigo;
END$$
DELIMITER ;

-- =====================================================================
-- Consultas del manual técnico (ejecútelas una por una)
-- =====================================================================

-- C1. Cuántos gránulos sostiene cada hipótesis y en qué ramas aparece
SELECT codigo, nombre, dominio, granulos, certeza_min, certeza_max, certeza_prom, ramas
  FROM v_hipotesis_resumen
 ORDER BY granulos DESC, codigo;

-- C2. Todos los gránulos de una hipótesis, escritos como regla (HIP-06, Memoria RAM)
SELECT granulo, rama_codigo AS rama, factor_certeza AS certeza, regla
  FROM v_granulo_texto
 WHERE hipotesis_codigo = 'HIP-06'
 ORDER BY granulo;

-- C3. Los gránulos de una hipótesis con sus condiciones, una por fila
SELECT g.regla AS granulo, g.orden, g.conector, e.tipo, e.codigo AS evidencia, e.enunciado
  FROM hipotesis h
  JOIN granulo g   ON g.hipotesis_id = h.id AND g.activo = 1
  JOIN evidencia e ON e.id = g.evidencia_id
 WHERE h.nombre = 'Resolución de nombres (DNS)'
 ORDER BY g.regla, g.orden;

-- C4. Consulta inversa: qué hipótesis sostiene una evidencia
SELECT e.codigo AS evidencia, e.enunciado, h.codigo AS hipotesis_codigo, h.nombre AS hipotesis,
       COUNT(DISTINCT g.regla) AS granulos
  FROM evidencia e
  JOIN granulo g   ON g.evidencia_id = e.id AND g.activo = 1
  JOIN hipotesis h ON h.id = g.hipotesis_id
 WHERE e.codigo = 'E-014'
 GROUP BY e.codigo, e.enunciado, h.codigo, h.nombre
 ORDER BY granulos DESC, h.codigo;

-- C5. Evidencias más repetidas dentro de una hipótesis
SELECT e.tipo, e.codigo, e.enunciado, COUNT(*) AS veces_en_granulos
  FROM hipotesis h
  JOIN granulo g   ON g.hipotesis_id = h.id AND g.activo = 1
  JOIN evidencia e ON e.id = g.evidencia_id
 WHERE h.codigo = 'HIP-06'
 GROUP BY e.tipo, e.codigo, e.enunciado
 ORDER BY veces_en_granulos DESC, e.codigo
 LIMIT 10;

-- C6. Hipótesis presentes en más de una categoría del árbol (conocimiento transversal)
SELECT h.codigo, h.nombre, COUNT(DISTINCT g.categoria_codigo) AS categorias,
       GROUP_CONCAT(DISTINCT g.categoria_codigo ORDER BY g.categoria_codigo SEPARATOR ', ') AS letras
  FROM hipotesis h
  JOIN granulo g ON g.hipotesis_id = h.id AND g.activo = 1
 GROUP BY h.id, h.codigo, h.nombre
HAVING categorias > 1
 ORDER BY categorias DESC, h.codigo;

-- C7. Hipótesis con un solo gránulo (se pueden reforzar con más caminos de evidencia)
SELECT codigo, nombre, dominio, certeza_max
  FROM v_hipotesis_resumen
 WHERE granulos = 1
 ORDER BY dominio, codigo;

-- C8. Matriz de cobertura: gránulos por hipótesis y categoría
SELECT h.codigo, h.nombre,
       COUNT(DISTINCT IF(g.categoria_codigo = 'A', g.regla, NULL)) AS A,
       COUNT(DISTINCT IF(g.categoria_codigo = 'B', g.regla, NULL)) AS B,
       COUNT(DISTINCT IF(g.categoria_codigo = 'C', g.regla, NULL)) AS C,
       COUNT(DISTINCT IF(g.categoria_codigo = 'D', g.regla, NULL)) AS D,
       COUNT(DISTINCT IF(g.categoria_codigo = 'E', g.regla, NULL)) AS E,
       COUNT(DISTINCT IF(g.categoria_codigo = 'F', g.regla, NULL)) AS F,
       COUNT(DISTINCT IF(g.categoria_codigo = 'G', g.regla, NULL)) AS G,
       COUNT(DISTINCT g.regla) AS total
  FROM hipotesis h
  JOIN granulo g ON g.hipotesis_id = h.id AND g.activo = 1
 GROUP BY h.id, h.codigo, h.nombre
 ORDER BY total DESC, h.codigo;

-- C9. Inferencia: con las evidencias observadas, qué hipótesis propone el sistema (impresora)
CALL sp_inferir_hipotesis('["E-079","E-083","E-084","E-085"]', NULL);

-- C10. La misma inferencia mostrando cada gránulo evaluado
CALL sp_inferir_granulos('["E-079","E-083","E-084","E-085"]');

-- C11. Segunda ronda de un diagnóstico, descartando la hipótesis HIP-02 (equipo que no enciende)
CALL sp_inferir_hipotesis('["E-001","E-003","E-004","E-005"]', '["HIP-02"]');
