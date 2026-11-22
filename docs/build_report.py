"""Genera el documento de entrega en PDF con ReportLab.

Requiere reportlab. Ejecutar desde cualquier carpeta: python docs/build_report.py
"""
import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

HERE = Path(__file__).resolve().parent
WIDTH = A4[0] - 100
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='DocTitle', fontName='Helvetica-Bold', fontSize=24, leading=28, spaceAfter=16, textColor=colors.black))
styles.add(ParagraphStyle(name='SectionTitle', fontName='Helvetica-Bold', fontSize=17, leading=21, spaceAfter=14, textColor=colors.black))
styles.add(ParagraphStyle(name='SubTitle', fontName='Helvetica-Bold', fontSize=11.5, leading=15, spaceBefore=12, spaceAfter=7, textColor=colors.black))
styles.add(ParagraphStyle(name='BodyCopy', fontName='Helvetica', fontSize=10.2, leading=15, spaceAfter=9))
styles.add(ParagraphStyle(name='SmallCopy', fontName='Helvetica', fontSize=8.5, leading=12, spaceAfter=6))
styles.add(ParagraphStyle(name='CellCopy', fontName='Helvetica', fontSize=9, leading=12))
styles.add(ParagraphStyle(name='CellHead', fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=colors.white))
styles.add(ParagraphStyle(name='CodeCopy', fontName='Courier', fontSize=8, leading=12, spaceAfter=9, wordWrap='CJK'))
story = []


def para(text, style='BodyCopy'):
    story.append(Paragraph(text, styles[style]))


def title(text):
    para(text, 'SectionTitle')


def sub(text):
    para(text, 'SubTitle')


def code(text):
    para(escape(text).replace('\n', '<br/>'), 'CodeCopy')


def table(headers, rows, widths):
    content = [[Paragraph(escape(str(cell)), styles['CellHead']) for cell in headers]]
    content += [[Paragraph(escape(str(cell)), styles['CellCopy']) for cell in row] for row in rows]
    item = Table(content, colWidths=[WIDTH * w for w in widths], repeatRows=1, hAlign='LEFT')
    item.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#253C51')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F1F4F6')]),
        ('GRID', (0, 0), (-1, -1), .45, colors.HexColor('#D9D9D9')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9),
    ]))
    story.extend([item, Spacer(1, 12)])


def page():
    story.append(PageBreak())


def footer(canvas, doc):
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.HexColor('#555555'))
    canvas.drawString(50, 32, 'Proyecto Integradora | Caso de inventario | 22 de noviembre de 2026')
    canvas.drawRightString(A4[0] - 50, 32, str(doc.page))


