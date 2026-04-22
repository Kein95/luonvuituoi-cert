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
  -e ALLOWED_ORIGINS="https://mycerts.example" \
  -e TRUST_PROXY_HEADERS=1 \
  -e FORCE_HSTS=1 \
  -v "$(pwd)/data:/app/project/data" \
  -v "$(pwd)/private_key.pem:/app/project/private_key.pem:ro" \
  my-portal:latest
```

### Env checklist

| Name | Why |
|------|-----|
| `JWT_SECRET` | Required. No ephemeral fallback. |
| `PUBLIC_BASE_URL` | Pins magic-link + QR URLs. |
| `ALLOWED_ORIGINS` | CORS whitelist; scope down from `*` once the front-end origin is known. |
| `TRUST_PROXY_HEADERS=1` | Enable only when the Nginx/Caddy reverse proxy below is in place. Without a proxy rewriting `X-Forwarded-For`, leave at `0` — otherwise clients can spoof their IP and bypass rate limits. |
| `FORCE_HSTS=1` | Enable once the reverse proxy terminates TLS. |
| `WEB_CONCURRENCY` | Defaults to `2`. With `KV_BACKEND=local` + >1 worker, startup logs a warning — the local file KV is not cross-process safe. Switch to `upstash` when scaling. |
| `GSHEET_WEBHOOK_URL` | Optional. Must be `https://…`. |

### Mounted volumes

- `data/` — persistent SQLite + optional local KV store survives container restarts.
- `private_key.pem` — the QR signing key. Never bake this into the image.

### Container user

The image runs as non-root `app:app` (system UID/GID). If you bind-mount
`data/` from the host, ensure the directory is writable by that UID
(`chown $(id -u):$(id -g) data/` on the host works because the Docker
daemon maps host UIDs 1:1 by default).

## Healthcheck

`/health` returns `{"ok": true}` with no KV write, no DB read, no rate-limit
interaction. Dockerfile + compose healthcheck probes it every 30s.

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
