# SEDATI · Sistema experto para el diagnóstico de fallas de cómputo y redes

Aplicación web **sin cuentas, sin contraseñas y sin roles**: la persona escribe su nombre («¿Cómo te llamas?») y empieza
a diagnosticar.

El diagnóstico sigue el **árbol de decisión**:

1. Se pregunta categoría por categoría, en orden: primero **A. Energía y arranque**, después **B. Video y pantalla**, y
   así sucesivamente.
2. En la categoría donde la persona responde **Sí**, marca lo que ocurre (los síntomas de entrada de cada rama).
3. El **motor de inferencia** continúa con las preguntas necesarias. Se responde con grado de certeza (Sí, con certeza ·
   Probablemente sí · No lo sé · Probablemente no · No, con certeza).
4. El sistema entrega las **5 hipótesis más probables con su peso probabilístico**, la acción recomendada y la
   explicación del razonamiento. El diagnóstico se guarda con el nombre de quien consultó.

El motor no es un árbol de `if` en el código: todo el conocimiento (88 reglas If / And / Then, 38 hipótesis) está en la
base de conocimiento (`sedati_kb`), y el motor la consulta de forma **granular** (solo los gránulos que necesita en
cada paso).

## 1. Ejecutarlo en su equipo

Requisitos: **Python 3.10 o superior**. No hace falta instalar ninguna base de datos: por defecto usa SQLite.

```bash
git clone https://github.com/JuanCastro6208/SistemaExperto.git
cd SistemaExperto
pip install -r requirements.txt
python servidor_web.py
```

Abra **<http://127.0.0.1:8000>**, escriba su nombre y pulse **Nuevo diagnóstico**.

En Visual Studio Code: abra la carpeta, vaya a **Ejecutar y depurar** (Ctrl+Shift+D), elija
**SEDATI · servidor web** y pulse F5.

La primera vez, las dos bases se crean solas a partir de los scripts de `bd/`: `bd/sedati_kb.db` y `bd/sedati_trx.db`.
Para empezar de cero, borre esos dos archivos `.db`.

### Secciones de la web

| Pestaña | Qué hace |
|---|---|
| Diagnóstico | Recorrido del árbol, preguntas del motor con razonamiento en vivo y resultado |
| Historial | Diagnósticos guardados; se puede filtrar por nombre y ver el razonamiento o el informe |
| Base de conocimiento | Hipótesis, evidencias y gránulos (If / And / Then) de solo lectura |
| Servicio | Estado del servicio y lista de rutas de la API |

## 2. Pruebas automáticas

```bash
python -m unittest discover -s tests -v
```

Son 29 pruebas: 19 del motor y 10 de la API y del handler de Lambda.

Las pruebas de la API también corren contra un MySQL 8 real:

```bash
SEDATI_PRUEBAS_MYSQL=127.0.0.1:3306:root:<contraseña> python -m unittest tests.test_api
```

## 3. Usar MySQL 8

1. Instale las dos bases. Esto ejecuta, en orden, los mismos scripts que se abren en MySQL Workbench:
   ```bash
   python bd/instalar_mysql.py --host localhost --usuario root --usuario-servicio sedati_app
   ```
2. En `config.ini` ponga `motor = mysql` y escriba el usuario y la contraseña en `[mysql]`.

| Script | Contenido |
|---|---|
| `bd/mysql/01_kb_esquema.sql` | Base de conocimiento `sedati_kb`: **exactamente 3 tablas** (`hipotesis`, `evidencia`, `granulo`) y sus disparadores |
| `bd/02_kb_datos.sql` | Conocimiento del experto: 38 hipótesis, 153 evidencias, 88 reglas (224 filas de `granulo`) |
| `bd/mysql/03_trx_esquema.sql` | Base transaccional `sedati_trx`: 4 tablas (`escala_respuesta`, `diagnostico`, `incidente_evidencia`, `diagnostico_hipotesis`) |
| `bd/04_trx_datos.sql` | Escala de respuestas graduadas |
| `bd/mysql/05_roles_permisos.sql` | Rol de MySQL `sedati_aplicacion` para la cuenta del servicio, sin permiso de borrado |
| `bd/mysql/06_consultas_granulos_por_hipotesis.sql` | Vistas, procedimientos de inferencia en SQL y consultas del manual |

