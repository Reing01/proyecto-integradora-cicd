"""API WSGI de inventario con SQLite y métricas Prometheus, sin framework."""
import hmac
import json
import logging
import os
import sqlite3
import threading
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, float('inf'))


class Inventory:
    def __init__(self, db_path, token, version='dev'):
        if len(token) < 32:
            raise ValueError('API_TOKEN debe contener al menos 32 caracteres')
        self.db_path, self.token, self.version = str(db_path), token, version
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS products ('
                       'id INTEGER PRIMARY KEY, sku TEXT NOT NULL UNIQUE, '
                       'name TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity >= 0))')
        self.lock = threading.Lock()
        self.requests, self.buckets = Counter(), Counter()
        self.duration_sum, self.duration_count = 0.0, 0
        self.started = time.monotonic()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db_path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def metrics(self):
        with self.lock:
            lines = ['# TYPE http_requests_total counter']
            for (method, route, status), count in sorted(self.requests.items()):
                lines.append(f'http_requests_total{{method="{method}",route="{route}",status="{status}"}} {count}')
            lines.append('# TYPE http_request_duration_seconds histogram')
            for limit in BUCKETS:
                label = '+Inf' if limit == float('inf') else str(limit)
                lines.append(f'http_request_duration_seconds_bucket{{le="{label}"}} {self.buckets[limit]}')
            lines.extend([f'http_request_duration_seconds_sum {self.duration_sum}',
                          f'http_request_duration_seconds_count {self.duration_count}',
                          '# TYPE app_uptime_seconds gauge',
                          f'app_uptime_seconds {time.monotonic() - self.started}'])
        return ('\n'.join(lines) + '\n').encode()

    def dispatch(self, env):
        path, method = env.get('PATH_INFO', '/'), env.get('REQUEST_METHOD', 'GET')
        if path == '/metrics' and method == 'GET':
            return 200, self.metrics(), 'text/plain; version=0.0.4'
        if path == '/health' and method == 'GET':
            return 200, {'status': 'ok', 'version': self.version}, 'application/json'
        if path == '/ready' and method == 'GET':
            with self.connect() as db:
                db.execute('SELECT count(*) FROM products').fetchone()
            return 200, {'status': 'ready'}, 'application/json'
        if path != '/api/products':
            return 404, {'error': 'Recurso no encontrado'}, 'application/json'
        if not hmac.compare_digest(env.get('HTTP_AUTHORIZATION', ''), 'Bearer ' + self.token):
            return 401, {'error': 'No autorizado'}, 'application/json'
        if method == 'GET':
            with self.connect() as db:
                db.row_factory = sqlite3.Row
                rows = db.execute('SELECT * FROM products ORDER BY id LIMIT 1000').fetchall()
            return 200, [dict(row) for row in rows], 'application/json'
        if method != 'POST':
            return 405, {'error': 'Método no permitido'}, 'application/json'
        try:
            length = int(env.get('CONTENT_LENGTH') or 0)
            if not 0 < length <= 16384:
                return 413, {'error': 'Tamaño de cuerpo no permitido'}, 'application/json'
            data = json.loads(env['wsgi.input'].read(length))
            if (not isinstance(data, dict) or
                not isinstance(data.get('sku'), str) or not 1 <= len(data['sku'].strip()) <= 64 or
                not isinstance(data.get('name'), str) or not 1 <= len(data['name'].strip()) <= 120 or
                type(data.get('quantity')) is not int or not 0 <= data['quantity'] <= 2147483647):
                raise ValueError('Producto inválido')
        except (ValueError, UnicodeDecodeError):
            return 400, {'error': 'Se requiere sku, name y quantity entero no negativo'}, 'application/json'
        try:
            with self.connect() as db:
                cursor = db.execute('INSERT INTO products(sku,name,quantity) VALUES (?,?,?)',
                                    (data['sku'].strip(), data['name'].strip(), data['quantity']))
                product_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            return 409, {'error': 'SKU ya registrado'}, 'application/json'
        return 201, {'id': product_id, **data}, 'application/json'

    def __call__(self, env, start_response):
        started = time.monotonic()
        path = env.get('PATH_INFO', '/')
        route = path if path in ('/health', '/ready', '/metrics', '/api/products') else 'other'
        try:
            status, body, content_type = self.dispatch(env)
        except sqlite3.Error:
            logging.exception('database_error')
            status, body, content_type = 503, {'error': 'Almacenamiento no disponible'}, 'application/json'
        except Exception:
            logging.exception('request_error')
            status, body, content_type = 500, {'error': 'Error interno'}, 'application/json'
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        # Excluir probes y scrapes para que no alteren la latencia de negocio.
        if route == '/api/products' or route == 'other':
            elapsed = time.monotonic() - started
            with self.lock:
                method = env.get('REQUEST_METHOD', 'GET')
                method = method if method in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS') else 'OTHER'
                self.requests[(method, route, status)] += 1
                self.duration_sum += elapsed
                self.duration_count += 1
                for limit in BUCKETS:
                    if elapsed <= limit:
                        self.buckets[limit] += 1
        reasons = {200: 'OK', 201: 'Created', 400: 'Bad Request', 401: 'Unauthorized',
                   404: 'Not Found', 405: 'Method Not Allowed', 409: 'Conflict',
                   413: 'Content Too Large', 500: 'Internal Server Error', 503: 'Service Unavailable'}
        start_response(f'{status} {reasons[status]}', [('Content-Type', content_type),
                       ('Content-Length', str(len(body))), ('X-Content-Type-Options', 'nosniff')])
        return [body]


_instance = None
_init_lock = threading.Lock()


def application(env, start_response):
    global _instance
    with _init_lock:
        if _instance is None:
            _instance = Inventory(os.environ.get('DB_PATH', 'artifacts/inventory.sqlite'),
                                  os.environ.get('API_TOKEN', ''), os.environ.get('APP_VERSION', 'dev'))
    return _instance(env, start_response)


if __name__ == '__main__':
    from wsgiref.simple_server import make_server
    with make_server('127.0.0.1', int(os.environ.get('PORT', '8000')), application) as server:
        server.serve_forever()
