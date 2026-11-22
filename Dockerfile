FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    groupadd --gid 10001 app && useradd --uid 10001 --gid app app && \
    mkdir /data && chown app:app /data
COPY app ./app
USER 10001:10001
ENV PYTHONUNBUFFERED=1 DB_PATH=/data/inventory.sqlite
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", "--timeout", "30", "--access-logfile", "-", "app.main:application"]