Los scripts de `bd/sqlite/` son los equivalentes para SQLite.

## 4. Arquitectura

```
servidor_web.py · lambda_function.py   puntos de entrada (local / AWS Lambda)
web/                                   interfaz web (HTML, CSS y JS sin dependencias)
sedati/
├── servicio/   CAPA DE SERVICIO: API REST (api.py) y serialización
├── negocio/    CAPA DE NEGOCIO: sin SQL ni interfaz
│   ├── motor_inferencia.py, memoria_trabajo.py, selector_preguntas.py, certeza.py, explicacion.py
│   └── servicios.py               ServicioDiagnostico y ServicioConocimiento
├── datos/      CAPA DE DATOS: patrón DAO, la única que conoce SQL
│   ├── conexion.py                ConexionBD (abstracta) → ConexionSQLite, ConexionMySQL
│   ├── dto.py                     DiagnosticoDTO, RespuestaDTO, HipotesisPropuestaDTO
│   └── dao/
│       ├── interfaces.py          ConocimientoDAO, CatalogoDAO, DiagnosticoDAO
│       ├── sql_conocimiento.py    ConocimientoDAOSQL (sedati_kb)
│       ├── sql_transaccional.py   CatalogoDAOSQL, DiagnosticoDAOSQL (sedati_trx)
│       └── fabrica.py             FabricaDAO
└── presentacion/  aplicación de escritorio (CustomTkinter): consulta rápida del motor (python main.py)
```

Las dependencias van en un solo sentido: servicio / presentación → negocio → datos.

## 5. API REST

Ninguna ruta pide autenticación. La lista completa aparece en la pestaña **Servicio** y en `RUTAS`, al final de
`sedati/servicio/api.py`.

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/salud` | Estado del servicio y de las dos bases |
| GET | `/api/catalogo` | Árbol de decisión (categoría → rama → síntomas) y escala de respuestas |
| POST | `/api/diagnostico` | Siguiente pregunta, top 5 con peso probabilístico y explicación |
| POST | `/api/consultas` | Guardar el diagnóstico con el nombre de quien consultó |
| GET | `/api/consultas` | Historial (`?nombre=` para ver solo los de una persona) |
| GET | `/api/consultas/{id}` | Razonamiento de un diagnóstico guardado |
| GET | `/api/consultas/{id}/informe` | Informe en texto |
| GET | `/api/conocimiento/hipotesis` | Hipótesis |
| GET | `/api/conocimiento/hipotesis/{id}` | Gránulos de una hipótesis |
| GET | `/api/conocimiento/evidencias` | Síntomas y pruebas |

```bash
curl -X POST http://127.0.0.1:8000/api/diagnostico -H "Content-Type: application/json" \
     -d '{"sintomas": [1], "respuestas": []}'
```

## 6. Desplegar en AWS

| Servicio | Qué aloja |
|---|---|
| Amazon RDS for MySQL | `sedati_kb` y `sedati_trx` |
| AWS Lambda | Servicio, negocio, motor y DAO |
| Amazon API Gateway | `ANY /api/{proxy+}` |
| Amazon S3 | `web/` |

1. **RDS.**
   ```bash
   python bd/instalar_mysql.py --host <endpoint-rds> --usuario admin --usuario-servicio sedati_app
   ```
2. **Lambda.** Ejecute `python aws/construir_paquete_lambda.py`, que crea `dist/sedati_lambda.zip`. Configure la
   función así:
   - Python 3.13, handler `lambda_function.lambda_handler`, 512 MB, 15 s, en la VPC de RDS.
   - Variables de entorno: `SEDATI_MOTOR_BD=mysql`, `SEDATI_MYSQL_HOST`, `SEDATI_MYSQL_USUARIO=sedati_app`,
     `SEDATI_MYSQL_CONTRASENA`, `SEDATI_MYSQL_BASE_KB=sedati_kb`, `SEDATI_MYSQL_BASE_TRX=sedati_trx`.
3. **API Gateway.** Cree una API HTTP con la ruta `ANY /api/{proxy+}` y la etapa `$default`.
4. **S3.** Ponga la URL de la API en `web/config.js` y suba `index.html`, `estilos.css`, `app.js` y `config.js`.
