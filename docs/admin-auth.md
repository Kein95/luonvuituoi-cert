# Admin authentication

Three login flavors share the same JWT-minting entry point. Pick one in `cert.config.json#admin.auth_mode`:

| Mode | Flow |
|------|------|
| `password` | Email + password, single step. |
| `otp_email` | Email first → 6-digit code via email → submit code. Two steps. |
| `magic_link` | Email first → one-click URL via email → land on `/admin?token=…`. Two steps. |

Every successful login returns a JWT that encodes `sub` (user id), `email`, `role`, and `exp` (8h default). The token is HS256-signed with `JWT_SECRET`.

## `JWT_SECRET`

**Required.** No ephemeral fallback — a missing secret raises `TokenError('JWT_SECRET is not set')` immediately. Use 32+ random characters; rotate on compromise.

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

OTP / magic-link users don't need a password — pass `password=None`.

## Roles

| Role | Capabilities |
|------|--------------|
| `super-admin` | Everything + can create/delete other admins. |
| `admin` | CRUD students, manage shipments, view activity log. |
| `viewer` | Read-only. Cannot update students or shipments. |

Handlers check role with an **allowlist** — `token.role in (ADMIN, SUPER_ADMIN)` — so future roles default to read-only until they're explicitly added to the allowlist.

## Timing-safe lookup

`verify_admin_password()` runs the PBKDF2 hash **even for unknown emails** so a wall-clock observer can't distinguish a nonexistent account from a wrong password. The same pattern holds in the OTP/magic-link step-1 paths: unknown emails get a decoy KV write + hash, identical response shape, and no email is sent.

## OTP (`otp_email`)

- Code: 6 digits, `secrets.SystemRandom`.
- Storage: `SHA-256(email + "|" + code)` in KV keyed by `otp:<email>` with a 5-minute TTL. Plaintext never hits disk.
- Verify: atomic `kv.consume()` — a concurrent submit can't race into double-use.
- Provider: `features.otp_email.provider` — `resend` is the only adapter shipped. Set `RESEND_API_KEY` and `CERT_EMAIL_FROM` in `.env`.

Bootstrap the provider in custom transport code:

```python
from luonvuitoi_cert.auth import ResendProvider

with ResendProvider(api_key=os.environ["RESEND_API_KEY"], from_address="no-reply@example.org") as mailer:
    …
```

## Magic link (`magic_link`)

- Token: 32-byte url-safe random.
- Storage: `SHA-256(token)` → email, 15-minute TTL.
- Verify: atomic consume — clicking the link twice only works once.
- Caller supplies a `link_builder(token) -> str` callback that assembles the click URL (Phase 11 dev server uses `PUBLIC_BASE_URL + "/admin?token="`).

## Activity log

When you pass an `ActivityLog` to `perform_login`, it records:

- `admin.login.success` — user_id, email, role, IP.
- `admin.login.failure` — email (if provided), reason (`bad-password`, `bad-otp`, `bad-magic-link`, `missing-email`, …), IP.

Entries live in the `admin_activity` SQLite table and, if `GSHEET_WEBHOOK_URL` is set, are forwarded asynchronously on a daemon thread so the webhook being slow or down doesn't block the login response.

## Transport-layer contract

Whoever wires `perform_login` into HTTP (the dev server does it at `/api/admin/login`) **must**:

1. Call `validate_request_size(body, max_bytes=32 * 1024)` before parsing JSON.
2. Catch `LoginError` and translate to HTTP 401. Don't catch `Exception` — internal bugs should bubble to the platform's 500 handler, not leak as the 401 body.
3. Emit `Content-Security-Policy: script-src 'self' 'nonce-…'` on `/admin` (or any page that renders the JWT-handling JS) so a reflected XSS sink can't exfiltrate the token from `sessionStorage`.