def main():
    evidence_file = HERE / 'evidence.json'
    evidence = json.loads(evidence_file.read_text(encoding='utf-8')) if evidence_file.exists() else {}
    para('Liberación y despliegue continuo del sistema de inventario', 'DocTitle')
    para('Caso de estudio de Abarrotes La Esquina', 'SubTitle')
    para('Documento técnico y evidencia de implementación<br/>Responsable del repositorio Reing01<br/>22 de noviembre de 2026', 'SmallCopy')
    sub('Propósito y resultado')
    para('La solución automatiza la validación, liberación y actualización de una API de inventario. Cada entrega se prueba dentro de un contenedor antes de llegar a staging; las versiones etiquetadas se promueven a producción. El despliegue verifica salud, acceso, versión y métricas, conserva el volumen de datos y recupera la versión anterior ante un fallo de verificación.')
    sub('Situación del negocio')
    para('Abarrotes La Esquina es una empresa ficticia con un almacén y hasta veinte usuarios internos. Necesita registrar productos, consultar existencias y evitar cantidades negativas o SKU duplicados. El problema inicial es la actualización manual: depende del equipo del desarrollador, carece de pruebas repetibles y dificulta saber qué versión está instalada.')
    para('El caso supone diez solicitudes por segundo como carga de diseño. La implementación cubre altas y consultas de productos, autenticación por token, almacenamiento SQLite y observabilidad. La aplicación se ejecuta en una red local de demostración; no incluye ventas, facturación, interfaz gráfica ni alta disponibilidad.')
    table(['Requisito académico', 'Evidencia entregada'], [
        ['Justificación y entorno', 'Diseño del pipeline y separación de ambientes'],
        ['Servicio y monitoreo', 'Acuerdo del caso, indicadores y reglas de alerta'],
        ['Parámetros y vinculación', 'Configuración versionada, entornos y runner de GitHub'],
        ['Repositorio configurado', 'Workflows, entorno, pruebas y scripts de despliegue'],
    ], [.37, .63])
    para('Repositorio privado <link href="https://github.com/Reing01/proyecto-integradora-cicd" color="#17466B">github.com/Reing01/proyecto-integradora-cicd</link>', 'SmallCopy')

    page()
    title('Justificación del flujo de trabajo')
    para('El pipeline separa la integración continua de la liberación y del despliegue. La integración detecta defectos en cada cambio. La liberación genera un artefacto identificado por el SHA del commit y verifica que realmente funcione. El despliegue instala ese mismo artefacto y comprueba el servicio resultante.')
    table(['Etapa', 'Acción y criterio de salida'], [
        ['1 Cambio', 'Pull request, push a main o etiqueta v*. Los pull requests nunca ejecutan jobs en el host de despliegue.'],
        ['2 Validación', '13 pruebas de autenticación, entradas, SKU, persistencia, concurrencia, SQL parametrizado, salud y métricas. Cualquier fallo detiene la liberación.'],
        ['3 Construcción', 'Docker construye inventory:SHA a partir de Dockerfile. Gunicorn queda fijado en requirements.txt.'],
        ['4 Entorno de liberación', 'Contenedor y volumen temporales. Se prueban alta, consulta, duplicado, cantidad inválida, acceso y persistencia tras reinicio.'],
        ['5 Artefacto', 'Exportar imagen tar y SHA256. GitHub conserva el artefacto durante 14 días. El receptor verifica la suma antes de cargarlo.'],
        ['6 Staging', 'Runner vinculado a Docker. Backup previo, arranque con espera de salud y smoke. Un push a main termina aquí.'],
        ['7 Producción', 'Una etiqueta v* promueve la imagen ya verificada en staging dentro del mismo run, sin reconstruir la aplicación.'],
        ['8 Verificación', 'Manifestar éxito tras el smoke. Ante fallo, recuperar configuración e imagen anterior y repetir la comprobación.'],
    ], [.22, .78])
    sub('Razones de las decisiones')
    para('Docker reduce diferencias entre validación y ejecución. El SHA permite rastrear el código de cada entrega. Separar volúmenes evita que una prueba modifique el inventario operativo. La promoción por etiquetas identifica la intención de liberar; después de ese disparador no exige aprobación manual. La concurrencia serializa liberaciones y respaldos para que dos ejecuciones no modifiquen el mismo ambiente a la vez.')
    para('Una sola instancia y SQLite mantienen el caso reproducible. La sustitución del contenedor puede causar una interrupción breve; por eso el diseño no promete despliegue sin caída. Un cambio incompatible del esquema requerirá una estrategia de migración adicional.', 'SmallCopy')

    page()
    title('Entorno requerido y arquitectura')
    para('GitHub Actions ejecuta las verificaciones en ubuntu-latest con Python 3.13. El despliegue usa un runner propio, conectado a GitHub y al motor local de Docker. En esta entrega el host es Windows con Docker Desktop y contenedores Linux; la API escucha únicamente en loopback.')
    table(['Componente', 'Requisito y configuración'], [
        ['Host de demostración', 'Windows con Docker Desktop en modo Linux. Base de capacidad propuesta: 4 CPU, 8 GB RAM y 20 GB libres. El host debe permanecer encendido.'],
        ['Herramientas', 'Git, Python 3.12 o 3.13 y Docker Compose v2 con --wait. Python 3.13 dentro del contenedor; Gunicorn 27.0.1.'],
        ['Staging', 'Proyecto inventory-staging. API 127.0.0.1:8081 y Prometheus 127.0.0.1:9091. Volumen de inventario independiente.'],
        ['Producción', 'Proyecto inventory-production. API 127.0.0.1:8080 y Prometheus 127.0.0.1:9090. Volumen de inventario independiente.'],
        ['Liberación temporal', 'Proyecto inventory-test. Puerto API 18080. El volumen de pruebas se elimina al terminar; no se usan datos de negocio.'],
        ['Persistencia', 'SQLite en /data/inventory.sqlite sobre volumen Docker. Estado y backups fuera del checkout en .local/state/inventory-cicd del usuario.'],
        ['Acceso y red', 'Token Bearer aleatorio de 64 caracteres hexadecimales para /api/products. Métricas y administración solo en red interna o loopback.'],
        ['Conectividad', 'HTTPS saliente a GitHub, PyPI y registros de imágenes. El runner recibe jobs sin publicar puertos de administración.'],
    ], [.26, .74])
    sub('Distribución de recursos')
    para('La API dispone de un límite de 1 CPU y 256 MB RAM; Gunicorn usa un worker y ocho hilos. SQLite usa WAL, consultas parametrizadas y espera de bloqueo de cinco segundos. Prometheus dispone de 512 MB y Blackbox Exporter de 64 MB. Los volúmenes de Prometheus conservan 35 días de datos.')
    sub('Configuración reproducible')
    code('python scripts/release.py init --env staging\npython scripts/release.py init --env production')
    para('Los comandos generan tokens y archivos runtime.env fuera del control de versiones y validan Compose. En Linux, scripts/provision-host.sh comprueba los prerrequisitos y crea /opt/inventory-state. Las imágenes de monitoreo incorporan su configuración al construirse, sin depender de montajes de archivos del host.', 'SmallCopy')

    page()
    title('Niveles de servicio acordados')
    para('El siguiente acuerdo pertenece al caso académico entre el encargado de Abarrotes La Esquina y el responsable de operación. Los valores definen objetivos y criterios de aceptación; no constituyen una certificación histórica ni una garantía comercial de la demostración local.')
    table(['Indicador', 'Objetivo del caso', 'Medición y respuesta'], [
        ['Disponibilidad', 'Al menos 99.5% mensual, 24 por 7', 'Prueba de /ready cada 15 s. En 30 días admite hasta 216 minutos de indisponibilidad. Las ventanas de mantenimiento también cuentan.'],
        ['Latencia de API', 'p95 menor o igual a 500 ms', 'Ventana de 5 min, con tráfico real y dentro de la carga de diseño de 10 solicitudes/s. Probes y scrapes se excluyen del histograma.'],
        ['Errores del servidor', 'Menos de 1% de solicitudes', 'Respuestas 5xx / solicitudes, ventana de 5 min. Los 4xx se revisan como errores de uso, no del servidor.'],
        ['RPO', 'Hasta 24 horas de datos', 'Respaldo diario y antes de cada despliegue. Para pérdida del host se necesita copia externa cifrada.'],
        ['RTO', 'Hasta 30 minutos', 'Desde declaración de incidente hasta restauración y smoke correcto. Requiere host y respaldo disponibles.'],
        ['Incidente P1', 'Acuse en 15 min', 'Caída total, corrupción o imposibilidad de leer inventario. Responsable de operación ejecuta diagnóstico y recuperación.'],
        ['Incidente P2', 'Acuse en 4 horas hábiles', 'Latencia elevada o fallos intermitentes sin caída total. Investigar versión, logs, CPU, memoria y disco.'],
    ], [.23, .29, .48])
    sub('Responsables y revisión')
    para('El encargado valida el impacto sobre el inventario y acepta una restauración de datos. Desarrollo mantiene pruebas y compatibilidad del esquema. Operación supervisa runs, respaldos, recursos y recuperación. Mensualmente se revisan disponibilidad, errores, tiempos de recuperación y causas recurrentes; se registra cada incumplimiento y su acción correctiva.')
    sub('Condiciones para evaluar el acuerdo')
    para('La disponibilidad solo puede evaluarse con cobertura suficiente de monitoreo. Los periodos sin Prometheus no prueban que el servicio estuvo disponible. Se requiere una sonda externa para medir pérdida completa del host; la entrega incluye una sonda interna. El respaldo diario queda programado en GitHub, pero su copia externa y retención deben ser operadas por el responsable.')

    page()
    title('Métricas y monitoreo de la aplicación')
    para('La API publica /metrics en formato Prometheus. El recolector consulta cada 15 segundos y evalúa reglas con la misma frecuencia. Blackbox Exporter comprueba /ready, que realiza una consulta real a SQLite; así se distingue un proceso vivo de un servicio con almacenamiento disponible.')
    table(['Métrica', 'Uso y umbral'], [
        ['probe_success', '1 si /ready responde HTTP 200. Alerta crítica cuando permanece en 0 durante 1 minuto; también se observa el fallo de scrape de la sonda.'],
        ['up', 'Disponibilidad de recolección por job. Alerta de advertencia si el scrape de la API falla durante 1 minuto. No equivale por sí solo a disponibilidad del negocio.'],
        ['http_requests_total', 'Contador por método, ruta normalizada y estado. rate(...[5m]) permite calcular solicitudes/s y proporción 5xx. Alerta crítica sobre 1% durante 5 min.'],
        ['http_request_duration_seconds', 'Histograma con buckets 0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5 y +Inf segundos. Alerta p95 mayor a 0.5 s durante 5 min.'],
        ['app_uptime_seconds', 'Tiempo desde que se inicializó la aplicación. Una caída del valor ayuda a identificar reinicios.'],
        ['Recursos y logs', 'docker stats --no-stream, docker system df y logs de Compose. Revisar CPU, memoria, espacio y crecimiento de respaldos. No hay exporter de host instalado.'],
    ], [.37, .63])
    sub('Consultas operativas')
    code('100 * avg_over_time(probe_success{job="readiness"}[30d])\nsum(rate(http_requests_total{route="/api/products"}[5m]))\nhistogram_quantile(0.95, sum by (le) (\n  rate(http_request_duration_seconds_bucket[5m])))')
    para('Para porcentaje de errores se divide la suma de rate de respuestas 5xx entre la suma de rate de solicitudes y se multiplica por 100. Las reglas completas están en monitoring/alerts.yml. Cuando no hay tráfico, un p95 NaN o una serie vacía no demuestra cumplimiento ni fallo.')
    sub('Consulta y atención')
    para('Prometheus permite explorar consultas y ver alertas en /alerts. La entrega no incluye Alertmanager ni notificaciones por correo. El operador revisa el panel y los runs de respaldo. La cardinalidad se limita usando rutas conocidas y una categoría other, sin SKU ni datos de usuario como etiquetas.', 'SmallCopy')

    page()
    title('Parámetros de las herramientas utilizadas')
    table(['Herramienta', 'Parámetros efectivos', 'Archivo o ubicación'], [
        ['GitHub Actions', 'Disparadores main, PR a main, v* y manual. contents: read. Jobs verify, staging y production. Timeouts 15/10/10 min. Concurrencia sin cancelación.', '.github/workflows/release.yml'],
        ['Runner', 'inventory-codex-host; self-hosted, Windows, X64, inventory-deploy. SHA256 del paquete oficial validado. Acceso al Docker del usuario.', 'scripts/register_runner.py; variable DEPLOY_RUNNER_LABELS'],
        ['Artefactos', 'inventory:SHA; tar y SHA256; 14 días de retención. La aplicación no se reconstruye al promoverla.', 'scripts/image_artifact.py'],
        ['Aplicación', 'API_TOKEN aleatorio; APP_VERSION igual al SHA; DB_PATH=/data/inventory.sqlite; cuerpo máximo 16 KB; consulta hasta 1000 registros.', 'app/main.py; runtime.env fuera de Git'],
        ['Gunicorn', 'Bind 0.0.0.0:8000; workers=1; threads=8; timeout=30 s; access-logfile=-. Versión 27.0.1.', 'Dockerfile y requirements.txt'],
        ['Docker Compose', 'restart unless-stopped; read_only; tmpfs /tmp; cap_drop ALL; no-new-privileges; 256 MB; 1 CPU.', 'compose.yml'],
        ['Healthcheck', '/ready cada 10 s; timeout 5 s; 6 reintentos; start_period 10 s. Compose espera hasta 120 s.', 'compose.yml; scripts/release.py'],
        ['Prometheus', 'Base v3.5.0; scrape y evaluación 15 s; retención 35 días; 512 MB. Configuración incorporada en imagen.', 'monitoring/prometheus.yml; compose.monitoring.yml'],
        ['Blackbox Exporter', 'Base v0.27.0; módulo http_ready; timeout 5 s; estado HTTP válido 200; 64 MB.', 'monitoring/blackbox.yml'],
        ['Respaldos y logs', 'Backup diario 08:00 UTC y previo a actualización. Logs API: 3 archivos de 10 MB. Backups SQLite consistentes mediante API online.', 'backup.yml; release.py backup; compose.yml'],
    ], [.20, .51, .29])
    para('RELEASE_STATE_DIR apunta a la carpeta de estado externa al checkout. En esta entrega usa .local/state/inventory-cicd dentro del perfil del usuario. runtime.env y previous.env contienen tokens y se excluyen de Git. Los archivos de estado tienen modo 0600 en Linux; Windows utiliza los permisos del perfil del usuario.', 'SmallCopy')

    page()
    title('Liberación despliegue y recuperación')
    sub('Ejecución reproducible')
    code('python scripts/release.py pipeline --env staging \\\n+  --image inventory:1.0.0 --version 1.0.0 --monitoring')
    para('El comando ejecuta las pruebas, construye la imagen, valida un entorno temporal y despliega staging. Se puede invocar también con scripts/pipeline.ps1 o scripts/pipeline.sh. Para un equipo nuevo se instala Docker y Python; init genera la configuración y provision-host.sh prepara el directorio persistente en Linux.')
    sub('Liberación mediante GitHub')
    code('git push origin main\ngit tag v1.0.0\ngit push origin v1.0.0')
    para('El runner está asociado al repositorio privado y usa variables del repositorio para elegir sus etiquetas y ubicar el estado. Los entornos staging y production quedan registrados en GitHub. Cada job de despliegue descarga el artefacto de su propio run y valida SHA256 antes de cargarlo. El host debe mantener Docker y el runner activos; después de reiniciar Windows se vuelve a ejecutar register_runner.py.')
    sub('Recuperación de aplicación y datos')
    code('python scripts/release.py backup --env production\npython scripts/release.py rollback --env production\npython scripts/release.py restore --env production \\\n+  --backup RUTA_AL_RESPALDO.sqlite')
    para('El rollback recupera la imagen anterior y conserva los datos actuales. Restore verifica la integridad del respaldo, genera una copia del estado actual, detiene la API, restaura SQLite y comprueba la disponibilidad. Esta operación reemplaza los datos por los del respaldo seleccionado. Los respaldos locales protegen frente a errores operativos; la pérdida del equipo exige una copia externa.')
    sub('Pruebas y evidencia técnica')
    para('La suite incluye 13 pruebas de integración de aplicación. test-release prueba el contenedor real y persistencia tras reinicio. verify_recovery.py ejecuta un simulacro aislado de respaldo íntegro, restauración y rollback automático ante un fallo de smoke inyectado; verifica que el producto original conserve su cantidad. load_test.py mide lecturas autenticadas sin escribir datos.')
    load = evidence.get('load_test')
    if load:
        para(f'Medición breve en staging: {load["requests"]} solicitudes con concurrencia {load["concurrency"]}, '
             f'{load["successful"]} correctas, {load["server_errors"]} errores del servidor, p95 {load["p95_ms"]} ms. '
             'Es una observación del entorno local, no una certificación de capacidad sostenida.', 'SmallCopy')

    page()
    title('Evidencia de entrega y referencias')
    table(['Elemento verificable', 'Ubicación o resultado'], [
        ['Repositorio', 'https://github.com/Reing01/proyecto-integradora-cicd; privado; rama main'],
        ['Documento', 'docs/Informe_CICD.pdf y fuente reproducible docs/build_report.py'],
        ['Pipeline', '.github/workflows/release.yml; scripts/pipeline.ps1 y pipeline.sh'],
        ['Generación del entorno', 'compose.yml; compose.monitoring.yml; monitoring/Dockerfile.*; provision-host.sh; release.py init'],
        ['Pruebas de liberación', 'tests/test_inventory.py; release.py test-release y smoke; verify_recovery.py'],
        ['Generación del despliegue', 'Dockerfile; release.py deploy; image_artifact.py; register_runner.py'],
        ['Evidencia de ejecución', 'docs/evidence.json; manifiestos por entorno y registros de GitHub Actions'],
    ], [.32, .68])
    if evidence.get('workflow_url'):
        para('Ejecución verificada <link href="' + evidence['workflow_url'] + '" color="#17466B">' + evidence['workflow_url'] + '</link>', 'SmallCopy')
        para('Resultado registrado ' + escape(evidence.get('workflow_result', '')) + '. La evidencia corresponde a la fecha de entrega; los runs posteriores quedan disponibles en el repositorio.', 'SmallCopy')
    sub('Criterios de aceptación')
    para('El pipeline debe terminar sin fallos; staging y producción deben responder /ready y exponer la versión liberada; los scrapes y la sonda deben ser correctos. La suite, el ensayo de persistencia y el simulacro de recuperación deben pasar. No se consideran demostrados 30 días de disponibilidad, la copia externa ni la atención humana permanente: son condiciones operativas del acuerdo del caso.')
    sub('Referencias técnicas oficiales')
    refs = [
        ('GitHub Actions y runners propios', 'https://docs.github.com/en/actions/concepts/runners/self-hosted-runners'),
        ('GitHub y entornos de despliegue', 'https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments'),
        ('Docker Compose y espera de salud', 'https://docs.docker.com/reference/cli/docker/compose/up/'),
        ('Prometheus e histogramas', 'https://prometheus.io/docs/practices/histograms/'),
        ('SQLite y respaldos online', 'https://www.sqlite.org/backup.html'),
        ('Gunicorn y configuración', 'https://docs.gunicorn.org/en/stable/settings.html'),
    ]
    for name, url in refs:
        para('<link href="' + url + '" color="#17466B">' + escape(name) + '</link>', 'SmallCopy')
    para('Consulta de documentación y parámetros realizada el 22 de noviembre de 2026.', 'SmallCopy')
    output = HERE / 'Informe_CICD.pdf'
    SimpleDocTemplate(str(output), pagesize=A4, leftMargin=50, rightMargin=50, topMargin=46,
        bottomMargin=52, title='Liberación y despliegue continuo del sistema de inventario',
        author='Reing01', subject='Proyecto Integradora de CI CD').build(story, onFirstPage=footer, onLaterPages=footer)
    print(output)


if __name__ == '__main__':
    main()
