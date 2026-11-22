# Operación y recuperación

## Estado persistente

En el host configurado para esta entrega, el estado está en `%USERPROFILE%/.local/state/inventory-cicd`, y el runner en `%USERPROFILE%/.local/share/inventory-cicd-runner`. Dentro del estado hay carpetas `staging` y `production` con configuración, manifiesto y respaldos. No agregues ese contenido a Git.

Los nombres de proyecto de Compose son `inventory-staging`, `inventory-production` e `inventory-test`. Los dos primeros tienen volúmenes diferentes; únicamente el volumen de pruebas se elimina automáticamente al terminar. `docker compose down --volumes` no forma parte de los despliegues.

## Reinicio del equipo

1. Iniciar Docker Desktop y verificar `docker info`.
2. Desde el repositorio ejecutar `python scripts/register_runner.py`.
3. Comprobar el estado online de `inventory-codex-host` en Settings > Actions > Runners.
4. Verificar `http://127.0.0.1:8080/ready` y `http://127.0.0.1:8081/ready`.

Los contenedores usan `restart: unless-stopped`; el runner es un proceso de usuario iniciado en segundo plano y debe reiniciarse después de reiniciar Windows. No cerrar Docker durante una liberación. El equipo necesita permanecer encendido y conectado para recibir jobs.

## Actualización y reversión

El pipeline guarda una copia consistente de SQLite antes de modificar una instancia activa. Carga una imagen ya verificada, ejecuta Compose con espera de salud y comprueba lectura, autorización, versión y métricas. Si falla, vuelve a la imagen anterior y repite el smoke. Una primera instalación fallida se detiene sin anunciar éxito.

La reversión de la imagen conserva la base actual. Esta versión usa una migración aditiva `CREATE TABLE IF NOT EXISTS`. Una futura migración destructiva necesita un plan independiente de compatibilidad y restauración. No mezclar un cambio incompatible del esquema con una reversión automática de aplicación.

```powershell
$env:RELEASE_STATE_DIR = "$env:USERPROFILE/.local/state/inventory-cicd"
python scripts/release.py rollback --env production
python scripts/release.py smoke --env production
```

Para corrupción o pérdida de datos, seleccionar un archivo dentro de `production/backups`, comprobar su fecha y ejecutar `restore`. Este paso produce interrupción y reemplaza los datos por los del respaldo; el script conserva una copia previa. Verificar la integridad y el contenido del inventario antes de reabrir el servicio.

```powershell
python scripts/release.py restore --env production --backup 'C:/ruta/20261122T000000000000Z.sqlite'
```

## Respaldo y niveles de servicio

El workflow de respaldo corre cada día a las 08:00 UTC. Sus archivos permanecen en el disco del host; para cubrir pérdida del equipo, el responsable debe copiarlos a almacenamiento externo cifrado. La entrega no configura un proveedor externo. La retención es manual: conservar al menos siete respaldos diarios y cuatro semanales, y revisar el espacio disponible.

RPO de 24 horas depende de la ejecución del respaldo diario y su copia externa. RTO de 30 minutos es un objetivo operativo que exige un simulacro de restauración y disponibilidad del host; no es una garantía de este equipo. Ante respaldo fallido, revisar el workflow y ejecutar la copia manualmente.

## Consultas de Prometheus

```promql
100 * avg_over_time(probe_success{job="readiness"}[30d])
sum(rate(http_requests_total{route="/api/products"}[5m]))
100 * sum(rate(http_requests_total{status=~"5.."}[5m])) / clamp_min(sum(rate(http_requests_total[5m])), 0.001)
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))
up{job="inventory"}
```

La primera consulta mide disponibilidad observada, siempre que exista cobertura de recolección. Un hueco de Prometheus no significa disponibilidad del servicio. Revisar también `up{job="readiness"}` y registrar incidentes fuera del host cuando se evalúe un SLA real. Sin tráfico, una tasa de errores vacía o p95 NaN no demuestra incumplimiento ni cumplimiento.

## Incidentes

P1 corresponde a caída de API, corrupción o lectura imposible. El responsable de operaciones acusa recibo en 15 minutos, evalúa `ready`, logs y almacenamiento, y decide rollback o restauración. P2 corresponde a errores intermitentes o p95 alto: respuesta en 4 horas hábiles. Documentar fecha, duración, versión, impacto, causa y acción correctiva. Los tiempos y responsables representan el acuerdo del caso académico.

## Recursos y límites

Revisar `docker stats --no-stream`, `docker system df` y el espacio del volumen del host. La API limita memoria a 256 MB y CPU a 1. Prometheus utiliza hasta 512 MB y conserva 35 días. Los back-ups y artefactos consumen espacio adicional. Los endpoints de métricas y las interfaces de administración son internos.
