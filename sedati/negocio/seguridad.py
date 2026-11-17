"""Contraseñas y sesiones de SEDATI. Solo usa la biblioteca estándar.

Contraseñas: PBKDF2-HMAC-SHA256 con sal aleatoria de 16 bytes y 120 000 iteraciones.
    Formato guardado: pbkdf2_sha256$<iteraciones>$<sal base64>$<hash base64>
    La contraseña nunca se guarda ni se muestra en texto plano.

Sesiones: el servicio web no guarda estado (AWS Lambda), así que la sesión viaja en un token
firmado con HMAC-SHA256:   base64url(datos JSON) . base64url(firma)
    datos = {"uid": id del usuario, "exp": vencimiento (epoch)}
Cada petición autenticada devuelve un token renovado; si pasan MINUTOS_SESION sin actividad, vence.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time

ITERACIONES = 120_000
MINUTOS_SESION = 30
INTENTOS_MAXIMOS = 5
MINUTOS_BLOQUEO = 15


def _b64(datos):
    return base64.urlsafe_b64encode(datos).rstrip(b'=').decode('ascii')


def _de_b64(texto):
    return base64.urlsafe_b64decode(texto + '=' * (-len(texto) % 4))


# ================================================================ contraseñas
def hash_contrasena(contrasena, sal=None, iteraciones=ITERACIONES):
    sal = sal or secrets.token_bytes(16)
    derivada = hashlib.pbkdf2_hmac('sha256', contrasena.encode('utf-8'), sal, iteraciones)
    return f'pbkdf2_sha256${iteraciones}${_b64(sal)}${_b64(derivada)}'


def verificar_contrasena(contrasena, guardado):
    try:
        algoritmo, iteraciones, sal, esperado = guardado.split('$')
        if algoritmo != 'pbkdf2_sha256':
            return False
        derivada = hashlib.pbkdf2_hmac('sha256', contrasena.encode('utf-8'), _de_b64(sal), int(iteraciones))
        return hmac.compare_digest(_b64(derivada), esperado)
    except (ValueError, AttributeError):
        return False


def validar_politica(contrasena):
    """Devuelve el motivo por el que la contraseña no cumple la política, o None si la cumple."""
    if len(contrasena) < 8:
        return 'La contraseña debe tener al menos 8 caracteres.'
    if len(contrasena) > 128:
        return 'La contraseña no puede tener más de 128 caracteres.'
    if not any(c.isdigit() for c in contrasena) or not any(c.isalpha() for c in contrasena):
        return 'La contraseña debe combinar letras y números.'
    return None


# ================================================================ sesiones
class FirmadorSesion:
    def __init__(self, secreto, minutos=MINUTOS_SESION):
        if not secreto:
            raise ValueError('Se necesita un secreto para firmar las sesiones.')
        self._clave = secreto.encode('utf-8') if isinstance(secreto, str) else secreto
        self.minutos = minutos

    def _firma(self, cuerpo):
        return _b64(hmac.new(self._clave, cuerpo.encode('ascii'), hashlib.sha256).digest())

    def emitir(self, usuario_id, ahora=None):
        """Devuelve (token, vencimiento en segundos epoch)."""
        exp = int((time.time() if ahora is None else ahora) + self.minutos * 60)
        cuerpo = _b64(json.dumps({'uid': usuario_id, 'exp': exp}, separators=(',', ':')).encode('utf-8'))
        return f'{cuerpo}.{self._firma(cuerpo)}', exp

    def leer(self, token, ahora=None):
        """Datos de la sesión si el token es auténtico y no ha vencido; None en otro caso."""
        try:
            cuerpo, firma = token.split('.')
            if not hmac.compare_digest(self._firma(cuerpo), firma.encode('ascii').decode('ascii')):
                return None
        except (ValueError, AttributeError, TypeError):   # forma inválida o caracteres no ASCII
            return None
        try:
            datos = json.loads(_de_b64(cuerpo))
        except ValueError:
            return None
        if not isinstance(datos, dict) or datos.get('exp', 0) < (time.time() if ahora is None else ahora):
            return None
        return datos
