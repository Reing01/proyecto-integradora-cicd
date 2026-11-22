"""Crear repositorio privado y entornos mediante credenciales de Git existentes.

Nunca imprime ni guarda el token. Alternativa: variable de entorno GH_TOKEN.
"""
import argparse
import json
import os
import subprocess
import urllib.error
import urllib.request


def credential():
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        return token
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'}
    result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                            text=True, capture_output=True, env=env)
    if result.returncode:
        raise RuntimeError('No hay una sesión local de GitHub disponible. Inicia sesión con Git Credential Manager o define GH_TOKEN.')
    values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if not values.get('password'):
        raise RuntimeError('La sesión de Git no proporcionó una credencial de GitHub')
    return values['password']


def api(token, path, method='GET', data=None):
    request = urllib.request.Request('https://api.github.com' + path,
        data=json.dumps(data).encode() if data is not None else None, method=method,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                 'Content-Type': 'application/json', 'User-Agent': 'inventory-cicd-setup'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        # No imprimir headers ni el objeto Request, que contienen la credencial.
        raise RuntimeError(f'GitHub API {method} {path}: HTTP {error.code}') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', default='proyecto-integradora-cicd')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    token = credential()
    user = api(token, '/user')['login']
    if args.check:
        print('Sesión de GitHub disponible:', user)
        return
    repo_path = f'/repos/{user}/{args.name}'
    try:
        repo = api(token, repo_path)
        if repo.get('size', 0) > 0:
            raise RuntimeError('El repositorio ya contiene datos; no se modificará automáticamente')
    except RuntimeError as error:
        if 'HTTP 404' not in str(error):
            raise
        repo = api(token, '/user/repos', 'POST', {'name': args.name, 'private': True,
            'description': 'Caso de estudio de inventario con CI CD, pruebas, Docker y monitoreo',
            'auto_init': False})
    for environment in ('staging', 'production'):
        api(token, repo_path + '/environments/' + environment, 'PUT', {})
    print(json.dumps({'repository': repo['html_url'], 'private': repo['private'],
                      'environments': ['staging', 'production']}, indent=2))


if __name__ == '__main__':
    main()
