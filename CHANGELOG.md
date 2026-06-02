# Changelog

All notable changes to LUONVUITUOI-CERT. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); project uses [SemVer](https://semver.org/).

## [Unreleased]

Post-1.0 security + ops hardening pass (PRs #3-#12).

### Added

- **Shipment-tracking lookup on the student portal** — when `features.shipment` is enabled, the public portal (`/`) now shows a "Track your certificate shipment" card. Recipients enter their registration number plus **name or phone (last-4)** to see delivery status + allowlisted public fields. The phone field appears only when `data_mapping.phone_col` is configured; the lookup always requires its own CAPTCHA. EN + VI strings included.
- **QR image upload on Certificate-Checker** — operators can drop a screenshot or photo of a printed QR (PNG/JPG/WebP) into the verifier page; client-side `jsQR` decode auto-fills the existing `blob` textarea and triggers verify. Pure-frontend (zero backend changes), bundled vendor file `static/jsqr.min.js` (Apache-2.0, operator-vendored — see `packages/core/luonvuitoi_cert/static/README.md`). New `/static/<name>` dispatcher route with strict allowlist (filename regex, MIME allowlist, no traversal) and `Cache-Control: public, max-age=31536000, immutable`. Decode-bomb guard: `createImageBitmap` with `resizeWidth/resizeHeight` so the browser downscales during decode rather than after — a 9 MB JPEG that would decompress to 25 000×25 000 px never materializes at full resolution. Upload button hidden when the decoder isn't loaded so the manual paste flow keeps working in vendored-asset-absent deploys. New EN/VI locale strings under `verify.upload_*`. End-to-end Flask-test-client coverage of the `/static` route (5 tests) plus reader-level coverage of name validation + traversal vectors (8 tests) plus 6 template-render tests.
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
- **Docker image** defaults to `WEB_CONCURRENCY=1` (the `local` KV backend is single-process only; running more workers needs a REST backend), healthcheck probes `/health`. (M4)
- **Security headers**: `X-Frame-Options: DENY` on every response, `Strict-Transport-Security` behind `FORCE_HSTS=1`.
- **GitHub Actions** bumped to Node 24-compatible versions (`checkout@v5`, `setup-python@v6`, `configure-pages@v5`, `upload-pages-artifact@v4`, `deploy-pages@v5`).

### Fixed

- **Flaky `test_search_rate_limit_kicks_in`**: now loops up to 2× the rate limit + 2 buffer, tolerates window-boundary rollover. (T1)
- **README tests badge**: dynamic GitHub Actions shield instead of static "tests: 383". (L1)
- **KV multi-worker guard**: `open_kv` now **raises** (was: warning) when the effective backend is `local` and `WEB_CONCURRENCY > 1`, since the per-process lock can't prevent cross-process replay of single-use CAPTCHA/OTP/magic-link tokens or rate-limit undercount. (H2)
- **Bulk shipment import 413** — the app-wide 32 KB body cap pre-empted the carrier-import route's own 10 MB limit, so any real multi-MB xlsx was rejected with a 413 before the handler ran. The import route now raises its per-request cap (`request.max_content_length`) so genuine uploads parse; JSON routes stay bounded at 32 KB.
- **Draft result-filter targeted the wrong columns** — `draft_add(result=…)` matched the result token against every non-excluded column via a hardcoded literal exclusion list, so under non-default `data_mapping` / `extra_cols` naming it could select students by an incidental column value. It now matches only configured subject columns (`subject.db_col`).
- **Docs/runtime layering** — corrected the `luonvuitoi_cert_cli.server` docstring that claimed it was a dev-only shim; production (Docker `wsgi.py` and the Vercel scaffold entrypoint) reuses the same `build_app`, so it's a production dependency.
- **Bulk-import re-send data loss** — promoting a re-sent shipment (new tracking code for an already-`promoted` SBD) hit a `UNIQUE(round_id,sbd,status)` collision that raised `IntegrityError` and rolled back the *entire* import transaction, discarding every just-inserted `shipment_history` row. The promote step now retires the stale draft row first (its record is preserved in `shipment_history`, keyed by tracking code) and only acts when there's an exported draft to close, so re-sends and re-runs are safe.
- **Rate limiter race** — `check_rate_limit` was a non-atomic `get`-then-`set`, so concurrent requests could read the same count before any write and slip past the cap. Added an atomic `incr` to the KV contract (Redis `INCR`+`EXPIRE` for RestKV; increment-under-lock for Memory/Local) and switched the limiter to it.
- **Silent Vietnamese glyph loss** — the PDF renderer now logs a warning when a field's text contains characters the configured font has no glyph for (e.g. a Latin-only font dropping tone-marked names), surfacing what was previously a silent blank-box render. Detection uses ReportLab's parsed cmap; no new dependency.
- **Carrier-export formula injection** — values starting with `= + - @` (or leading whitespace/control chars) in the exported draft Excel are now prefixed with an apostrophe so the carrier's spreadsheet treats them as text instead of executing a formula.
- **Export filename** — the draft-export download filename is run through `sanitize_filename` before it reaches `Content-Disposition` (defense-in-depth against an unvalidated carrier profile key).
- **Malformed admin tokens** — `verify_admin_token` now rejects a JWT missing any of `sub`/`email`/`iat`/`exp` instead of building an `AdminToken` with empty/zeroed fields (protects audit-log integrity and expiry logic).
- **Duplicate ingest headers** — the Excel and CSV readers now raise on duplicate column headers instead of silently collapsing them last-wins (which dropped a column's data).
- **RestKV robustness** — `scan_prefix` escapes Redis glob metacharacters in the prefix and caps `COUNT` at the caller's limit; `RestKV` is now a context manager (`with`-closeable).
- **Template PDF size cap** — the renderer rejects template PDFs over 50 MB before parsing (guard against a pathological/accidental file blowing up per-request memory).
- **Docker healthcheck** — `docker-compose` now probes the dependency-free `GET /health` instead of `POST /api/captcha` (which wrote a KV entry every 30 s and could trip the captcha rate limit).
- **Internal cleanup** — deduplicated the shipment UTC-timestamp helper into `shipment/_time.py` (`iso_now`); removed a dead `FIXED_COLUMNS` lint-placeholder and an inaccurate pypdf-version comment.

### Security

- **Login rate limiting** — `/api/admin/login` is now throttled (10/min per IP **and** per submitted email), closing the only public credential-guessing surface that lacked a limit. Bounds password brute-force and caps OTP-guess volume within the code's TTL window.
- **Boot guard for placeholder secrets** — the app refuses to start (and tokens refuse to sign/verify) when `JWT_SECRET` or `ADMIN_DEFAULT_PASSWORD` is still the shipped `change-me…` placeholder, so a copy-`.env`-unedited deploy can't run with a public-repo signing secret or a guessable super-admin password.
- **Shipment lookup identity factor** — `POST /api/shipment/lookup` now requires the recipient to confirm identity by **name OR phone** (last-4) on top of CAPTCHA + rate limit, and honours the public-lookup freeze, so a guessable, sequential SBD can no longer enumerate shipment status / allowlisted PII, and an embargo covers this surface too.
- **`KV_BACKEND` env honoured** — `open_kv` now lets the `KV_BACKEND` env var (advertised in `.env` / compose) override `config.features.kv_backend` instead of being inert; combined with the multi-worker hard error, the documented knob actually selects the backend.
- **Scaffold deploy hardening** — `lvt-cert init` `.env.example` now ships `PUBLIC_BASE_URL`, `ALLOWED_ORIGINS`, `TRUST_PROXY_HEADERS`, and `FORCE_HSTS` (previously omitted), so a scaffolded deploy no longer silently falls back to a spoofable Host header for magic-link / QR URLs and wildcard CORS.
- **CSP on all public pages** — the nonce-based Content-Security-Policy now covers the student portal (`/`) and certificate-checker, not just `/admin`. Both reflect user input, so they now have the same XSS backstop (the per-request nonce was previously inert on those pages). `img-src` allows an external branding logo.
- **`gen-keys` writes the QR private key 0600** — `private_key.pem` is created owner-only from the start (`os.open(..., 0o600)`) instead of inheriting the umask (often world-readable 0644). It's the sole secret behind every QR signature, so its at-rest permissions are enforced in code rather than left to a remembered `chmod`. (POSIX; best-effort on Windows.)
- **`JWT_SECRET` minimum length** — a secret under 32 bytes is now rejected (HS256 is a symmetric MAC; a short secret is brute-forceable offline from one captured token).

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
