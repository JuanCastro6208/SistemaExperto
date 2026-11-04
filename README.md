# SEDATI · Sistema de inferencia

Sistema experto para el diagnóstico y asistencia técnica de incidentes en equipos de cómputo y redes.
El motor identifica las **5 hipótesis más probables con su peso probabilístico** a partir de las respuestas
del usuario, mediante **consultas sucesivas y granulares** a la base de conocimiento. No es un sistema de
condicionales: el código no contiene ningún árbol `if` del dominio, todo el conocimiento está en la tabla `granulo`.

## Cómo usarlo

### 1. Requisitos

- **Python 3.10 o superior**, con Tkinter. Viene incluido en el instalador de python.org para Windows. En Linux:
  `sudo apt install python3-tk`.
- **Git**, para descargar el proyecto.
- Opcional: **MySQL 8**. Por defecto el sistema usa SQLite, que no requiere instalar nada.

### 2. Descargar e instalar

```bash
git clone https://github.com/JuanCastro6208/SistemaExperto.git
cd SistemaExperto
python -m venv .venv                   # opcional: entorno virtual
.venv\Scripts\activate                 # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
```

La primera vez que se ejecuta, la base de conocimiento SQLite (`bd/sedati.db`) se crea sola a partir de los scripts de
`bd/`.

### 3. Opción A · Aplicación de escritorio

```bash
python main.py
```

### 4. Opción B · Interfaz web en su equipo

```bash
python servidor_web.py                 # o: python servidor_web.py --puerto 9000
```

Abra <http://localhost:8000> en el navegador. Arriba a la derecha debe decir **«En línea · SQLite · sedati.db»**.
Detenga el servidor con `Ctrl+C`.

### 5. Hacer un diagnóstico

Funciona igual en las dos interfaces:

1. **Nuevo diagnóstico.** Escriba los datos del equipo (opcionales) y marque uno o más síntomas, por ejemplo *«La
   impresora no imprime»*. Luego elija **Iniciar diagnóstico**.
2. **Responda las preguntas** con su grado de certeza: *Sí, con certeza*, *Probablemente sí*, *No lo sé*,
   *Probablemente no* o *No, con certeza*. En la web también puede responder con las teclas **1** a **5**.
   - **¿Por qué pregunta esto?** explica qué reglas usan esa observación.
   - A la derecha se ven el top 5 en vivo, la evolución de las probabilidades y las consultas que el motor hizo a la base.
   - **Deshacer respuesta** corrige la última respuesta.
3. Cuando el motor recomienda concluir, o cuando usted quiera, elija **Ver diagnóstico**. Verá:
   - las **5 hipótesis más probables** con su peso probabilístico;
   - la **acción recomendada**, con un aviso si hay riesgo de perder datos;
   - **cómo se llegó a la conclusión**: cada regla con sus condiciones cumplidas (✔) o negadas (✖) y el cálculo de su aporte.
4. **Guardar consulta** la registra en la base. Después puede **descargar el informe** en texto.
5. Otras secciones:
   - **Historial:** las consultas guardadas.
   - **Base de conocimiento:** las hipótesis, sus reglas If / And / Then y las evidencias.

### 6. Pruebas automáticas

```bash
python -m unittest discover -s tests -v      # 22 pruebas: motor, API y handler de Lambda
```

### 7. Usar MySQL 8 en lugar de SQLite

1. En MySQL Workbench, ejecute en este orden:
   - `bd/mysql/01_esquema.sql`, que crea la base `sedati`;
   - `bd/02_datos_conocimiento.sql`;
   - `bd/03_datos_operacion.sql`.

   Otra opción es cargarlos con
   `python aws/cargar_base_conocimiento.py --host localhost --usuario root`.
2. En `config.ini` ponga `motor = mysql` y llene usuario y contraseña en la sección `[mysql]`.

Los dos motores dan los mismos resultados: los 12 casos de prueba se verificaron en ambos.

### 8. Configuración

Los parámetros del motor están en la sección `[motor]` de `config.ini`:

