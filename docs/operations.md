# Operations

How to run a LUONVUITUOI-CERT deployment day-to-day: health probes, log surfaces, KV backend choice, session revocation, and the incident checklist.

## Health probe

```http
GET /health
```

Returns `{"ok": true}` with HTTP 200. The endpoint:

- Does **not** read the database.
- Does **not** write to KV.
- Does **not** hit the rate limiter.
- Has no auth requirement.

Docker `HEALTHCHECK`, Kubernetes liveness, and load-balancer probes should all target this path. Older deploys that probed `POST /api/captcha` as a health signal should switch — every probe minted a KV entry and pushed the rate-limit bucket.

## KV backends

`KV_BACKEND` decides where ephemeral state lives: CAPTCHA challenges, rate-limit counters, OTP codes, magic-link hashes, JWT denylist. Pick one:

| Backend | When to use | Multi-worker safe? |
|---------|-------------|--------------------|
| `local` | Local dev, single-container Docker | **No** — file-lock only scopes inside one process. Startup logs a warning when `WEB_CONCURRENCY > 1`. |
| `upstash` | Anywhere — recommended for production | Yes — Redis atomic `GETDEL` backs `kv.consume()`. |
| `vercel-kv` | Vercel deploys | Yes — auto-injected via the Vercel KV integration. |

If you run gunicorn with multiple workers against `local`, watch the startup log for:

```
KV_BACKEND=local with 2 workers is unsafe — concurrent reads can lose writes.
```

Either drop to 1 worker (`WEB_CONCURRENCY=1`) or switch to `upstash`.

## Logs

Everything flows through the stdlib `logging` module at `WARNING` and above. In Docker, those go to stdout and are captured by `docker logs`. On Vercel, `vercel logs --follow` streams them.

Loud messages worth alerting on:

| Logger | Message | Meaning |
|--------|---------|---------|
| `luonvuitoi_cert_cli.server.app` | `RESEND_API_KEY not set` | OTP/magic-link emails are being silently dropped. |
| `luonvuitoi_cert.storage.kv.factory` | `KV_BACKEND=local with N workers is unsafe` | Concurrent workers racing on a single file KV. |
| `luonvuitoi_cert.auth.activity_log` | `must be https://` | Someone set `GSHEET_WEBHOOK_URL` to a non-HTTPS target; forwarding is disabled. |
| `luonvuitoi_cert.auth.activity_log` | `activity log webhook POST failed` | The GSheet endpoint is down. Local SQLite record is still authoritative. |

Handled errors (rate-limit 429s, CAPTCHA rejections, 404 searches) are **not** logged — they're normal traffic.

## Audit log

Admin actions land in the `admin_activity` SQLite table:

| Column | Notes |
|--------|-------|
| `id` | UUID4 per entry. |
| `timestamp` | ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`). |
| `user_id` / `user_email` | JWT `sub` + `email` claims. |
| `action` | `admin.login.success`, `admin.login.failure`, `student.update`, `shipment.upsert`, etc. |
| `target_id` | Subject of the change (e.g. `students:12345`). |
| `metadata` | JSON blob — _never includes PII_; `student.update` records `{column, changed, value_length_delta}`, not raw old/new values. |
| `ip` | Client IP (honors `TRUST_PROXY_HEADERS`). |

If `GSHEET_WEBHOOK_URL` is set (and `https://`), each entry is POSTed fire-and-forget to the sheet on a bounded `ThreadPoolExecutor(4)`. The SQLite write is authoritative — webhook failures never break admin flows.

### Query recipes

```bash
sqlite3 data/portal.db "SELECT timestamp, user_email, action, target_id FROM admin_activity ORDER BY timestamp DESC LIMIT 20;"

# Failed logins in the last hour:
sqlite3 data/portal.db "SELECT timestamp, user_email, metadata FROM admin_activity WHERE action = 'admin.login.failure' AND timestamp > datetime('now', '-1 hour');"
```

## Session revocation

See [admin-auth.md](admin-auth.md#signing-out-revoking-sessions) for the full flow. Summary:

- `POST /api/admin/logout` with the user's current JWT → `jti` added to the KV denylist with TTL matching the token's remaining life.
- Any endpoint that threads `kv=` into `verify_admin_token` will reject the token.
- Denylist self-expires — no cron needed.

Use this instead of rotating `JWT_SECRET` (which invalidates _every_ session at once and requires all admins to log back in).

## Public-surface feature gates

Two super-admin-only toggles control whether the public surfaces are live. State is stored in KV so flips take effect immediately, no redeploy.

- **Lookup toggle** — gates `POST /api/search` (student mode). When off, the endpoint returns `503` with `{"error": "public lookup is currently disabled by the operator"}`. Admin mode (`mode=admin`, JWT required) is unaffected so operators keep working during a freeze.
- **Download toggle** — gates `POST /api/download` (student mode). When off, the endpoint returns `503` with a download-specific message. Admin mode unaffected.

Invariant: **download requires lookup**. Lookup off ⇒ download forced off. This is enforced both on write (the toggle API clamps the request) and on read (the gate checks both flags).

### How to flip

Sign in as super-admin → the **Public surface** card appears above the student lookup form → tick the boxes → **Save**. The download checkbox auto-disables when lookup is off.

REST equivalent:

```bash
curl -X POST https://your.host/api/admin/features/update \
  -H 'Content-Type: application/json' \
  -d '{"token": "<super-admin JWT>", "lookup_enabled": false, "download_enabled": false}'
```

Only the `super-admin` role is accepted; `admin` / `viewer` get `403`. Every flip is recorded in the audit log as `admin.features.update` with the new state in `metadata`.

### Defaults

Fresh deploys: both on (pre-gate behavior). The KV is only written when a super-admin first saves — a never-touched deploy reads the baked-in default.

## Updating dependencies

Dependabot scans weekly (pip) and monthly (github-actions, docker) and opens PRs. Review and merge them promptly — `reportlab`, `pypdf`, and `cryptography` are supply-chain targets.

## Backing up

```bash
# Stop the container for a consistent snapshot:
docker compose stop
tar czf "backup-$(date +%Y%m%d).tar.gz" data/
docker compose start
```

Or with the container running, use SQLite's online backup:

```bash
sqlite3 data/portal.db ".backup '/tmp/portal.db.bak'"
```

The DB is the only stateful artifact — the KV entries (rate-limit counters, CAPTCHA challenges) are ephemeral.

## Incident checklist

One admin's session looks compromised:

1. `POST /api/admin/logout` with their token (revokes the JTI).
2. `UPDATE admin_users SET is_active = 0 WHERE email = '…';` (belt-and-suspenders).
3. Rotate the admin's password (or reset via OTP).
4. Grep `admin_activity` for `target_id` they touched in the last window.

`JWT_SECRET` leaked:

1. Generate a new secret.
2. Redeploy with the new value (invalidates every session).
3. Rotate the **QR signing key** too if the secret leaked via the same channel — `private_key.pem` is a separate artifact but often co-located.
