# Configuration reference

Every deployment is described by a single `cert.config.json`. This page is the authoritative list of keys; the JSON Schema at `cert.schema.json` powers editor autocomplete.

## Top-level shape

```jsonc
{
  "$schema": "…/cert.schema.json",
  "project":       { "name": "DEMO", "slug": "demo", "locale": "en", "branding": { … } },
  "rounds":        [{ "id": …, "label": …, "table": …, "pdf": … }],
  "subjects":      [{ "code": …, "en": …, "vi": …, "db_col": … }],
  "results":       { "<subject_code>": { "<result_name>": <page_number> } },
  "data_mapping":  { "sbd_col": …, "name_col": …, … },
  "layout":        { "page_size": [842, 595], "fields": { "<field>": { … } } },
  "fonts":         { "<font_key>": "<relative/path.ttf>" },
  "student_search": { "mode": …, "admin_mode": … },
  "admin":         { "auth_mode": …, "multi_user": …, "roles": […] },
  "features":      { "qr_verify": { … }, "shipment": { … }, "otp_email": { … }, "gsheet_log": { … }, "kv_backend": … }
}
```

## `project`

| Key | Type | Notes |
|-----|------|-------|
| `name` | string | Displayed in the page header. 1–120 chars. |
| `slug` | string | Lowercase kebab-case, used in signed QR payloads to bind certs to the issuer. |
| `locale` | `"en"` / `"vi"` | Default UI language. |
| `branding.primary_color` | hex | CSS `--primary` value. |
| `branding.accent_color` | hex | CSS `--accent` value. |
| `branding.logo_url` | string or null | Must start with `/`, `http(s)://`, or `data:image/`. `javascript:` rejected. |

## `rounds` and `subjects`

Each **round** is a set of certificates (e.g. qualifier vs finals); each **subject** is a parallel discipline (e.g. Math / Science). Every round shares the full subject list.

- `rounds[].id` + `subjects[].code` must be unique and match `^[A-Za-z0-9][A-Za-z0-9_-]*$`.
- `rounds[].table` + `subjects[].db_col` must be SQL identifiers (`^[A-Za-z_][A-Za-z0-9_]*$`).
- `rounds[].pdf` is relative to the project root; absolute paths and `..` traversal are rejected.

## `results`

Maps `subject_code → { result_name: page_number }`. Example:

```json
"results": {
  "S": { "GOLD": 1, "SILVER": 2, "BRONZE": 3 },
  "E": { "GOLD": 4, "SILVER": 5, "BRONZE": 6 }
}
```

Rules: every `subjects[].code` must appear as a top-level key; page numbers are ≥ 1 and unique within each subject. Result names in the source Excel are matched accent- and case-tolerantly.

## `data_mapping`

Maps logical roles to source column names (i.e. what the Excel/CSV header calls them). All values must pass the SQL-identifier regex.

| Key | Required |
|-----|----------|
| `sbd_col` | yes |
| `name_col` | yes |
| `dob_col`, `school_col`, `grade_col`, `phone_col` | optional — enable their respective search modes |
| `extra_cols` | `string[]` — flex fields ingested into the schema |

## `layout`

```jsonc
{
  "page_size": [842, 595],
  "fields": {
    "name":   { "x": 421, "y": 330, "font": "script", "size": 40, "color": "#1E3A8A", "align": "center", "wrap": null },
    "school": { "x": 421, "y": 280, "font": "serif",  "size": 18, "align": "center", "wrap": 60 }
  }
}
```

Field keys are the logical names the engine fills (e.g. `name`, `school`, `grade`, `dob`, `phone`). `font` must point to a key in the top-level `fonts` registry; `align` is `left` / `center` / `right`; `wrap` (optional) line-wraps at that many characters.

## `fonts`

`{ "<key>": "<relative_ttf_path>" }`. Paths cannot be absolute, contain `..`, or start with a drive letter. Keys are the tokens referenced by `layout.fields[*].font`.

## `student_search`

- `mode`: `name_dob_captcha` (default) / `name_sbd_captcha` / `sbd_phone`.
- `admin_mode`: `sbd_auth` (default) / `sbd_phone` — used by the admin panel's search form.

## `admin`

| Key | Notes |
|-----|-------|
| `auth_mode` | `password`, `otp_email`, or `magic_link`. Controls the login flow shape. |
| `multi_user` | Currently informational; the auth table always supports multiple users. |
| `roles` | Non-empty list; the built-ins are `super-admin`, `admin`, `viewer`. |

## `features`

### `qr_verify`

