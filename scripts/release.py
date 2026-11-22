"""Flujo reproducible para Windows y Linux. No necesita paquetes de Python."""
import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get('RELEASE_STATE_DIR') or str(ROOT / '.release')).resolve()


def run(*args, capture=False):
    result = subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True,
                            capture_output=capture, text=True)
    return result.stdout.strip() if capture else None


def read_env(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines()
                if line and not line.startswith('#'))


def write_env(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(''.join(f'{key}={value}\n' for key, value in data.items()), encoding='utf-8')
    temporary.replace(path)
    if os.name != 'nt':
        path.chmod(0o600)


def initialize(environment):
    directory = STATE / environment
    path = directory / 'runtime.env'
    if not path.exists():
        ports = {'staging': ('8081', '9091'), 'production': ('8080', '9090'), 'test': ('18080', '19090')}
        app_port, prom_port = ports[environment]
        write_env(path, {'APP_IMAGE': 'inventory:unreleased', 'APP_VERSION': 'unreleased',
                         'API_TOKEN': secrets.token_hex(32), 'APP_PORT': app_port,
                         'PROMETHEUS_PORT': prom_port})
    return path


def compose(environment, *args, monitoring=False, capture=False):
    path = initialize(environment)
    command = ['docker', 'compose', '--project-name', f'inventory-{environment}',
               '--env-file', str(path), '-f', str(ROOT / 'compose.yml')]
    if monitoring:
        command += ['-f', str(ROOT / 'compose.monitoring.yml')]
    return run(*command, *args, capture=capture)


def http(base, path, token='', method='GET', data=None):
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    encoded = json.dumps(data).encode() if data is not None else None
    if encoded:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(base + path, data=encoded, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def smoke(environment, expected_version=None):
    config = read_env(initialize(environment))
    base = 'http://127.0.0.1:' + config['APP_PORT']
    last = None
    for attempt in range(12):
        try:
            assert http(base, '/ready')[0] == 200, 'readiness'
            status, health = http(base, '/health')
            assert status == 200, 'health'
            assert json.loads(health)['version'] == (expected_version or config['APP_VERSION']), 'version'
            assert http(base, '/api/products', config['API_TOKEN'])[0] == 200, 'lectura autenticada'
            assert http(base, '/api/products', 'invalid')[0] == 401, 'autenticación'
            status, metrics = http(base, '/metrics')
            assert status == 200 and b'http_requests_total' in metrics, 'metrics'
            print(f'Smoke correcto: {environment} {base}')
            return
        except (OSError, AssertionError, ValueError) as error:
            last = error
            time.sleep(2)
    raise RuntimeError(f'Smoke fallido: {environment}: {last}')


def backup(environment):
    directory = STATE / environment / 'backups'
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination = directory / f'{timestamp}.sqlite'
    # SQLite online backup incorpora el WAL y es consistente con escrituras concurrentes.
    compose(environment, 'exec', '-T', 'app', 'python', '-c',
            "import sqlite3; src=sqlite3.connect('/data/inventory.sqlite'); "
            "dst=sqlite3.connect('/tmp/backup.sqlite'); src.backup(dst); dst.close(); src.close()")
    encoded = compose(environment, 'exec', '-T', 'app', 'python', '-c',
                      "import base64; from pathlib import Path; print(base64.b64encode(Path('/tmp/backup.sqlite').read_bytes()).decode())",
                      capture=True)
    destination.write_bytes(base64.b64decode(encoded, validate=True))
    import sqlite3
    with closing(sqlite3.connect(destination)) as database:
        assert database.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    print('Backup consistente:', destination)
    return destination


def restore(environment, source):
    import sqlite3
    source = Path(source).resolve()
    if not source.is_file():
        raise RuntimeError('No se encuentra el respaldo indicado')
    with closing(sqlite3.connect(f'file:{source.as_posix()}?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Respaldo corrupto; restauración rechazada')
        db.execute('SELECT sku, name, quantity FROM products LIMIT 1')
    backup(environment)
    compose(environment, 'stop', 'app')
    path = initialize(environment)
    command = ['docker', 'compose', '--project-name', f'inventory-{environment}',
               '--env-file', str(path), '-f', str(ROOT / 'compose.yml'), 'run', '--rm', '--no-deps', '-T',
               'app', 'python', '-c',
               "import sys,sqlite3; from pathlib import Path; Path('/tmp/restore.sqlite').write_bytes(sys.stdin.buffer.read()); "
               "src=sqlite3.connect('/tmp/restore.sqlite'); dst=sqlite3.connect('/data/inventory.sqlite'); "
               "src.backup(dst); dst.close(); src.close()"]
    try:
        with source.open('rb') as stream:
            subprocess.run(command, cwd=ROOT, stdin=stream, check=True)
    finally:
        compose(environment, 'up', '-d', '--wait', '--wait-timeout', '120', 'app')
    smoke(environment)
    print('Restauración correcta:', source)


def deploy(environment, image, version, monitoring=False):
    path = initialize(environment)
    current = read_env(path)
    candidate = {**current, 'APP_IMAGE': image, 'APP_VERSION': version}
    # No reconstruir ni descargar una etiqueta diferente durante promoción o rollback.
    run('docker', 'image', 'inspect', image, capture=True)
    running = compose(environment, 'ps', '--status', 'running', '-q', 'app', capture=True)
    if running:
        backup(environment)
    previous_path = path.parent / 'previous.env'
    write_env(path, candidate)
    try:
        compose(environment, 'up', '-d', '--wait', '--wait-timeout', '120', '--pull', 'never', 'app')
        smoke(environment, version)
        if monitoring:
            compose(environment, 'up', '-d', '--build', 'prometheus', 'blackbox', monitoring=True)
    except Exception:
        print('Despliegue fallido; restaurando versión anterior.', file=sys.stderr)
        write_env(path, current)
        if running:
            compose(environment, 'up', '-d', '--wait', '--wait-timeout', '120', '--pull', 'never', 'app')
            smoke(environment, current['APP_VERSION'])
        else:
            compose(environment, 'stop', 'app')
        raise
    if running:
        write_env(previous_path, current)
    manifest = {'environment': environment, 'image': image, 'version': version,
                'utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'smoke': 'passed'}
    (path.parent / 'deployment.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


def test_release(image, version):
    global STATE
    old_state = STATE
    # Proyecto fijo exclusivo de pruebas; los despliegues se serializan por workflow.
    with tempfile.TemporaryDirectory(prefix='inventory-release-') as directory:
        STATE = Path(directory)
        config = read_env(initialize('test'))
        write_env(initialize('test'), {**config, 'APP_IMAGE': image, 'APP_VERSION': version})
        try:
            compose('test', 'up', '-d', '--wait', '--wait-timeout', '120', '--pull', 'never', 'app')
            smoke('test', version)
            base = 'http://127.0.0.1:' + config['APP_PORT']
            product = {'sku': 'RELEASE-' + secrets.token_hex(8), 'name': 'Prueba de liberación', 'quantity': 5}
            assert http(base, '/api/products', config['API_TOKEN'], 'POST', product)[0] == 201
            assert http(base, '/api/products', config['API_TOKEN'], 'POST', product)[0] == 409
            assert http(base, '/api/products', config['API_TOKEN'], 'POST', {**product, 'quantity': -1})[0] == 400
            compose('test', 'restart', 'app')
            smoke('test', version)
            products = json.loads(http(base, '/api/products', config['API_TOKEN'])[1])
            assert any(row['sku'] == product['sku'] and row['quantity'] == 5 for row in products)
            print('Pruebas de liberación: CRUD, validación, auth y persistencia correctos')
        finally:
            try:
                compose('test', 'down', '--volumes')
            finally:
                STATE = old_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'test', 'build', 'test-release', 'deploy', 'smoke',
                                          'backup', 'restore', 'rollback', 'pipeline', 'status'])
    parser.add_argument('--env', choices=['staging', 'production'], default='staging')
    parser.add_argument('--image', default='inventory:local')
    parser.add_argument('--version', default='local')
    parser.add_argument('--monitoring', action='store_true')
    parser.add_argument('--backup', help='Respaldo SQLite que se restaurará explícitamente')
    args = parser.parse_args()
    if args.command == 'init':
        print('Entorno generado:', initialize(args.env))
        compose(args.env, 'config', '--quiet', monitoring=True)
    elif args.command == 'test':
        run(sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v')
    elif args.command == 'build':
        run('docker', 'build', '--pull', '-t', args.image, '.')
    elif args.command == 'test-release':
        test_release(args.image, args.version)
    elif args.command == 'pipeline':
        run(sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v')
        run('docker', 'build', '--pull', '-t', args.image, '.')
        test_release(args.image, args.version)
        deploy(args.env, args.image, args.version, args.monitoring)
    elif args.command == 'deploy':
        deploy(args.env, args.image, args.version, args.monitoring)
    elif args.command == 'smoke':
        smoke(args.env)
    elif args.command == 'backup':
        backup(args.env)
    elif args.command == 'restore':
        if not args.backup:
            parser.error('restore requiere --backup ruta.sqlite')
        restore(args.env, args.backup)
    elif args.command == 'rollback':
        previous = initialize(args.env).parent / 'previous.env'
        if not previous.exists():
            raise RuntimeError('No existe una versión anterior verificada')
        config = read_env(previous)
        deploy(args.env, config['APP_IMAGE'], config['APP_VERSION'])
    else:
        compose(args.env, 'ps', monitoring=True)


if __name__ == '__main__':
    main()
