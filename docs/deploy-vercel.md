# Deploy to Vercel

Vercel's Python serverless runtime is the recommended production target for small-to-medium portals — free tier handles thousands of monthly students.

## Prerequisites

- A Vercel account.
- The Vercel CLI: `npm i -g vercel`.
- An Upstash Redis or Vercel KV instance (the SQLite file in `/tmp` is ephemeral on Vercel).

## Project layout

`lvt-cert init` produces a Vercel-compatible tree:

```text
my-portal/
├── cert.config.json
├── api/                  # serverless entrypoints (Phase 15 generates these)
├── templates/
├── assets/fonts/
├── data/                 # bundled with the deployment
├── public_key.pem
├── requirements.txt
├── vercel.json
└── .gitignore
```

> Phase 15 wires the `api/*.py` handlers that Vercel invokes. For now, mirror
> the Flask route table in `packages/cli/luonvuitoi_cert_cli/server/app.py` —
> each handler is a one-line wrapper around a pure function from
> `luonvuitoi_cert.api`.

## Environment variables

Set these in the Vercel dashboard or via `vercel env add`:

| Name | Required | Notes |
|------|----------|-------|
| `JWT_SECRET` | yes | 32+ random chars. |
| `ADMIN_DEFAULT_PASSWORD` | bootstrap | Used by seed scripts; rotate immediately. |
| `PUBLIC_BASE_URL` | yes | e.g. `https://mycerts.example`. Pins magic-link + QR URLs against Host-header injection. |
| `KV_BACKEND` | yes | `upstash` or `vercel-kv`. |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | if `KV_BACKEND=upstash` | |
| `KV_REST_API_URL` / `KV_REST_API_TOKEN` | if `KV_BACKEND=vercel-kv` | Auto-injected when you link a Vercel KV store. |
| `RESEND_API_KEY` / `CERT_EMAIL_FROM` | if `admin.auth_mode` is `otp_email` or `magic_link` | |
| `GSHEET_WEBHOOK_URL` | optional | Fire-and-forget audit trail. |
| `ALLOWED_ORIGINS` | optional | Comma-separated CORS whitelist. Defaults to `*`. |

## `vercel.json`

The scaffolded file routes root / admin / verify to the serverless handlers and sets a 30-second timeout per invocation:

```json
{
  "rewrites": [
    { "source": "/", "destination": "/api/index" },
    { "source": "/admin", "destination": "/api/admin" },
    { "source": "/certificate-checker", "destination": "/api/certificate-checker" }
  ],
  "functions": {
    "api/*.py": { "maxDuration": 30 }
  }
}
```

## The `/tmp` SQLite pattern

Vercel runtime provides a writable `/tmp` per warm container. On cold start, copy your bundled DB there:

```python
_SRC = Path(__file__).parent.parent / "data" / "my-portal.db"
_TMP = Path("/tmp/my-portal.db")

def get_db_path() -> Path:
    if not _TMP.exists():
        shutil.copy2(_SRC, _TMP)
    return _TMP
```

Admin mutations write to `/tmp` and mirror through Upstash/Vercel KV (see `luonvuitoi_cert.storage.kv`) so the next cold start replays the deltas.

## Deploy

```bash
vercel --prod
```

First run prompts you to link a project and set env vars. Subsequent deploys are one command.

## Verifying

```bash
curl https://mycerts.example/api/captcha -X POST
# → {"id":"…","question":"3 + 5 = ?"}
```

Open `https://mycerts.example/admin` and create the first admin with a one-off script (see [Admin auth](admin-auth.md)).

## CSP note

`/admin` must emit `Content-Security-Policy: script-src 'self' 'nonce-…'; default-src 'self'; frame-ancestors 'none'`. The Flask dev server does this automatically; the Vercel handler wrapper must replicate it so the sessionStorage JWT stays safe against reflected XSS.

## Logs

`vercel logs` streams recent invocations. Admin failures and webhook retries land there via the stdlib `logging` module.
