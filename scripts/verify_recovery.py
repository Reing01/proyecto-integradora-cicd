"""Simulacro aislado de backup, restauración y rollback ante fallo de smoke."""
import argparse
import json
from pathlib import Path
import tempfile
import release


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', default='inventory:1.0.0')
    args = parser.parse_args()
    previous_state = release.STATE
    with tempfile.TemporaryDirectory(prefix='inventory-recovery-') as directory:
        release.STATE = Path(directory)
        try:
            release.deploy('test', args.image, 'recovery-a')
            config = release.read_env(release.initialize('test'))
            base = 'http://127.0.0.1:' + config['APP_PORT']
            token = config['API_TOKEN']
            assert release.http(base, '/api/products', token, 'POST',
                {'sku': 'RECOVERY-1', 'name': 'Producto conservado', 'quantity': 7})[0] == 201
            saved = release.backup('test')
            assert release.http(base, '/api/products', token, 'POST',
                {'sku': 'RECOVERY-2', 'name': 'Posterior al respaldo', 'quantity': 2})[0] == 201
            release.restore('test', saved)
            products = json.loads(release.http(base, '/api/products', token)[1])
            assert [p['sku'] for p in products] == ['RECOVERY-1']
            release.deploy('test', args.image, 'recovery-b')
            real_smoke = release.smoke

            def fail_candidate(environment, expected_version=None):
                if expected_version == 'controlled-failure':
                    raise RuntimeError('Fallo de smoke inyectado por el simulacro')
                return real_smoke(environment, expected_version)

            release.smoke = fail_candidate
            try:
                release.deploy('test', args.image, 'controlled-failure')
                raise AssertionError('La versión fallida no debió aceptarse')
            except RuntimeError as error:
                assert 'inyectado' in str(error)
            finally:
                release.smoke = real_smoke
            assert json.loads(release.http(base, '/health')[1])['version'] == 'recovery-b'
            assert json.loads(release.http(base, '/api/products', token)[1])[0]['quantity'] == 7
            print('RECOVERY PASSED: respaldo íntegro, restauración y rollback automático con datos conservados')
        finally:
            try:
                release.compose('test', 'down', '--volumes')
            finally:
                release.STATE = previous_state


if __name__ == '__main__':
    main()