| Parámetro | Para qué sirve | Valor por defecto |
|---|---|---|
| `beta` | Sensibilidad del peso probabilístico al factor de certeza | 5,0 |
| `umbral_probabilidad` | Probabilidad de la hipótesis líder con la que se recomienda concluir | 0,85 |
| `ganancia_minima` | Ganancia de información mínima, en bits, para seguir preguntando | 0,01 |
| `max_preguntas` | Número máximo de preguntas | 20 |
| `hipotesis_resultado` | Número de hipótesis que entrega el sistema | 5 |
| `aplicabilidad_base` | Peso de una regla cuyo síntoma de entrada no fue reportado | 0,10 |

La conexión a la base también se puede indicar con variables de entorno, que tienen prioridad sobre `config.ini`:
`SEDATI_MOTOR_BD` (`sqlite` o `mysql`), `SEDATI_RUTA_SQLITE`, `SEDATI_MYSQL_HOST`, `SEDATI_MYSQL_PUERTO`,
`SEDATI_MYSQL_USUARIO`, `SEDATI_MYSQL_CONTRASENA` y `SEDATI_MYSQL_BASE`.

## El sistema experto como servicio web (API REST)

El mismo motor se publica como **API REST** y lo consume la **interfaz web** (`web/`):

- `sedati/servicio/` es la capa de servicio. Traduce las peticiones HTTP a la capa de negocio y **no guarda estado**: el
  cliente envía los síntomas y todas las respuestas, y el motor rehace el razonamiento en cada llamada.
- `servidor_web.py` es el servidor local, hecho solo con la biblioteca estándar de Python.
- `lambda_function.py` es el punto de entrada en **AWS Lambda**. Las dos atienden las mismas rutas.
- `web/` es la interfaz estática (HTML, CSS y JS sin dependencias). La dirección del servicio se configura en
  `web/config.js`: vacía para usar el servidor local, o la URL de API Gateway en AWS.

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/salud` | Estado del servicio y de la base de datos |
| GET | `/api/catalogo` | Categorías, síntomas iniciales y escala de respuestas |
| POST | `/api/diagnostico` | Siguiente pregunta, top 5 con peso probabilístico, explicación y traza |
| POST | `/api/consultas` | Guarda la consulta terminada y su diagnóstico |
| GET | `/api/consultas` | Historial de consultas |
| GET | `/api/consultas/{id}` | Razonamiento de una consulta guardada |
| GET | `/api/consultas/{id}/informe` | Informe en texto |
| GET | `/api/conocimiento/hipotesis` | Hipótesis de la base de conocimiento |
| GET | `/api/conocimiento/hipotesis/{id}` | Reglas If / And / Then de una hipótesis |
| GET | `/api/conocimiento/evidencias` | Síntomas y pruebas |

Ejemplo, con el servidor local encendido:

```bash
curl -X POST http://localhost:8000/api/diagnostico -H "Content-Type: application/json" \
     -d '{"sintomas": [79], "respuestas": [{"evidencia_id": 87, "escala": "SI"}]}'
