-- =====================================================================
-- SEDATI - Datos iniciales de sedati_trx (compatible con MySQL 8 y SQLite)
-- Catálogos, matriz de permisos y cuentas de demostración.
--
-- Cuentas de demostración (todas con la contraseña  Sedati2026*  guardada como hash PBKDF2):
--   admin@sedati.example          Administrador
--   laura.gomez@sedati.example    Administrador
--   solicitante@sedati.example    Solicitante
--   ana.rodriguez@sedati.example  Solicitante
--   miguel.torres@sedati.example  Solicitante
-- Cámbielas antes de usar el sistema con datos reales.
-- =====================================================================

-- Respuestas graduadas: el usuario no responde solo "sí" o "no", indica qué tan seguro está.
INSERT INTO escala_respuesta (codigo, etiqueta, valor, orden, color) VALUES
('SI',      'Sí, con certeza',   1.00, 1, '#1E8E5A'),
('PROB_SI', 'Probablemente sí',  0.60, 2, '#6DBE8C'),
('NO_SE',   'No lo sé',          0.00, 3, '#8A94A6'),
('PROB_NO', 'Probablemente no', -0.60, 4, '#E59A6B'),
('NO',      'No, con certeza',  -1.00, 5, '#C9473D');

INSERT INTO rol (id, codigo, nombre, descripcion) VALUES
(1, 'ADMINISTRADOR', 'Administrador', 'Personal de soporte: atiende y diagnostica incidentes, mantiene la base de conocimiento y administra las cuentas.'),
(2, 'SOLICITANTE',   'Solicitante',   'Persona de la institución que reporta fallas de su equipo y programa citas de atención.');

INSERT INTO modulo (id, codigo, nombre) VALUES
(1, 'USUARIOS',     'Cuentas de usuario y roles'),
(2, 'INCIDENTES',   'Incidentes'),
(3, 'CITAS',        'Citas'),
(4, 'DIAGNOSTICO',  'Diagnóstico (inferencia y registro)'),
(5, 'CONOCIMIENTO', 'Base de conocimiento'),
(6, 'INDICADORES',  'Historial e indicadores'),
(7, 'RESPALDO',     'Respaldo y restauración');

-- Matriz de permisos. El filtro por fila (el solicitante solo ve lo suyo) lo aplica la capa de negocio.
-- Ningún rol tiene permiso de borrado: lo que sale de uso se desactiva.
INSERT INTO rol_permiso (rol_id, modulo_id, puede_consultar, puede_crear, puede_modificar) VALUES
(1, 1, 1, 1, 1), (1, 2, 1, 1, 1), (1, 3, 1, 1, 1), (1, 4, 1, 1, 1), (1, 5, 1, 1, 1), (1, 6, 1, 0, 0), (1, 7, 1, 1, 0),
(2, 1, 0, 0, 0), (2, 2, 1, 1, 0), (2, 3, 1, 1, 1), (2, 4, 0, 0, 0), (2, 5, 0, 0, 0), (2, 6, 0, 0, 0), (2, 7, 0, 0, 0);

INSERT INTO dependencia (id, nombre, activo) VALUES
(1, 'Sala de cómputo 1', 1),
(2, 'Sala de cómputo 2', 1),
(3, 'Biblioteca', 1),
(4, 'Laboratorio de redes', 1),
(5, 'Oficina de soporte técnico', 1);

INSERT INTO tipo_equipo (id, codigo, nombre) VALUES
(1, 'ESCRITORIO', 'Computador de escritorio'),
(2, 'PORTATIL',   'Computador portátil'),
(3, 'IMPRESORA',  'Impresora'),
(4, 'MONITOR',    'Monitor'),
(5, 'PERIFERICO', 'Periférico (teclado, mouse, USB)'),
(6, 'RED',        'Equipo de red'),
(7, 'OTRO',       'Otro');

INSERT INTO usuario (id, rol_id, dependencia_id, documento, nombre, correo, contrasena_hash,
                     debe_cambiar_contrasena, activo, intentos_fallidos) VALUES
(1, 1, 5, '1000000001', 'Administrador SEDATI', 'admin@sedati.example', 'pbkdf2_sha256$120000$AU1lUprTUxQ7UXbNgwCJNQ$ZqjrSk6LkTVs5HbmxgzvmWKzKhOeTqbi03FfEX8ylOQ', 0, 1, 0),
(2, 1, 5, '1000000002', 'Laura Gómez', 'laura.gomez@sedati.example', 'pbkdf2_sha256$120000$FWDONxG8L2P6NgJM_NlJdg$xlYSErUtbHmu6vf3t5vkB6SJa5bmpmz9Md_BriTZ8TU', 0, 1, 0),
(3, 2, 2, '1000000003', 'Carlos Pérez', 'solicitante@sedati.example', 'pbkdf2_sha256$120000$Zv3qJs3xn3KB8xPdogm2eA$R-y0Ys5QQg4RpV7Rd4bs-7kOgDYyL_NS4TnIhHN3bZY', 0, 1, 0),
(4, 2, 3, '1000000004', 'Ana Rodríguez', 'ana.rodriguez@sedati.example', 'pbkdf2_sha256$120000$DGzA1TVT-US3bZea9BD6Ww$ij9a6GFTyHnBI11YBUu7oG_UOmX-eLiqPFT3dYUUWFQ', 0, 1, 0),
(5, 2, 4, '1000000005', 'Miguel Torres', 'miguel.torres@sedati.example', 'pbkdf2_sha256$120000$jrn4snlnud1HWgJrLLh0LQ$4ngxxtwMZugj81b22Ijw1wNuM1P_FPbKjeBJaZXh_IU', 0, 1, 0);

INSERT INTO equipo (id, inventario, tipo_equipo_id, dependencia_id, marca, modelo, ubicacion, activo) VALUES
(1, 'PC-SALA2-014', 1, 2, 'Dell', 'OptiPlex 7090', 'Sala de cómputo 2, puesto 14', 1),
(2, 'PC-SALA1-003', 1, 1, 'HP', 'ProDesk 400 G7', 'Sala de cómputo 1, puesto 3', 1),
(3, 'IMP-BIB-01',   3, 3, 'HP', 'LaserJet Pro M404', 'Biblioteca, mostrador', 1),
(4, 'PC-LABRED-07', 1, 4, 'Lenovo', 'ThinkCentre M70q', 'Laboratorio de redes, puesto 7', 1),
(5, 'POR-SOP-02',   2, 5, 'Lenovo', 'ThinkPad E14', 'Oficina de soporte técnico', 1);

INSERT INTO auditoria_conocimiento (entidad, codigo, version, accion, usuario_id, detalle) VALUES
('GRANULO', NULL, 1, 'CARGA_INICIAL', 1, '{"hipotesis": 38, "evidencias": 153, "reglas": 88, "filas_granulo": 224, "fuente": "02_kb_datos.sql"}');
