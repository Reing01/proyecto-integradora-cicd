"""Exportación y verificación SHA256 del artefacto Docker, multiplataforma."""
import argparse
import hashlib
from pathlib import Path
import subprocess


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['save', 'load'])
    parser.add_argument('--image')
    args = parser.parse_args()
    folder = Path('artifacts')
    folder.mkdir(exist_ok=True)
    archive = folder / 'inventory.tar'
    checksum = folder / 'inventory.tar.sha256'
    if args.command == 'save':
        if not args.image:
            parser.error('--image requerido para save')
        subprocess.run(['docker', 'save', args.image, '-o', str(archive)], check=True)
        checksum.write_text(digest(archive) + '  inventory.tar\n')
    else:
        if digest(archive) != checksum.read_text().split()[0]:
            raise RuntimeError('El SHA256 no coincide; artefacto rechazado')
        subprocess.run(['docker', 'load', '-i', str(archive)], check=True)


if __name__ == '__main__':
    main()
