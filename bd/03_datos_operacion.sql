-- =====================================================================
-- SEDATI - Escala de respuestas graduadas (compatible con MySQL 8 y SQLite)
-- El usuario no responde solo "sí" o "no": indica qué tan seguro está de cada observación.
-- El valor es la certeza de la evidencia, de -1 (es falsa) a +1 (es verdadera).
-- =====================================================================

INSERT INTO escala_respuesta (codigo, etiqueta, valor, orden, color) VALUES
('SI',      'Sí, con certeza',   1.00, 1, '#1E8E5A'),
('PROB_SI', 'Probablemente sí',  0.60, 2, '#6DBE8C'),
('NO_SE',   'No lo sé',          0.00, 3, '#8A94A6'),
('PROB_NO', 'Probablemente no', -0.60, 4, '#E59A6B'),
('NO',      'No, con certeza',  -1.00, 5, '#C9473D');
