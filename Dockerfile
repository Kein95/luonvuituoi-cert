FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PROJECT_ROOT=/app/project \
    WEB_CONCURRENCY=2

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libjpeg-dev zlib1g-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install engine + CLI + gunicorn. CLI package pulls in luonvuitoi-cert as a
# transitive dep, so one install covers both.
COPY packages/core /app/_build/core
COPY packages/cli /app/_build/cli
RUN pip install /app/_build/core /app/_build/cli gunicorn && rm -rf /app/_build

# Placeholder so cold-starts don't crash before a volume is mounted.
RUN mkdir -p /app/project/data

# Minimal WSGI shim — gunicorn targets 'wsgi:app', build_app reads the bind-
# mounted project directory at import time.
RUN printf '%s\n' \
    'from pathlib import Path' \
    'import os' \
    'from luonvuitoi_cert_cli.server import build_app' \
    '' \
    'ROOT = Path(os.environ.get("PROJECT_ROOT", "/app/project")).resolve()' \
    'app = build_app(ROOT / "cert.config.json", ROOT)' \
    > /app/wsgi.py

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fsS -X POST http://127.0.0.1:8000/api/captcha -H 'Content-Type: application/json' -d '{}' || exit 1

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-2} --timeout 60 --access-logfile - wsgi:app"]
