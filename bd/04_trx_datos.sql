-- =====================================================================
-- SEDATI - Datos iniciales de sedati_trx (compatible con MySQL 8 y SQLite)
-- La escala de respuestas y una cuenta de demostración (no hay roles: todas las cuentas son de usuario).
-- =====================================================================

-- Respuestas graduadas: la persona no responde solo "sí" o "no", indica qué tan segura está.
INSERT INTO escala_respuesta (codigo, etiqueta, valor, orden, color) VALUES
('SI',      'Sí, con certeza',   1.00, 1, '#1E8E5A'),
('PROB_SI', 'Probablemente sí',  0.60, 2, '#6DBE8C'),
('NO_SE',   'No lo sé',          0.00, 3, '#8A94A6'),
('PROB_NO', 'Probablemente no', -0.60, 4, '#E59A6B'),
('NO',      'No, con certeza',  -1.00, 5, '#C9473D');

-- Cuenta de demostración:  usuario@sedati.example  /  Sedati2026*
-- (la contraseña se guarda como hash PBKDF2-HMAC-SHA256; las demás cuentas se crean desde la web).
INSERT INTO usuario (nombre, correo, contrasena_hash) VALUES
('Usuario de demostración', 'usuario@sedati.example',
 'pbkdf2_sha256$120000$DA2yLAZm4oD3h3qUHn4DFA$Ia2JC3vrIArFnOOl63jqaLVSRk0FqMmds-7fnOjnHTQ');
