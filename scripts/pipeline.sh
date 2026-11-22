#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/release.py pipeline --env "${1:-staging}" --image "inventory:${2:-local}" --version "${2:-local}" --monitoring
