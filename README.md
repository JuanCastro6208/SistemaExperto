# SEDATI · Sistema experto para el diagnóstico y la atención de incidentes de cómputo y redes

Aplicación web con dos roles, **Solicitante** y **Administrador**:

- **El solicitante** reporta la falla de su equipo, sigue el estado de su incidente y programa, reprograma o cancela la
  cita de atención.
- **El administrador**:
  - toma el incidente;
  - lo diagnostica con el **motor de inferencia**, que usa 88 reglas If / And / Then, 38 hipótesis y entrega las
    **5 causas más probables con su peso probabilístico**;
  - confirma o descarta hipótesis y registra la solución. Si la solución no funciona, ejecuta otra ronda sin las
    hipótesis descartadas. También puede escalar el incidente;
  - consulta el historial por equipo y los indicadores;
  - administra las cuentas y la base de conocimiento.

El motor no es un árbol de `if` en el código: todo el conocimiento está en la base de conocimiento (`sedati_kb`), y el
motor la consulta de forma **granular** (solo los gránulos que necesita en cada paso).

## 1. Ejecutarlo en su equipo (5 minutos)

Requisitos: **Python 3.10 o superior**. No hace falta instalar ninguna base de datos: por defecto usa SQLite.

```bash
git clone https://github.com/JuanCastro6208/SistemaExperto.git
cd SistemaExperto
pip install -r requirements.txt
python servidor_web.py
```

Abra **<http://127.0.0.1:8000>** e ingrese con una cuenta de demostración. Todas tienen la contraseña `Sedati2026*`:

| Correo | Rol |
|---|---|
| `admin@sedati.example` | Administrador |
| `laura.gomez@sedati.example` | Administrador |
| `solicitante@sedati.example` | Solicitante |
| `ana.rodriguez@sedati.example` | Solicitante |
| `miguel.torres@sedati.example` | Solicitante |

La primera vez, las dos bases se crean solas a partir de los scripts de `bd/`: `bd/sedati_kb.db` y `bd/sedati_trx.db`.
También se cargan seis incidentes de demostración, que se crean con la propia lógica del sistema:

| Incidente | Qué muestra |
|---|---|
| 1 | Cerrado en la primera ronda |
| 2 | Cerrado en la segunda ronda, después de que una solución no funcionó |
| 3 | Escalado |
| 4 | Cerrado |
| 5 | En diagnóstico |
| 6 | Abierto y sin responsable |

Para empezar de cero, borre esos dos archivos `.db`.

> Cambie las contraseñas de demostración antes de usar el sistema con datos reales
> (`config.ini` → `datos_demostracion = no`).

### Recorrido sugerido

1. Ingrese como **solicitante** → **+ Reportar incidente**.
2. Ingrese como **administrador** → **Incidentes** → abra el incidente → **Tomar incidente** → **Programar cita** →
   **Iniciar ronda 1 de diagnóstico**.
3. Marque los síntomas y responda las preguntas con su grado de certeza. Puede usar las teclas **1** a **5**.
4. **Ver diagnóstico** → **Guardar ronda**.
5. En el incidente, **Confirmar** la hipótesis → **Registrar solución**:
   - con *Solucionado*, el incidente se cierra;
   - con *No solucionado*, ejecute una nueva ronda: la hipótesis que falló ya no se propone.
6. Revise **Indicadores**, **Historial**, **Usuarios** y **Base de conocimiento**. En esta última puede crear un
   gránulo, simularlo, editarlo (sube de versión) o desactivarlo.

## 2. Pruebas automáticas

```bash
python -m unittest discover -s tests -v
```

Son 33 pruebas en total:

- 17 prueban el motor;
- 16 prueban la API y los procesos transaccionales: acceso, bloqueo, permisos por rol, flujo completo de un incidente
  con dos rondas, escalamiento, administración del conocimiento y handler de Lambda.

Las mismas pruebas corren contra un MySQL 8 real:

```bash
SEDATI_PRUEBAS_MYSQL=127.0.0.1:3306:root:<contraseña> python -m unittest tests.test_api
```

## 3. Usar MySQL 8

1. Instale las dos bases. Esto ejecuta, en orden, los mismos scripts que se abren en MySQL Workbench:
   ```bash
   python bd/instalar_mysql.py --host localhost --usuario root --usuario-servicio sedati_app --demo
   ```
2. En `config.ini` ponga `motor = mysql` y escriba el usuario y la contraseña en `[mysql]`.

| Script | Contenido |
|---|---|
| `bd/mysql/01_kb_esquema.sql` | Base de conocimiento `sedati_kb`: **exactamente 3 tablas** (`hipotesis`, `evidencia`, `granulo`) y sus disparadores |
| `bd/02_kb_datos.sql` | Conocimiento del experto: 38 hipótesis, 153 evidencias, 88 reglas (224 filas de `granulo`) |
| `bd/mysql/03_trx_esquema.sql` | Base transaccional `sedati_trx`: 18 tablas y 33 disparadores de integridad (41 en la versión SQLite) |
| `bd/04_trx_datos.sql` | Roles, módulos, matriz de permisos, dependencias, tipos de equipo y cuentas de demostración |
| `bd/mysql/05_roles_permisos.sql` | Roles de MySQL (`sedati_solicitante`, `sedati_administrador`, `sedati_aplicacion`), sin permiso de borrado |
| `bd/mysql/06_consultas_granulos_por_hipotesis.sql` | Vistas, procedimientos de inferencia en SQL y consultas C1 a C11 del manual |

Los scripts de `bd/sqlite/` son los equivalentes para SQLite.

