-- =====================================================================
-- SEDATI - Datos iniciales de sedati_trx (compatible con MySQL 8 y SQLite)
-- Solo la escala de respuestas: no hay cuentas ni roles, la persona entra con su nombre.
-- =====================================================================

-- Respuestas graduadas: la persona no responde solo "sí" o "no", indica qué tan segura está.
INSERT INTO escala_respuesta (codigo, etiqueta, valor, orden, color) VALUES
('SI',      'Sí, con certeza',   1.00, 1, '#1E8E5A'),
('PROB_SI', 'Probablemente sí',  0.60, 2, '#6DBE8C'),
('NO_SE',   'No lo sé',          0.00, 3, '#8A94A6'),
('PROB_NO', 'Probablemente no', -0.60, 4, '#E59A6B'),
('NO',      'No, con certeza',  -1.00, 5, '#C9473D');
