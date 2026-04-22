# Security (user guide)

This page is the **deployer's** security guide — what knobs to turn, what to watch for, what's already handled for you. For the maintainer-facing policy (reporting a vulnerability, threat model, cryptographic choices), see [`SECURITY.md`](https://github.com/Kein95/luonvuituoi-cert/blob/main/SECURITY.md) at the repo root.

## What's protected by default

You don't need to do anything for these — they're on from the first deploy:

- **Rate limiting + CAPTCHA** on every public endpoint (`/api/search`, `/api/download`, `/api/verify`, `/api/captcha`, `/api/shipment/lookup`). Burst defaults: 20 req/min per IP for search, 30 req/min for CAPTCHA.
- **Oversized requests rejected at the socket.** Werkzeug enforces `MAX_CONTENT_LENGTH = 32 KB` before parsing, so a 1 GB POST can't exhaust parser memory.
- **User enumeration blocked.** OTP / magic-link step 1 runs the same KV write + dummy hash for known and unknown emails, so a timing observer can't probe for valid addresses.
- **QR signatures** use RSA-PSS over canonical JSON. Signature covers the payload and the project slug, so a cert issued for project A cannot be replayed against project B.
- **Atomic CAPTCHA / OTP / magic-link consumption.** Each single-use token goes through `kv.consume()`, backed by Redis `GETDEL` on Upstash. No TOCTOU race.
- **Admin CSP.** `/admin` ships with `script-src 'self' 'nonce-…'` per request, so a reflected-XSS sink can't execute code.
- **Audit log without PII.** `student.update` records the column + change flag, not the old/new values. Phones, DOBs, addresses never leave the DB via the audit forward webhook.
- **Security headers.** Every response carries `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`.
- **JWT revocation.** Sign-out adds the JTI to a KV denylist with TTL = remaining-life; no need to rotate `JWT_SECRET` to log one admin out.

## What you must configure

### 1. `JWT_SECRET`

**Required.** 32+ random characters. Without it, the app refuses to issue admin tokens.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Rotate on compromise — note that rotation invalidates every session. For single-admin compromise, use `POST /api/admin/logout` instead (see [revocation](admin-auth.md#signing-out-revoking-sessions)).

### 2. `PUBLIC_BASE_URL`

**Required for production.** Pins the origin baked into magic-link emails and QR verify URLs against an attacker-controlled `Host` header. Set it to the exact HTTPS origin — `https://mycerts.example`, no trailing slash.

### 3. `ALLOWED_ORIGINS`

**Recommended.** Comma-separated origin whitelist for `/api/*`. Leave at the default `*` only when the portal is fully public and never serves credentialed requests. Once you know the front-end origin, pin it:

```bash
ALLOWED_ORIGINS=https://mycerts.example
```

A mismatched origin gets no `Access-Control-Allow-Origin` header back — the browser will reject the cross-origin fetch.

### 4. `TRUST_PROXY_HEADERS`

Set to `1` **only** when the deploy sits behind a reverse proxy that overwrites `X-Forwarded-For` (Nginx, Caddy, Vercel, Cloud Run). Without a trusted proxy, a direct client can send the header themselves and spoof their IP — bypassing the rate limiter.

Defaults to `0` (use `request.remote_addr` directly).

### 5. `FORCE_HSTS`

Set to `1` once the site is **exclusively** reachable over HTTPS. Browsers cache `Strict-Transport-Security` for a year — enabling on an HTTP dev env locks users out when they try to revisit.

### 6. Email provider

If `admin.auth_mode` is `otp_email` or `magic_link`, set both:

- `RESEND_API_KEY` — from the Resend dashboard
- `CERT_EMAIL_FROM` (or `RESEND_FROM_ADDRESS`) — a verified sender

Without the key, the app falls back to `NullEmailProvider` and logs a warning. Login flows succeed at the HTTP level but silently drop the outgoing email, leaving users stuck.

### 7. QR signing key

`lvt-cert gen-keys` writes `private_key.pem` + `public_key.pem` to the project root. Handling:

- `private_key.pem` → filesystem ACLs (`chmod 0400`), keep out of backups that aren't themselves encrypted.
- `public_key.pem` → ship freely. Verifiers need it to check signatures.

If the private key leaks, regenerate and re-sign (every prior cert loses its signature guarantee, so plan a re-issue window if real users depend on QR verify).

### 8. `GSHEET_WEBHOOK_URL`

If you enable activity-log forwarding, the URL **must** be `https://`. Other schemes are rejected with a warning — the local SQLite audit table is always authoritative, so a disabled webhook doesn't break admin flows.

## What to watch

See [operations — Logs](operations.md#logs) for the loud messages worth alerting on. Short version:

- `RESEND_API_KEY not set` → login emails are dropping.
- `KV_BACKEND=local with N workers` → race conditions on CAPTCHA / rate-limit state.
- `must be https://` → webhook disabled due to scheme.

## Non-features (intentional)

Things we deliberately don't do, so you're not surprised:

- **No cookie-based admin sessions.** JWTs live in client-side `sessionStorage`, sent via request-body `token`. Browsers don't auto-send body params cross-origin, so CSRF is not exploitable. Do not refactor to cookies without adding a CSRF-token middleware.
- **No vendor CAPTCHA.** Math CAPTCHA handles the scrape-bot threat without a third-party dep. hCaptcha/Turnstile is a PR away if your threat model demands it.
- **No QR payload encryption.** The payload is non-sensitive (SBD + round + subject + result + issued_at). Signature alone prevents forgery.
- **No JWT revocation list for Vercel KV across deploys.** The denylist lives in your configured KV; if you switch KV backends, existing denylisted sessions flip back to "valid until exp." Use the cutover as a forcing function to rotate `JWT_SECRET`.

## Hardening checklist

Copy-paste before going to production:

- [ ] `JWT_SECRET` ≥ 32 random chars
- [ ] `PUBLIC_BASE_URL` matches the real HTTPS origin
- [ ] `ALLOWED_ORIGINS` pinned (not `*`)
- [ ] `TRUST_PROXY_HEADERS=1` if behind a reverse proxy, `0` otherwise
- [ ] `FORCE_HSTS=1` after TLS cutover
- [ ] `KV_BACKEND=upstash` or `vercel-kv` (never `local`) for multi-worker deploys
- [ ] `ADMIN_DEFAULT_PASSWORD` rotated after first admin login
- [ ] `private_key.pem` off public backups, `chmod 0400`
- [ ] Reverse proxy terminates TLS
- [ ] Dependabot PRs reviewed weekly
- [ ] Audit log periodically exported (even if `gsheet_log` is disabled)
