#!/usr/bin/env bash
# Ejecutar una vez en el host Linux del runner con Docker y Compose instalados.
set -euo pipefail
command -v docker >/dev/null
command -v python3 >/dev/null
docker info >/dev/null
docker compose version
sudo install -d -m 0700 -o "$(id -un)" -g "$(id -gn)" /opt/inventory-state
export RELEASE_STATE_DIR=/opt/inventory-state
python3 "$(dirname "$0")/release.py" init --env staging
python3 "$(dirname "$0")/release.py" init --env production
printf '%s\n' 'Registrar este host como runner con etiqueta inventory-deploy en GitHub Settings > Actions > Runners.'
