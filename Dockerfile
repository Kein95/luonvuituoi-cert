FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/core/luonvuitoi_cert packages/core/luonvuitoi_cert
RUN pip install ./packages/core gunicorn

COPY examples/demo-academy /app/project

WORKDIR /app/project
EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "luonvuitoi_cert.server:wsgi_app"]
