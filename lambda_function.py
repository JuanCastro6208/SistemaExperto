"""Punto de entrada de SEDATI en AWS Lambda (detrás de Amazon API Gateway, API HTTP, payload 2.0).

Handler de Lambda:  lambda_function.lambda_handler

Variables de entorno de la función:
    SEDATI_MOTOR_BD=mysql
    SEDATI_MYSQL_HOST=<punto de enlace de Amazon RDS>
    SEDATI_MYSQL_USUARIO, SEDATI_MYSQL_CONTRASENA
    SEDATI_MYSQL_BASE_KB=sedati_kb, SEDATI_MYSQL_BASE_TRX=sedati_trx
    SEDATI_CORS_ORIGEN=<URL del sitio web> (opcional; por defecto *)

Sin SEDATI_MOTOR_BD=mysql usa SQLite en /tmp: las dos bases se crean al arrancar a partir de los scripts
de bd/ (sirve para una demostración sin RDS, pero lo registrado se pierde al reciclar la función).
"""
import base64
import json
import os
import traceback

os.environ.setdefault('SEDATI_RUTA_SQLITE_KB', '/tmp/sedati_kb.db')    # el paquete de Lambda es de solo lectura
os.environ.setdefault('SEDATI_RUTA_SQLITE_TRX', '/tmp/sedati_trx.db')

from sedati.servicio import ApiSEDATI  # noqa: E402

_api = None   # se reutiliza entre invocaciones mientras la función esté «caliente»


def _cabeceras():
    return {
        'Content-Type': 'application/json; charset=utf-8',
        'Access-Control-Allow-Origin': os.environ.get('SEDATI_CORS_ORIGEN', '*'),
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
    }


def _respuesta(estado, datos):
    return {'statusCode': estado, 'headers': _cabeceras(),
            'body': json.dumps(datos, ensure_ascii=False, default=str)}


def lambda_handler(event, context):
    global _api
    http = (event.get('requestContext') or {}).get('http') or {}
    metodo = http.get('method') or event.get('httpMethod') or 'GET'
    ruta = event.get('rawPath') or event.get('path') or '/'
    if metodo == 'OPTIONS':                     # verificación previa de CORS del navegador
        return {'statusCode': 204, 'headers': _cabeceras(), 'body': ''}
    try:
        cuerpo = event.get('body')
        if cuerpo and event.get('isBase64Encoded'):
            cuerpo = base64.b64decode(cuerpo).decode('utf-8')
        try:
            cuerpo = json.loads(cuerpo) if cuerpo else {}
        except json.JSONDecodeError:
            return _respuesta(400, {'error': 'El cuerpo de la petición no es JSON válido.'})
        if _api is None:
            _api = ApiSEDATI()
        ip = http.get('sourceIp') or ((event.get('requestContext') or {}).get('identity') or {}).get('sourceIp')
        estado, datos = _api.atender(metodo, ruta, cuerpo, event.get('headers') or {},
                                     event.get('queryStringParameters') or {}, ip)
        return _respuesta(estado, datos)
    except Exception as error:  # noqa: BLE001 - cualquier fallo se registra en CloudWatch y se informa
        traceback.print_exc()
        _api = None                 # se vuelve a conectar en la siguiente invocación
        return _respuesta(500, {'error': f'Error interno del servicio: {error}'})