```

- `sintomas` son los `id` de las evidencias marcadas al inicio.
- `respuestas` son todas las respuestas en orden. `escala` puede ser `SI`, `PROB_SI`, `NO_SE`, `PROB_NO` o `NO`.

## Desplegar en AWS

Arquitectura: **Amazon RDS for MySQL** guarda la base de conocimiento, **AWS Lambda** ejecuta el motor de inferencia,
**Amazon API Gateway** publica la API y **Amazon S3** aloja la interfaz web.

1. **RDS.** Cree una instancia MySQL 8 (p. ej. `db.t4g.micro`, 20 GB) y permita el puerto 3306 desde su IP. Luego cargue
   la base de conocimiento y cree el usuario de la función, con permisos mínimos:
   ```bash
   python aws/cargar_base_conocimiento.py --host <endpoint-rds> --usuario admin --usuario-servicio sedati_app
   ```
2. **Lambda.** Arme el paquete con `python aws/construir_paquete_lambda.py`, que crea `dist/sedati_lambda.zip`. Cree
   una función:
   - Python 3.13, handler `lambda_function.lambda_handler`, 512 MB y 15 s.
   - En la misma VPC que RDS. Su grupo de seguridad debe poder entrar al 3306 de RDS.
   - Variables de entorno: `SEDATI_MOTOR_BD=mysql`, `SEDATI_MYSQL_HOST`, `SEDATI_MYSQL_USUARIO=sedati_app`,
     `SEDATI_MYSQL_CONTRASENA` y `SEDATI_MYSQL_BASE=sedati`.
3. **API Gateway.** Cree una API HTTP con la ruta `ANY /api/{proxy+}` integrada con la función, etapa `$default`.
4. **S3.**
   - Ponga la URL de la API en `web/config.js`.
   - Suba los archivos de `web/` a un bucket con alojamiento de sitio web estático y lectura pública.
   - Opcional: ponga la URL del sitio en la variable `SEDATI_CORS_ORIGEN` de la función.

Sin `SEDATI_MOTOR_BD=mysql`, la función usa SQLite en `/tmp`. Sirve para una demostración sin RDS, pero el historial se
pierde cuando la función se recicla.

## Entregables

| Entregable | Archivo |
|---|---|
| Diagrama de caja negra | `diseno/caja_negra.png` (fuente `.dot`) |
| Diagrama de flujo de datos | `diseno/dfd_nivel0.png` (contexto) y `diseno/dfd_nivel1.png` (notación Gane–Sarson) |
| Código fuente OO a tres capas | `sedati/datos`, `sedati/negocio`, `sedati/presentacion` · diagrama `diseno/clases_tres_capas.png` |
| Base de datos | `bd/` (MySQL 8 y SQLite) · modelo `diseno/mer_sistema_inferencia.png` |
| Complemento | `diseno/ciclo_inferencia.png` (actividades del motor) y `diseno/capturas/` (pantallas) |

## Arquitectura en tres capas

```
main.py                    arma las capas (raíz de composición)
sedati/
├── datos/                 CAPA DE DATOS — única que conoce SQL
│   ├── conexion.py        ConexionBD (abstracta) → ConexionSQLite, ConexionMySQL
│   ├── repositorio_conocimiento.py   consultas granulares a hipotesis / evidencia / granulo
│   └── repositorio_consultas.py      registro de consultas, respuestas y resultados
├── negocio/               CAPA DE NEGOCIO — sin SQL ni interfaz
│   ├── modelos.py         Hipotesis, Evidencia, Granulo, Condicion, ResultadoHipotesis, Pregunta…
│   ├── memoria_trabajo.py hechos conocidos y conocimiento ya consultado
│   ├── motor_inferencia.py  encadenamiento hacia adelante y cálculo de pesos
│   ├── selector_preguntas.py  siguiente pregunta por ganancia de información
│   ├── certeza.py         fórmulas (MYCIN, aplicabilidad, distribución, entropía)
│   ├── explicacion.py     «¿por qué pregunta esto?» y «¿cómo llegó a esta conclusión?»
│   └── servicios.py       ServicioDiagnostico, SesionDiagnostico, ServicioConocimiento
├── servicio/              CAPA DE SERVICIO — API REST para la web y AWS Lambda
│   ├── api.py             rutas /api/* sobre los servicios de negocio
│   └── serializacion.py   objetos del motor → JSON
└── presentacion/          CAPA DE PRESENTACIÓN — CustomTkinter + matplotlib
    ├── aplicacion.py      ventana principal y navegación
    ├── vista_inicio.py    nuevo diagnóstico (equipo y síntomas)
    ├── vista_consulta.py  preguntas, respuestas graduadas y razonamiento en vivo
    ├── vista_resultado.py las 5 hipótesis, su explicación y la acción recomendada
    ├── vista_conocimiento.py  explorador de la base de conocimiento
    └── vista_historial.py consultas guardadas
```

Las dependencias van en un solo sentido: presentación → negocio → datos.

## Cómo razona el motor

**1. Respuestas graduadas.** El usuario no responde solo sí o no. Indica qué tan seguro está de cada observación,
y la tabla `escala_respuesta` traduce cada respuesta a un valor:

| Respuesta | Sí, con certeza | Probablemente sí | No lo sé | Probablemente no | No, con certeza |
|---|---|---|---|---|---|
| Valor | +1,0 | +0,6 | 0 | −0,6 | −1,0 |

**2. Consultas sucesivas y granulares.** El motor no carga la base completa. Va trayendo solo lo que necesita:
- los gránulos que contienen los síntomas reportados;
- el resto de gránulos de esas categorías, que forman el diagnóstico diferencial;
- las condiciones de esas reglas y las evidencias equivalentes.

Cada respuesta afirmativa dispara una nueva consulta por los gránulos que contienen esa evidencia. La pestaña
*Consultas a la base* muestra la traza de cada consulta.

**3. Deducción entre evidencias.** Las evidencias que describen la misma observación comparten una `variable`, y su
`polaridad` indica si la afirman (+1) o la niegan (−1). Por ejemplo, *«hay tensión en la toma»* (+1) y *«no hay
tensión en la toma»* (−1). Al responder una, el motor deduce las demás y no las vuelve a preguntar.

**4. Evaluación de cada gránulo (regla If / And / Then).** El síntoma de entrada (la condición *If*) decide si la
regla aplica, y las condiciones *And* la confirman:

```
grado(g)   = Σ peso_i · v_i / Σ peso_i                 (sobre las condiciones And; v_i ∈ [−1, 1], 0 si se desconoce)
a(g)       = a0 + (1 − a0)·v_If   si v_If ≥ 0          (aplicabilidad; a0 = 0,10 en config.ini)
           = a0 · (1 + v_If)      si v_If < 0
aporte(g)  = a(g) · grado(g) · factor_certeza(g)
```

Con todas las condiciones confirmadas, el aporte es igual al factor de certeza del experto.

**5. Factor de certeza de cada hipótesis.** Sus reglas son caminos alternativos. Los aportes positivos se refuerzan
con la regla de MYCIN, `a + b(1 − a)`. Si ningún camino la apoya, se toma el aporte menos negativo: negar una regla
no descarta las demás reglas de la misma hipótesis.

**6. Peso probabilístico.**

```
previa_ctx(h) = Σ_g  previa(h)/reglas(h) · a(g)
P(h)          = previa_ctx(h) · e^(β·FC(h)) / Σ_j previa_ctx(j) · e^(β·FC(j))      (β = 5)
```

`previa(h)` viene de la distribución de casos de la revisión documental (sección 9.5 del documento): red 31 %,
software y accesos 22 %, etc. Se reparte entre las reglas de cada categoría.

**7. Selección de la siguiente pregunta.** Para cada observación pendiente, el motor simula las respuestas «Sí» y
«No» y pregunta por la que más reduce la entropía de la distribución:

```
ganancia(q) = H(P) − [ P(sí|q)·H(P | q = sí) + P(no|q)·H(P | q = no) ]
```

Las condiciones *And* de una regla solo se preguntan cuando su síntoma de entrada está confirmado.

**8. Cuándo concluir.** El motor recomienda concluir en cualquiera de estos casos:
- la hipótesis líder llega al 85 %;
- ninguna pregunta aporta más de 0,01 bits;
- no quedan preguntas;
- se llegó a 20 preguntas.

El usuario puede ver el diagnóstico en cualquier momento o seguir respondiendo.

## Base de datos

**Base de conocimiento: exactamente 3 tablas.**
- `hipotesis` (38): incluye `probabilidad_previa`.
- `evidencia` (153): 29 síntomas y 124 pruebas, con `pregunta`, `variable` y `polaridad`.
- `granulo` (224 filas): una fila por cada condición de las 88 reglas, con `regla`, `orden`, `conector`, `peso`,
  conclusión, acción, factor de certeza y riesgo de pérdida de datos.

**Operación del motor: 4 tablas.**
- `escala_respuesta`
- `consulta`
- `consulta_respuesta`
- `consulta_hipotesis`: guarda el top 5 con su probabilidad y certeza.

Las reglas, hipótesis y evidencias provienen del documento del proyecto (capítulo 11 y sección 14.4).
- La asignación de cada regla a su hipótesis se reconstruyó y se verificó contra la tabla de la sección 14.4:
  número de gránulos, certezas mínima y máxima, y ramas de cada hipótesis.
- Los 26 códigos E-NNN que el documento publica en sus consultas coinciden.
- Las variables observables, las probabilidades previas y las marcas de riesgo son conocimiento añadido en esta
  entrega. Conviene que las valide el experto.
