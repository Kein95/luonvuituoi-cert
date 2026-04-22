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

# Real WSGI entrypoint committed to the repo; no more printf shim drift.
COPY wsgi.py /app/wsgi.py

# Run as a non-root user. Create /app writable dir for pycache under the user.
RUN groupadd --system app && useradd --system --gid app --home /app --no-create-home app \
    && chown -R app:app /app
USER app

EXPOSE 8000
# M4: /health is a cheap, dependency-free probe — no KV write, no rate-limit
# impact, no attack surface. Replaces the POST /api/captcha probe.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-2} --timeout 60 --access-logfile - wsgi:app"]
