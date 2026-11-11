"""Arma el paquete .zip que se sube a AWS Lambda.

    python aws/construir_paquete_lambda.py

Resultado: dist/sedati_lambda.zip con
    lambda_function.py           handler de Lambda
    config.ini                   parámetros del motor (la conexión llega por variables de entorno)
    sedati/                      capas de datos, negocio y servicio (sin la interfaz de escritorio)
    bd/                          scripts SQL (para el modo SQLite de demostración)
    pymysql/                     controlador de MySQL (Python puro, funciona en cualquier arquitectura)
"""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIST = RAIZ / 'dist'
CONSTRUCCION = DIST / 'lambda'
ZIP = DIST / 'sedati_lambda.zip'

IGNORAR = shutil.ignore_patterns('__pycache__', '*.pyc', 'presentacion', '*.db', '.secreto_sesiones', '*.local.txt')


def main():
    if CONSTRUCCION.exists():
        shutil.rmtree(CONSTRUCCION)
    CONSTRUCCION.mkdir(parents=True)

    shutil.copy2(RAIZ / 'lambda_function.py', CONSTRUCCION)
    shutil.copy2(RAIZ / 'config.ini', CONSTRUCCION)
    shutil.copytree(RAIZ / 'sedati', CONSTRUCCION / 'sedati', ignore=IGNORAR)
    shutil.copytree(RAIZ / 'bd', CONSTRUCCION / 'bd', ignore=IGNORAR)

    print('Instalando PyMySQL en el paquete…')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', '--disable-pip-version-check',
                    '--target', str(CONSTRUCCION), 'pymysql>=1.1'], check=True)

    ZIP.unlink(missing_ok=True)
    with zipfile.ZipFile(ZIP, 'w', zipfile.ZIP_DEFLATED) as z:
        for archivo in sorted(CONSTRUCCION.rglob('*')):
            if archivo.is_file() and '__pycache__' not in archivo.parts:
                z.write(archivo, archivo.relative_to(CONSTRUCCION).as_posix())
    print(f'Paquete listo: {ZIP}  ({ZIP.stat().st_size / 1024:.0f} KB)')
    print('Súbalo en la consola de Lambda: Código → Cargar desde → archivo .zip')
    print('Handler: lambda_function.lambda_handler   ·   Runtime: Python 3.13')
    return 0


if __name__ == '__main__':
    sys.exit(main())
