import io
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from app.main import Inventory


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.sqlite'
        self.token = 'test-only-' + 'x' * 32
        self.app = Inventory(self.path, self.token, 'test')

    def request(self, path='/api/products', method='GET', data=None, token=None, raw=None):
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else b''
        result = {}
        env = {'PATH_INFO': path, 'REQUEST_METHOD': method, 'CONTENT_LENGTH': str(len(body)),
               'wsgi.input': io.BytesIO(body), 'HTTP_AUTHORIZATION': 'Bearer ' + (token or self.token)}
        response = b''.join(self.app(env, lambda status, headers: result.update(status=int(status[:3]))))
        return result['status'], response

    def test_create_and_persist(self):
        self.assertEqual(self.request(method='POST', data={'sku': 'A1', 'name': 'Arroz', 'quantity': 3})[0], 201)
        restarted = Inventory(self.path, self.token)
        self.app = restarted
        status, body = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)[0]['quantity'], 3)

    def test_reject_negative_quantity(self):
        self.assertEqual(self.request(method='POST', data={'sku': 'A', 'name': 'B', 'quantity': -1})[0], 400)

    def test_reject_boolean_quantity(self):
        self.assertEqual(self.request(method='POST', data={'sku': 'A', 'name': 'B', 'quantity': True})[0], 400)

    def test_reject_invalid_json_and_arrays(self):
        for raw in (b'{', b'[]', b'null', b'\xff'):
            self.assertEqual(self.request(method='POST', raw=raw)[0], 400)

    def test_reject_oversized_body(self):
        self.assertEqual(self.request(method='POST', raw=b'x' * 16385)[0], 413)

    def test_authentication(self):
        self.assertEqual(self.request(token='incorrect')[0], 401)

    def test_duplicate_sku(self):
        product = {'sku': 'A', 'name': 'B', 'quantity': 1}
        self.assertEqual(self.request(method='POST', data=product)[0], 201)
        self.assertEqual(self.request(method='POST', data=product)[0], 409)

    def test_sql_injection_is_data(self):
        product = {'sku': "'); DROP TABLE products; --", 'name': 'B', 'quantity': 1}
        self.assertEqual(self.request(method='POST', data=product)[0], 201)
        self.assertEqual(len(json.loads(self.request()[1])), 1)

    def test_concurrent_writes(self):
        def create(index):
            return self.request(method='POST', data={'sku': str(index), 'name': 'B', 'quantity': 1})[0]
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(create, range(20))), [201] * 20)

    def test_probes_and_metrics(self):
        for path in ('/health', '/ready'):
            self.assertEqual(self.request(path=path)[0], 200)
        self.request()
        metrics = self.request(path='/metrics')[1].decode()
        self.assertIn('http_request_duration_seconds_count 1', metrics)
        self.assertIn('status="200"} 1', metrics)

    def test_readiness_detects_missing_schema(self):
        with self.app.connect() as db:
            db.execute('DROP TABLE products')
        with self.assertLogs(level='ERROR'):
            self.assertEqual(self.request(path='/ready')[0], 503)

    def test_unknown_route_and_method(self):
        self.assertEqual(self.request(path='/secret')[0], 404)
        self.assertEqual(self.request(method='DELETE')[0], 405)

    def test_requires_strong_token(self):
        with self.assertRaises(ValueError):
            Inventory(self.path, 'weak')


if __name__ == '__main__':
    unittest.main()
