# Changelog

All notable changes to LUONVUITUOI-CERT. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); project uses [SemVer](https://semver.org/).

## [Unreleased]

Post-1.0 security + ops hardening pass (PRs #3-#12).

### Added

- **Shipment draft state machine** — admins can now curate drafts (filter by column / result tier / external SBD list), export a batch to carrier-ready Excel, then hard-lock. Once the carrier returns tracking data, the bulk-import hook flips matching drafts from `exported` to `promoted` automatically. New `shipment_draft` table, `lvt-cert shipment draft add/list/cancel` + `lvt-cert shipment export` CLI group, and `POST /api/admin/shipments/draft{,/list,/cancel}` + `POST /api/admin/shipments/export` API endpoints. `features.shipment.import.profiles.<carrier>.export_template` config drives the carrier-specific column headers.
- **Bulk shipment import** — new `lvt-cert import-shipments` CLI and `POST /api/admin/shipments/import` endpoint parse carrier Excel/CSV exports into a new `shipment_history` table (PK `(round_id, sbd, tracking_code)` — audit trail preserved). Config-driven multi-carrier profiles (`features.shipment.import.profiles.{viettel, ghn, ...}`), column-name fallbacks, `success_keywords` per carrier, `--dry-run` default with `--commit` opt-in. SBD matching via `data_mapping.phone_col`. Admin-only API endpoint with 10 MB cap + 5 req/min rate limit. Logs `shipment.bulk_import` with summary metadata (no PII).
- **`POST /api/admin/logout`** endpoint. JWTs can be revoked without rotating `JWT_SECRET`. Denylist stored in KV (`jwt_denylist:<jti>`) with TTL = remaining session life. `verify_admin_token(kv=…)` checks denylist; opt-in per-endpoint for backwards compat. (M7)
- **`GET /health`** — cheap dependency-free health probe for container / k8s probes. Replaces the `POST /api/captcha` probe (which burned KV writes every 30s). (M4)
- **`/api/*` CORS**: `Access-Control-Allow-Origin` echoed per `ALLOWED_ORIGINS`, OPTIONS preflight handler, `Vary: Origin` + 600s `Max-Age`. Previously CORS was advertised in docstring but no headers emitted. (C1)
- **`/api/captcha` rate limit** (30/min/IP) — closes the unbounded-KV-write DoS. (C2)
- **`_resolve_email_provider()`** — `build_app` now resolves a real `ResendProvider` when `RESEND_API_KEY` + `RESEND_FROM_ADDRESS` (or `CERT_EMAIL_FROM`) are set; falls back to `NullEmailProvider` with a warning. Previously hardcoded to Null. (C3)
- **Dependabot config** covering pip (core + cli), github-actions, docker. Weekly pip cadence, monthly other. (M2)
- **Real `/app/wsgi.py`** committed to the repo; Dockerfile drops the `printf` heredoc shim. (M3)
- **Non-root container**: Dockerfile runs as `app:app` system user.
- **JWT denylist TTL regression tests**, CORS preflight tests, captcha rate-limit test, email-provider resolution tests, rounds-cap test, webhook-HTTPS-only test, `/health` test, `X-Frame-Options` test.
- **New docs**: `architecture.md`, `security.md`, `operations.md`, `troubleshooting.md`. Full environment-variable reference in `config-reference.md`.

### Changed

- **mypy now blocking** in CI. 3 pre-existing type errors cleared (`rate_limiter.Callable`, `captcha._Op.symbol` read-only, `activity_log` dict invariance). (M1)
- **`X-Forwarded-For` opt-in**: trusted only when `TRUST_PROXY_HEADERS=1`. Previously trusted unconditionally — clients could spoof the header to bypass rate limits. (H5)
- **`rounds` capped at 20** in Pydantic config validation; public search can't fan out unbounded queries. (H3)
- **Activity-log webhook** uses a module-level `ThreadPoolExecutor(4)` instead of one daemon thread per call. (H4)
- **Activity-log webhook URLs** must be `https://`; non-HTTPS rejected with a warning (SSRF guard). (M6)
- **`admin.student.update` audit metadata** no longer persists raw `old`/`new` values; records `{column, changed, value_length_delta}` only — PII never reaches the GSheet forward. (M5)
- **`verify_admin_password`** now issues a single `SELECT` instead of two. (M8)
- **Docker image** sets `WEB_CONCURRENCY=2` env, healthcheck probes `/health`. (M4)
- **Security headers**: `X-Frame-Options: DENY` on every response, `Strict-Transport-Security` behind `FORCE_HSTS=1`.
- **GitHub Actions** bumped to Node 24-compatible versions (`checkout@v5`, `setup-python@v6`, `configure-pages@v5`, `upload-pages-artifact@v4`, `deploy-pages@v5`).

### Fixed

- **Flaky `test_search_rate_limit_kicks_in`**: now loops up to 2× the rate limit + 2 buffer, tolerates window-boundary rollover. (T1)
- **README tests badge**: dynamic GitHub Actions shield instead of static "tests: 383". (L1)
- **KV multi-worker warning**: `open_kv` logs a loud warning when `KV_BACKEND=local` and `WEB_CONCURRENCY > 1`. (H2)

### Docs

- Explicit H1 (SQL-identifier allowlist model) + H6 (CSRF posture guardrail) notes in `SECURITY.md`.
- Per-project audit-log PII hygiene rule in `CONTRIBUTING.md`.

## [1.0.0] — 2026-04-22

First public release. Extracts a config-driven certificate portal toolkit from three internal competition-certificate portals. Zero-leak policy enforced throughout: no strings, fonts, data, or domain artifacts from the source projects ship in the public codebase.

### Added

**Engine**

- Pydantic v2 `CertConfig` with cross-field validation (round ID uniqueness, subject ↔ results match, layout fonts registered, path-traversal guards on every file reference, SQL-identifier guards on every interpolated column).
- PDF overlay renderer built on reportlab + pypdf, with an idempotent path-keyed FontRegistry and safe-by-default field clamping (`MAX_FIELD_LENGTH = 1000`, whitespace-only skipped).
- i18n `Locale` with dotted-key lookup, `$name` substitution via `string.Template.safe_substitute` (no format-string injection), EN/VI bundles.

**Storage + ingest**

- SQLite schema derived from config; one table per round with shared column list.
- KV backends: `MemoryKV`, `LocalFileKV` (atomic tempfile writes), `RestKV` (Upstash + Vercel KV share this adapter). All expose an atomic `consume()` so CAPTCHA / OTP / magic-link paths are race-free.
- Ingest readers for Excel, CSV (streaming, quoted-multiline safe), JSON (list root or envelope). Orchestrator with warn/skip/replace duplicate policies. GSheet deferred to a later release.

**Handlers**

- `search_student` + `download_certificate` with student + admin modes, CAPTCHA-before-rate-limit gating, Vietnamese-accent-tolerant name match, multi-format DOB normalization (ISO / dotted / slashed).
- Arithmetic CAPTCHA with single-use consume semantics.
- RSA-PSS-SHA256 QR signer + `/api/verify` with project-slug binding + optional `max_age_seconds` TTL. Canonical-JSON payloads are byte-stable across runtimes.
- Admin subsystem: PBKDF2 passwords, JWT HS256 tokens (strict `JWT_SECRET` — no ephemeral fallback), three login flows (password / OTP-email / magic-link) with uniform-time responses for unknown emails, `admin_activity` audit log with optional async GSheet webhook.
- Opt-in shipment tracking with `(round_id, sbd)` upserts, race-safe `ON CONFLICT DO UPDATE`, and `public_fields` allowlist (default empty — students see only `status` + `updated_at`).

**UI**

- Jinja templates: student portal (three search modes, CAPTCHA auto-refresh, download via Blob URL), admin panel (auth-mode-aware login + sessionStorage JWT + SBD lookup + sign-out wipes state), Certificate-Checker (paste / auto-fill from `?blob=`, fetch + verdict). All pages respect `config.project.branding` CSS vars, autoescape everywhere, CSP nonce on the admin page.

**CLI + transport**

- `lvt-cert init` scaffolder copies a bundled skeleton, renders `.j2` via Jinja `tojson`, and round-trips the rendered config through the validator so typos fail loud.
- `lvt-cert seed` generates Faker students with deterministic `--seed`.
- `lvt-cert dev` serves the Flask app via `build_app()`; `lvt-cert gen-keys` mints RSA pairs.
- Flask dev shim + Vercel `api/index.py` entrypoint share a single request dispatcher; Dockerfile + docker-compose ship a production-shaped host.

**Docs + CI**

- MkDocs Material site: quickstart, config reference, PDF overlay guide, admin-auth, deploy (Vercel + Docker), QR verify, shipment tracking.
- GitHub Actions: pytest matrix (py3.11 + py3.12), ruff lint + format, mypy advisory, demo-academy smoke test, GitHub Pages docs publish.
- 383 unit + E2E tests; end-to-end flows verified through a live Flask server.

### Security posture

- No ephemeral `JWT_SECRET` fallback.
- CAPTCHA + OTP + magic-link all use the atomic `kv.consume()` primitive; concurrent requests with the same correct answer cannot both succeed.
- Uniform-time OTP / magic-link step 1 regardless of whether the email maps to a real admin (closes user-enumeration timing oracle).
- Host-header injection blocked via `PUBLIC_BASE_URL` env var for magic-link and QR URLs.
- `branding.logo_url` scheme allowlist rejects `javascript:` / `vbscript:`.
- Admin page CSP uses a per-request nonce; no `'unsafe-inline'`.
- PII redaction: shipment audit log records `fields_touched` (names), not raw values.

### Deferred to future releases

- Google Sheets ingest reader (OAuth / service-account wiring).
- Playwright end-to-end browser tests (httpx is sufficient today).
- Postgres/Turso data-layer adapter for deployments that outgrow SQLite.
- CLI for managing admin users (today: the Python API in `luonvuitoi_cert.auth`).

[1.0.0]: https://github.com/Kein95/luonvuituoi-cert/releases/tag/v1.0.0
