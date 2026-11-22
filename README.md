# Inventario con liberación y despliegue continuo

Caso de estudio académico para **Abarrotes La Esquina**, una pequeña empresa ficticia. Incluye API de inventario, pruebas, contenedores, pipeline de GitHub Actions, entornos aislados, monitoreo, copias de seguridad y recuperación.

El documento principal está en [docs/Informe_CICD.pdf](docs/Informe_CICD.pdf). Explica la justificación del pipeline, entorno requerido, niveles de servicio, métricas y parámetros de cada herramienta. El código fuente que lo genera está en `docs/build_report.py`.

## Ejecución local

Requisitos: Git, Python 3.12 o 3.13, Docker Engine con contenedores Linux y Docker Compose v2 con soporte de `--wait`. El caso usa Python 3.13 dentro de Docker.

```powershell
python scripts/release.py pipeline --env staging --image inventory:1.0.0 --version 1.0.0 --monitoring
```

El comando genera un token aleatorio, corre 13 pruebas, construye la imagen, prueba su persistencia en un entorno temporal y despliega staging. La API queda en `http://127.0.0.1:8081/health` y Prometheus en `http://127.0.0.1:9091`. Producción utiliza los puertos 8080 y 9090.

Para cambiar la ruta del estado persistente, define `RELEASE_STATE_DIR`. Por defecto es `.release/` y se excluye de Git. En un runner debe estar fuera del checkout para sobrevivir a su limpieza. **Nunca publiques `runtime.env`, `previous.env` ni respaldos**, que contienen secretos o datos.

```powershell
python scripts/release.py test
python scripts/release.py init --env staging
python scripts/release.py build --image inventory:1.0.0
python scripts/release.py test-release --image inventory:1.0.0 --version 1.0.0
python scripts/release.py deploy --env staging --image inventory:1.0.0 --version 1.0.0 --monitoring
python scripts/release.py smoke --env staging
python scripts/release.py backup --env staging
python scripts/release.py rollback --env staging
python scripts/release.py restore --env staging --backup RUTA_AL_RESPALDO.sqlite
```

`rollback` requiere una versión anterior desplegada y verificada. Conserva los datos actuales. `restore` reemplaza los datos por el punto del respaldo y genera una copia de seguridad antes de hacerlo.

## Pipeline de GitHub Actions

1. Los pull requests a `main` ejecutan pruebas y validan la imagen en un entorno aislado; no llegan al runner de despliegue.
2. Un push a `main` ejecuta las pruebas, construye y exporta una imagen identificada por SHA, y despliega staging.
3. Una etiqueta `v*` ejecuta las mismas verificaciones y promueve **el mismo artefacto del run** desde staging a producción.
4. Si el despliegue o el smoke falla, se recupera la imagen anterior. Los volúmenes se conservan.
5. `.github/workflows/backup.yml` genera un respaldo diario a las 08:00 UTC, equivalente a las 02:00 de Ciudad de México. También se respalda antes de cada actualización.

```powershell
git add .
git commit -m "Actualizar inventario"
git push origin main
git tag v1.0.0
git push origin v1.0.0
```

El host de despliegue necesita un runner registrado con la etiqueta `inventory-deploy`, Python accesible como `python` y Docker en ejecución. `DEPLOY_RUNNER_LABELS` define las etiquetas en JSON; `RELEASE_STATE_DIR` apunta al estado persistente. Son variables del repositorio, no secretos.

Para un host Windows con sesión de GitHub en Git Credential Manager:

```powershell
python scripts/register_runner.py
```

El script descarga el runner oficial, verifica su SHA256, lo registra en este repositorio privado y lo inicia en segundo plano. No instala inicio automático al arrancar Windows: tras reiniciar, enciende Docker Desktop y vuelve a ejecutar el script. Detalles en [docs/OPERACION.md](docs/OPERACION.md).

## API

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/health` | Estado del proceso y versión |
| GET | `/ready` | Consulta real de SQLite |
| GET | `/metrics` | Métricas Prometheus internas |
| GET | `/api/products` | Lista hasta 1000 productos con token |
| POST | `/api/products` | Registra producto con SKU único y cantidad no negativa |

Para Windows PowerShell, utiliza el token local sin imprimirlo:

```powershell
$configFile = '.release/staging/runtime.env' # o RELEASE_STATE_DIR/staging/runtime.env
$tokenLine = Get-Content $configFile | Where-Object { $_.StartsWith('API_TOKEN=') }
$apiToken = $tokenLine.Substring(10)
$headers = @{Authorization = "Bearer $apiToken"}
$body = @{sku='ARROZ-001'; name='Arroz de un kilogramo'; quantity=25} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8081/api/products -Method Post -Headers $headers -ContentType 'application/json' -Body $body
Invoke-RestMethod http://127.0.0.1:8081/api/products -Headers $headers
```

## Monitoreo

Prometheus recolecta cada 15 segundos. Blackbox Exporter comprueba `/ready`. Las reglas cubren disponibilidad, errores, latencia y fallo de recolección. Las alertas se consultan en `/alerts` de Prometheus; no hay envío de correo configurado. Los logs de Docker rotan a 3 archivos de 10 MB por contenedor de API.

Los entornos llamados `production` y `staging` pertenecen a una demostración local, con una réplica y SQLite. Los objetivos de servicio del documento son metas del caso, no certificaciones de disponibilidad medidas. La API y Prometheus se publican únicamente en loopback; para acceso público se requiere una capa de acceso y HTTPS.

## Entregables

| Requisito | Archivo |
| --- | --- |
| Documento del caso y parámetros | `docs/Informe_CICD.pdf` |
| Pipeline | `.github/workflows/release.yml`, `scripts/pipeline.ps1`, `scripts/pipeline.sh` |
| Generación del entorno | `compose.yml`, `compose.monitoring.yml`, `scripts/provision-host.sh`, `release.py init` |
| Pruebas en liberación | `tests/test_inventory.py`, `release.py test-release` y `release.py smoke` |
| Generación del despliegue | `Dockerfile`, `release.py deploy`, `image_artifact.py` |
| Vinculación de herramienta | `register_runner.py`, variables y entornos de GitHub |
| Respaldo y recuperación | `.github/workflows/backup.yml`, `release.py backup`, `restore`, `rollback` |

No se incluyen credenciales en el repositorio. La aplicación usa solamente biblioteca estándar; Gunicorn, fijado en `requirements.txt`, proporciona el servidor WSGI dentro del contenedor.
