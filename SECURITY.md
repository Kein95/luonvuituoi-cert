# Security Policy

## Supported versions

LUONVUITUOI-CERT follows semantic versioning. The latest minor release of the current major branch receives security fixes. Earlier minors receive fixes only when the upgrade path would break a public API.

| Version | Supported |
|---------|-----------|
| 1.x     | ✓         |
| < 1.0   | ✗         |

## Reporting a vulnerability

If you believe you've found a vulnerability in LUONVUITUOI-CERT:

- **Do not** open a public GitHub issue.
- Email the maintainers — if the repository has a `.github/SECURITY_CONTACTS` or the `README.md` lists a security contact, use that. Otherwise open a draft **private security advisory** via the GitHub repository's Security tab.
- Include reproduction steps, the affected version, and any proof-of-concept material you have.

We aim to acknowledge reports within 72 hours and to ship a fix or mitigation within 30 days for critical issues. You'll be credited in the advisory unless you request otherwise.

## Threat model

LUONVUITUOI-CERT is a public-facing certificate portal. The design assumptions:

- **Config author is trusted.** The operator writes `cert.config.json` and provides the PDF template, fonts, RSA private key, and DB. We validate relative paths, SQL identifiers, and hex colors defensively, but an operator determined to inject SQL into `data_mapping.sbd_col` would still succeed once they bypass the Pydantic check. We do not protect against malicious operators.
- **Students are untrusted.** Every public endpoint (`/api/search`, `/api/download`, `/api/verify`, `/api/captcha`, `/api/shipment/lookup`) applies CAPTCHA + rate limiting and rejects oversized bodies pre-parse.
- **Admins are trusted within their role.** Viewer role is read-only; admin/super-admin can CRUD. Authentication failures leave an `admin.login.failure` audit entry with the caller's IP.
- **The network is hostile.** `JWT_SECRET` is mandatory; there is no ephemeral fallback. `PUBLIC_BASE_URL` must be set in production so magic-link emails and printed QR URLs aren't poisoned by attacker-controlled `Host` headers.

Out-of-scope:

- Denial of service via costly renders (we cap `MAX_FIELD_LENGTH = 1000`, `MAX_CONTENT_LENGTH = 32 KB`, `MAX_QR_TEXT_LENGTH = 2000`; beyond that, a resource-exhaustion attack succeeds at the platform level).
- Supply-chain compromise of `reportlab`, `pypdf`, `pydantic`, `cryptography`, or `flask`. Pin dependencies in your deployment's lockfile.
- Compromise of the signing key. If `private_key.pem` leaks, rotate it and any certificates signed with it lose their authenticity guarantee.

## Hardening checklist

Before exposing a deployment publicly:

1. Set `JWT_SECRET` to 32+ random characters. Rotate on compromise.
2. Set `PUBLIC_BASE_URL` to the exact HTTPS origin the portal is reachable at.
3. Set `ADMIN_DEFAULT_PASSWORD` to something secret and change the initial admin's password immediately after first login.
4. If you enable QR verification, protect `private_key.pem` with filesystem ACLs and exclude it from backups that are not themselves encrypted.
5. Put the Flask dev server behind a reverse proxy (Nginx / Caddy) that terminates TLS and forwards `X-Forwarded-For`. Set `TRUST_PROXY_HEADERS=1` so the app honors the forwarded IP for rate limiting; without this, the bucket is keyed on the unspoofable `remote_addr` but a proxy chain will hide the real client.
6. If you enable `otp_email` or `magic_link`, use a real transactional provider (`RESEND_API_KEY` wired up) rather than shipping `NullEmailProvider`.
7. Review the admin-mode CSP on `/admin` and extend `script-src`/`style-src` only with specific nonces — never re-introduce `'unsafe-inline'`.
8. Enable the `gsheet_log` feature only with a webhook that can afford PII exposure; otherwise the local SQLite audit table is authoritative. The webhook URL is rejected if it is not `https://`.
9. Set `ALLOWED_ORIGINS` to a comma-separated list of trusted origins if the portal is embedded cross-domain; otherwise the app will emit `Access-Control-Allow-Origin: *` and browsers will happily call `/api/*` from anywhere.
10. Set `FORCE_HSTS=1` once the site is reachable exclusively over HTTPS. Do not enable on HTTP/dev — HSTS is cached by browsers.

### H1 — SQL identifier model (clarification)

`admin_update.py` accepts a `column` name from the client body and interpolates it into a SQL statement. We validate against an allowlist derived from `_allowed_columns(config)` — a name not in the allowlist is rejected before any SQL is built. A malicious **operator** who authored the config can smuggle a column that eventually maps to something hostile (e.g., a reserved word, a name that collides with a trigger). Per the trust model at the top, *config authors are trusted*; review your config before deploying.

### H6 — CSRF posture (do-not-touch)

Admin auth ships JWTs in the request **body** (via `sessionStorage` on the client), not in a cookie. Browsers do not auto-send body params on cross-site requests, so CSRF is not exploitable. **Do not refactor admin auth to cookie storage** without adding a CSRF token + `SameSite=Strict` middleware first — that refactor would quietly re-introduce the entire CSRF attack surface. See the `cookie storage is a deliberate non-feature` note in `CONTRIBUTING.md`.

## Cryptographic choices

- **Passwords**: PBKDF2-SHA256, 200,000 iterations, 16-byte salt, 32-byte hash. Stored as `pbkdf2$iterations$salt_b64$hash_b64` so migrating to argon2id in a future release can coexist with existing rows.
- **Tokens**: JWT HS256 with an 8-hour default TTL. Include `sub`, `email`, `role`, `jti`, `iat`, `exp`.
- **QR signatures**: RSA-PSS over canonical-JSON payloads, SHA-256, 2048-bit keys by default. No encryption layer — the payload is non-sensitive (SBD + round + subject + result + issued_at).
- **CAPTCHA / OTP / magic-link storage**: SHA-256 of the salted answer; atomic `consume()` ensures single use even under concurrency.
