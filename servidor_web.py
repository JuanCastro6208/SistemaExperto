"""Servidor local de SEDATI: publica la API y la interfaz web en http://localhost:8000.

    python servidor_web.py              # usa la base indicada en config.ini (SQLite por defecto)
    python servidor_web.py --puerto 9000

Sirve para probar todo en el equipo antes de desplegarlo en AWS. Atiende las mismas rutas que la
función Lambda (lambda_function.py), con el mismo código de la capa de servicio.
Solo usa la biblioteca estándar de Python.
"""
import argparse
import json
import mimetypes
import sys
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sedati.servicio import ApiSEDATI

WEB = Path(__file__).resolve().parent / 'web'
mimetypes.add_type('application/javascript', '.js')


class Manejador(BaseHTTPRequestHandler):
    api = None

    def _enviar(self, estado, contenido, tipo):
        self.send_response(estado)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(contenido)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
        self.wfile.write(contenido)

    def _json(self, estado, datos):
        self._enviar(estado, json.dumps(datos, ensure_ascii=False, default=str).encode('utf-8'),
                     'application/json; charset=utf-8')

    def _api(self, metodo):
        cuerpo = {}
        if metodo == 'POST':
            largo = int(self.headers.get('Content-Length') or 0)
            try:
                cuerpo = json.loads(self.rfile.read(largo) or b'{}')
            except json.JSONDecodeError:
                return self._json(400, {'error': 'El cuerpo de la petición no es JSON válido.'})
        try:
            url = urlparse(self.path)
            consulta = {k: v[0] for k, v in parse_qs(url.query).items()}
            estado, datos = self.api.atender(metodo, url.path, cuerpo, dict(self.headers.items()), consulta,
                                             self.client_address[0])
        except Exception as error:  # noqa: BLE001
            traceback.print_exc()
            estado, datos = 500, {'error': f'Error interno del servicio: {error}'}
        self._json(estado, datos)

    def _archivo(self):
        ruta = urlparse(self.path).path
        destino = (WEB / ruta.lstrip('/')).resolve()
        if ruta.endswith('/'):
            destino = destino / 'index.html'
        if WEB not in destino.parents or not destino.is_file():
            return self._enviar(404, b'No encontrado', 'text/plain; charset=utf-8')
        tipo = mimetypes.guess_type(destino.name)[0] or 'application/octet-stream'
        if tipo.startswith('text/') or tipo == 'application/javascript':
            tipo += '; charset=utf-8'
        self._enviar(200, destino.read_bytes(), tipo)

    def do_OPTIONS(self):  # noqa: N802
        self._enviar(204, b'', 'text/plain')

    def do_GET(self):  # noqa: N802
        if urlparse(self.path).path.startswith('/api/'):
            self._api('GET')
        else:
            self._archivo()

    def do_POST(self):  # noqa: N802
        self._api('POST')

    def log_message(self, formato, *args):
        sys.stderr.write(f'  {self.command:<6} {self.path}  →  {args[1] if len(args) > 1 else ""}\n')


def main():
    parser = argparse.ArgumentParser(description='Servidor local de SEDATI (API + interfaz web).')
    parser.add_argument('--puerto', type=int, default=8000)
    args = parser.parse_args()
    Manejador.api = ApiSEDATI()
    servidor = HTTPServer(('127.0.0.1', args.puerto), Manejador)
    print(f'SEDATI · servicio web en http://127.0.0.1:{args.puerto}  (base: {Manejador.api.fabrica.descripcion})')
    print('Cuentas de demostración: admin@sedati.example / solicitante@sedati.example  ·  contraseña Sedati2026*')
    print('Ctrl+C para detener.')
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        Manejador.api.fabrica.cerrar()
    return 0


if __name__ == '__main__':
    sys.exit(main())
