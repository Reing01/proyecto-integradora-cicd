"""Registrar y arrancar un ejecutor local Windows para el repositorio privado."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile
from github_setup import api, credential


def main():
    token = credential()
    owner = api(token, '/user')['login']
    repository = f'{owner}/proyecto-integradora-cicd'
    base = '/repos/' + repository
    if not api(token, base)['private']:
        raise RuntimeError('Este ejecutor persistente está destinado al repositorio privado del caso')
    if os.name != 'nt':
        raise RuntimeError('Para Linux, registra el runner desde Settings > Actions > Runners y ejecuta provision-host.sh')
    home = Path.home()
    directory = home / '.local' / 'share' / 'inventory-cicd-runner'
    state = home / '.local' / 'state' / 'inventory-cicd'
    directory.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)
    for name, value in {'DEPLOY_RUNNER_LABELS': json.dumps(['self-hosted', 'Windows', 'X64', 'inventory-deploy']),
                        'RELEASE_STATE_DIR': state.as_posix()}.items():
        try:
            api(token, base + '/actions/variables/' + name, 'PATCH', {'name': name, 'value': value})
        except RuntimeError as error:
            if 'HTTP 404' not in str(error):
                raise
            api(token, base + '/actions/variables', 'POST', {'name': name, 'value': value})
    env = {**os.environ, 'PATH': str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH']}
    if not (directory / '.runner').exists():
        packages = api(token, base + '/actions/runners/downloads')
        package = next((item for item in packages if item['os'] in ('win', 'win32') and item['architecture'] == 'x64'), None)
        if package is None:
            release = api(token, '/repos/actions/runner/releases/latest')
            asset = next(item for item in release['assets'] if 'win-x64' in item['name'] and item['name'].endswith('.zip'))
            package = {'filename': asset['name'], 'download_url': asset['browser_download_url'],
                       'sha256_checksum': asset['digest'].removeprefix('sha256:')}
        archive = directory / package['filename']
        print('Descargando runner oficial de GitHub', flush=True)
        urllib.request.urlretrieve(package['download_url'], archive)
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        if checksum != package['sha256_checksum']:
            raise RuntimeError('SHA256 del runner incorrecto')
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(directory)
        registration = api(token, base + '/actions/runners/registration-token', 'POST', {})['token']
        subprocess.run([str(directory / 'config.cmd'), '--unattended', '--url', 'https://github.com/' + repository,
                        '--token', registration, '--name', 'inventory-codex-host', '--labels', 'inventory-deploy',
                        '--work', 'work'], cwd=directory, env=env, check=True)
    runners = api(token, base + '/actions/runners')['runners']
    configured = next((item for item in runners if item['name'] == 'inventory-codex-host'), None)
    if configured and configured['status'] == 'online':
        print('Runner ya conectado')
        return
    with (directory / 'listener.log').open('ab') as log:
        process = subprocess.Popen([str(directory / 'bin' / 'Runner.Listener.exe'), 'run'],
            cwd=directory, env=env, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
    print(json.dumps({'repository': repository, 'runner_pid': process.pid,
                      'runner_directory': str(directory), 'release_state': str(state)}, indent=2))


if __name__ == '__main__':
    main()