## 4. Arquitectura

```
servidor_web.py · lambda_function.py   puntos de entrada (local / AWS Lambda)
web/                                   interfaz web (HTML, CSS y JS sin dependencias)
  app.js        núcleo, diagnóstico, base de conocimiento, historial
  atencion.js   acceso, incidentes, citas, usuarios, indicadores, administración del conocimiento
sedati/
├── servicio/   CAPA DE SERVICIO: API REST, sesión por token firmado, permiso por ruta
├── negocio/    CAPA DE NEGOCIO: sin SQL ni interfaz
│   ├── motor_inferencia.py, memoria_trabajo.py, selector_preguntas.py, certeza.py, explicacion.py
│   ├── servicios.py               ServicioDiagnostico y ServicioConocimiento     (RF-02, RF-03)
│   ├── servicio_acceso.py         ServicioAcceso y ServicioUsuarios              (RF-01)
│   ├── servicio_atencion.py       incidentes, citas, rondas, solución, escalamiento e indicadores (RF-02)
│   ├── servicio_conocimiento.py   administración de hipótesis, evidencias y gránulos (RF-03)
│   └── seguridad.py               PBKDF2-SHA256 con sal y tokens HMAC
├── datos/      CAPA DE DATOS: patrón DAO, la única que conoce SQL
│   ├── conexion.py                ConexionBD (abstracta) → ConexionSQLite, ConexionMySQL
│   ├── dto.py                     objetos de transferencia (UsuarioDTO, IncidenteDTO, …)
│   └── dao/
│       ├── interfaces.py          13 interfaces DAO
│       ├── sql_conocimiento.py    ConocimientoDAOSQL, AdministracionConocimientoDAOSQL (sedati_kb)
│       ├── sql_transaccional.py   UsuarioDAOSQL, IncidenteDAOSQL, CitaDAOSQL, DiagnosticoDAOSQL, … (sedati_trx)
│       └── fabrica.py             FabricaDAO
└── presentacion/  aplicación de escritorio (CustomTkinter): consulta rápida del motor (python main.py)
```

Las dependencias van en un solo sentido: servicio / presentación → negocio → datos.

## 5. Diseño

| Diagrama | Archivo (fuente editable al lado) |
|---|---|
| Árbol de decisión: general y una figura por rama | `diseno/arbol/*.png` (`python diseno/generar_arbol.py`, a partir de la base) |
| Caja negra | `diseno/caja_negra.png` |
| Flujo de datos | `diseno/dfd_nivel0.png`, `diseno/dfd_nivel1.png`, `diseno/dfd_nivel2_diagnostico.png` |
| Clases DAO | `diseno/clases_dao_conocimiento.png`, `diseno/clases_dao_transaccional.png` |
| Modelo relacional obtenido del SGBD | `diseno/mr_sedati_kb.png`, `diseno/mer_sedati.png` (`python diseno/generar_mer.py`, lee `information_schema` de MySQL) |
| Capturas de la web | `diseno/capturas_web/` |

## 6. API REST

Todas las rutas exigen `Authorization: Bearer <token>`, excepto `GET /api/salud` y `POST /api/auth/ingresar`. El token
lo entrega el ingreso y se renueva en cada respuesta (campo `_sesion`). Vence a los 15 minutos sin actividad.

El servidor valida el permiso de cada ruta contra la matriz `rol_permiso`. El solicitante solo ve sus propios
incidentes y citas.

La lista completa de rutas aparece en la vista **Servicio** de la web y en `RUTAS`, al final de `sedati/servicio/api.py`.

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/ingresar -H "Content-Type: application/json" \
        -d '{"correo":"admin@sedati.example","contrasena":"Sedati2026*"}' | python -c "import json,sys;print(json.load(sys.stdin)['_sesion']['token'])")
curl -X POST http://127.0.0.1:8000/api/diagnostico -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" -d '{"sintomas": [79], "respuestas": [{"evidencia_id": 87, "escala": "SI"}]}'
```

## 7. Desplegar en AWS

| Servicio | Qué aloja |
|---|---|
| Amazon RDS for MySQL | `sedati_kb` y `sedati_trx` |
| AWS Lambda | Servicio, negocio, motor y DAO |
| Amazon API Gateway | `ANY /api/{proxy+}` |
| Amazon S3 | `web/` |

1. **RDS.**
   ```bash
   python bd/instalar_mysql.py --host <endpoint-rds> --usuario admin --usuario-servicio sedati_app --demo
   ```
2. **Lambda.** Ejecute `python aws/construir_paquete_lambda.py`, que crea `dist/sedati_lambda.zip`. Configure la
   función así:
   - Python 3.13, handler `lambda_function.lambda_handler`, 512 MB, 15 s, en la VPC de RDS.
   - Variables de entorno:
     - `SEDATI_MOTOR_BD=mysql`
     - `SEDATI_MYSQL_HOST`
     - `SEDATI_MYSQL_USUARIO=sedati_app`
     - `SEDATI_MYSQL_CONTRASENA`
     - `SEDATI_MYSQL_BASE_KB=sedati_kb`
     - `SEDATI_MYSQL_BASE_TRX=sedati_trx`
     - `SEDATI_SECRETO`: una cadena aleatoria larga.
3. **API Gateway.** Cree una API HTTP con la ruta `ANY /api/{proxy+}` y la etapa `$default`.
4. **S3.** Ponga la URL de la API en `web/config.js` y suba `index.html`, `estilos.css`, `app.js`, `atencion.js` y
   `config.js`.
