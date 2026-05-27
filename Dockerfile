FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=3000 \
    GATEWAY_CONFIG_PATH=/app/config.yaml

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY app.py config.py registry.py warp_agent.py ./
COPY bots/ ./bots/
COPY webhooks/ ./webhooks/
COPY config.example.yaml ./config.example.yaml

RUN chown -R app:app /app
USER app

EXPOSE 3000

CMD ["sh", "-c", "gunicorn --bind :${PORT} --workers ${GUNICORN_WORKERS:-2} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-300} app:flask_app"]
