# Admin authentication

Three login flavors share the same JWT-minting entry point. Pick one in `cert.config.json#admin.auth_mode`:

| Mode | Flow |
|------|------|
| `password` | Email + password, single step. |
| `otp_email` | Email first, then a 6-digit code via email, then submit the code. Two steps. |
| `magic_link` | Email first, then a one-click URL via email, then land on `/admin?token=…`. Two steps. |

Every successful login returns a JWT that encodes `sub` (user id), `email`, `role`, and `exp` (8h default). The token is HS256-signed with `JWT_SECRET`.

## `JWT_SECRET`

**Required.** There is no ephemeral fallback. A missing secret raises `TokenError('JWT_SECRET is not set')` immediately. Use 32+ random characters and rotate on compromise.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Creating the first admin

The CLI doesn't ship a one-shot admin-create command yet (on the roadmap). Use the Python API:

```python
from luonvuitoi_cert.auth import Role, create_admin_user

create_admin_user(
    "data/my-portal.db",              # same DB the handler reads
    email="you@example.org",
    role=Role.SUPER_ADMIN,
    password="a-real-password-please",
)
```

OTP and magic-link users do not need a password. Pass `password=None`.

## Roles

| Role | Capabilities |
|------|--------------|
| `super-admin` | Everything + can create/delete other admins + flip public-surface [feature gates](operations.md#public-surface-feature-gates). |
| `admin` | CRUD students, manage shipments, view activity log. |
| `viewer` | Read-only. Cannot update students or shipments. |

Handlers check role with an **allowlist** (`token.role in (ADMIN, SUPER_ADMIN)`), so future roles default to read-only until they are explicitly added to the allowlist. Super-admin-only surfaces (user management, feature gates) use a strict equality check instead of the allowlist.

## Timing-safe lookup

`verify_admin_password()` runs the PBKDF2 hash **even for unknown emails** so a wall-clock observer cannot distinguish a nonexistent account from a wrong password. The same pattern holds in the OTP and magic-link step-1 paths: unknown emails get a decoy KV write plus hash, an identical response shape, and no email is sent.

## OTP (`otp_email`)

- Code: 6 digits, `secrets.SystemRandom`.
- Storage: `SHA-256(email + "|" + code)` in KV keyed by `otp:<email>` with a 5-minute TTL. Plaintext never hits disk.
- Verify: atomic `kv.consume()` ensures a concurrent submit cannot race into double-use.
- Provider: `features.otp_email.provider`. The `resend` adapter is the only one shipped. Set `RESEND_API_KEY` and `CERT_EMAIL_FROM` in `.env`.

Bootstrap the provider in custom transport code:

```python
from luonvuitoi_cert.auth import ResendProvider

with ResendProvider(api_key=os.environ["RESEND_API_KEY"], from_address="no-reply@example.org") as mailer:
    …
```

## Magic link (`magic_link`)

- Token: 32-byte url-safe random.
- Storage: `SHA-256(token)` mapped to email, 15-minute TTL.
- Verify: atomic consume, so clicking the link twice only works once.
- Caller supplies a `link_builder(token) -> str` callback that assembles the click URL (Phase 11 dev server uses `PUBLIC_BASE_URL + "/admin?token="`).

## Signing out / revoking sessions

JWTs are stateless, so rotating `JWT_SECRET` invalidates every active session.
For the case where one admin is compromised and needs to be logged out without
disrupting everyone, the portal ships a KV-backed revocation list.

### Client flow

```http
POST /api/admin/logout
Content-Type: application/json

{"token": "<the-current-jwt>"}
```

Response is always `200`:

- `{"revoked": true, "jti": "<jti>"}`: token accepted, with `jti` added to the denylist using a TTL equal to the remaining life of the token.
- `{"revoked": false, "error": "admin session expired"}`: the token was already invalid, so there is nothing to do (the client is signing out anyway).

### Server-side enforcement

Any handler that threads `kv=` through to `verify_admin_token` will reject a
revoked session with `TokenError("admin session revoked")`. In this repo, the
Flask shim passes `kv` to:

- `/api/admin/search` (admin-mode search)
- `/api/shipment/upsert`
- `/api/admin/logout` (idempotent, since the revoke call itself does not block on prior denylist hits)

Handlers that do not pass `kv` keep the pre-M7 behavior (token valid until `exp`).
This is deliberate: your custom transport code can opt into revocation per
endpoint as you thread the KV instance through.

### Denylist storage

Entries land in the configured KV backend under `jwt_denylist:<jti>` with
TTL = `exp - now`. The denylist self-expires, so no cron job is needed. With the
default 8-hour session TTL, the worst-case denylist size is bounded by the
number of log-out events in any 8-hour window.

### Programmatic revocation

```python
from luonvuitoi_cert.auth import revoke_admin_token

jti = revoke_admin_token(kv, token=caller_jwt, env={"JWT_SECRET": "..."})
# Subsequent verify_admin_token(jwt, kv=kv) calls raise TokenError('revoked').
```

## Activity log

When you pass an `ActivityLog` to `perform_login`, it records:

- `admin.login.success`: user_id, email, role, IP.
- `admin.login.failure`: email (if provided), reason (`bad-password`, `bad-otp`, `bad-magic-link`, `missing-email`, and similar), IP.

Entries live in the `admin_activity` SQLite table and, if `GSHEET_WEBHOOK_URL` is set, are forwarded asynchronously on a daemon thread so a slow or unavailable webhook does not block the login response.

## Transport-layer contract

Whoever wires `perform_login` into HTTP (the dev server does it at `/api/admin/login`) **must**:

1. Call `validate_request_size(body, max_bytes=32 * 1024)` before parsing JSON.
2. Catch `LoginError` and translate to HTTP 401. Do not catch `Exception`, because internal bugs should bubble to the platform's 500 handler rather than leak as the 401 body.
3. Emit `Content-Security-Policy: script-src 'self' 'nonce-…'` on `/admin` (or any page that renders the JWT-handling JS) so a reflected XSS sink cannot exfiltrate the token from `sessionStorage`.