| Key | Notes |
|-----|-------|
| `enabled` | bool |
| `private_key_path` | defaults to `private_key.pem`. Relative, no traversal. |
| `public_key_path` | defaults to `public_key.pem`. |
| `x`, `y`, `size_pt` | Where the engine draws the QR on each overlaid page (PDF points). |
| `max_age_seconds` | `0` (default) disables expiry; non-zero rejects verify requests older than N seconds. |

### `shipment`

| Key | Notes |
|-----|-------|
| `enabled` | bool |
| `statuses` | Non-empty, case-insensitive-unique status vocabulary. |
| `fields` | Extra TEXT columns on the shipments table. Each must be a SQL identifier; clashes with reserved names (`id`, `round_id`, `sbd`, `status`, `created_at`, `updated_at`) are rejected. |
| `public_fields` | Subset of `fields` that the public lookup endpoint is allowed to return. Default empty — students see only `status` + `updated_at`. |

### `kv_backend`

`local` (default), `upstash`, or `vercel-kv`. See [Deploy — Vercel](deploy-vercel.md) for the env vars each backend needs.

### Other feature flags

- `otp_email.enabled` + `otp_email.provider: "resend"` — wires OTP login. Needs `RESEND_API_KEY` and `CERT_EMAIL_FROM` env vars.
- `gsheet_log.enabled` — forwards admin activity to `GSHEET_WEBHOOK_URL` on a background thread.

## Environment variables

Config file handles _what_ the portal does; env vars handle _where_ it runs.
Full list with defaults:

### Required

| Name | Notes |
|------|-------|
| `JWT_SECRET` | 32+ random chars. No ephemeral fallback — missing value raises `TokenError` at startup. Rotate on compromise (nukes all sessions). |
| `PUBLIC_BASE_URL` | Pins magic-link emails + QR verify URLs against Host-header injection. Set to the exact HTTPS origin. |

### Commonly set

| Name | Default | Notes |
|------|---------|-------|
| `ALLOWED_ORIGINS` | `*` | Comma-separated CORS whitelist. Leave as `*` only if the portal is fully public. |
| `TRUST_PROXY_HEADERS` | `0` | Set to `1` when deploying behind Nginx / Caddy / Vercel / Cloud Run so the app reads `X-Forwarded-For` for rate-limit bucketing. Do NOT enable on direct binds — clients could spoof the header to bypass the limiter. |
| `FORCE_HSTS` | `0` | Set to `1` once the site is reachable only via HTTPS. Emits `Strict-Transport-Security: max-age=31536000; includeSubDomains` on every response. Browsers cache HSTS — enabling on HTTP locks users out. |
| `WEB_CONCURRENCY` | `2` | Gunicorn worker count. Dockerfile sets this; if paired with `KV_BACKEND=local` and >1 worker, a startup warning fires (local KV is not cross-process safe). |
| `KV_BACKEND` | `local` | `local` / `upstash` / `vercel-kv`. See [operations](operations.md#kv-backends). |

### Auth / email

| Name | Notes |
|------|-------|
| `ADMIN_DEFAULT_PASSWORD` | Used by the one-off admin-bootstrap script. Rotate immediately after first login. |
| `RESEND_API_KEY` | Required for `otp_email` / `magic_link` auth modes. Without it, `_resolve_email_provider` falls back to `NullEmailProvider` and logs a warning — OTP / magic-link flows will silently drop messages. |
| `RESEND_FROM_ADDRESS` / `CERT_EMAIL_FROM` | Verified Resend sender. Either name works (alias for backwards compat with `.env.example`). |

### Storage backends

| Name | When set |
|------|----------|
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | `KV_BACKEND=upstash` |
| `KV_REST_API_URL` / `KV_REST_API_TOKEN` | `KV_BACKEND=vercel-kv` (auto-injected by Vercel) |
| `KV_LOCAL_PATH` | Override default `./.kv/store.json` location |

### Optional integrations

| Name | Notes |
|------|-------|
| `GSHEET_WEBHOOK_URL` | Must be `https://…`. Non-HTTPS URLs are rejected with a warning (SSRF guard). Fire-and-forget — local audit table is authoritative. |
| `GUNICORN_WORKERS` / `UVICORN_WORKERS` | Detected by the KV factory alongside `WEB_CONCURRENCY` for the multi-worker warning. |

## Validation errors

If a value is rejected at config load time you'll see a message like:

```
cert.config.json failed validation (…/cert.config.json):
  - rounds.0.pdf: round.pdf must be a relative path (got absolute '/etc/passwd')
```

The file path is always included; raw input values never are (keeps secrets out of the error stream).
