# Deploy with Docker

Self-host when you want persistent SQLite instead of the Vercel `/tmp` dance, or when your deployment target doesn't have a serverless Python runtime.

## The bundled image

The repo root ships a `Dockerfile` that installs the core engine + gunicorn and serves the Flask dev server on port 8000. It's fine for small-org production — a single worker handles ~30 req/s on cheap hardware.

```bash
docker build -t my-portal:latest .
```

## Runtime

```bash
docker run --rm -p 8000:8000 \
  -e JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  -e ADMIN_DEFAULT_PASSWORD="change-me" \
  -e PUBLIC_BASE_URL="https://mycerts.example" \
  -v "$(pwd)/data:/app/project/data" \
  -v "$(pwd)/private_key.pem:/app/project/private_key.pem:ro" \
  my-portal:latest
```

The mounted volumes give you:

- `data/` — persistent SQLite + optional local KV store survives container restarts.
- `private_key.pem` — the QR signing key. Never bake this into the image.

## docker-compose

`docker-compose.yml` in the repo root is a reasonable starting point. Drop a `.env` alongside it and run `docker compose up -d`. Mount the project directory (config + templates + fonts) under `/app/project`; the entrypoint reads `cert.config.json` from there.

## Behind a reverse proxy

Gunicorn speaks plain HTTP; put Caddy or Nginx in front to terminate TLS and pass `X-Forwarded-For` so the rate limiter keys off the real client IP.

```nginx
location / {
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_pass http://127.0.0.1:8000;
}
```

## Backups

Stop the container (or use SQLite's `.backup` command against a live DB), tar up `data/`, and ship it somewhere off-host. The DB is the only stateful artifact.

## Scaling

The Flask dev server is single-process; gunicorn spawns multiple workers but they share nothing in memory. That's fine because:

- The rate limiter + CAPTCHA live in the configured KV backend (Upstash REST, Vercel KV REST, or a shared `LocalFileKV` mount). Use Upstash if you want multi-host.
- SQLite writes serialize per database file — adequate for sub-second admin edits.
- The FontRegistry is per-process, so extra workers just re-register fonts on first request.

If you outgrow SQLite (~hundreds of writes/sec), swap the data layer to Postgres — the repository pattern in `luonvuitoi_cert.storage` is a small target for a new backend.
