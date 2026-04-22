# Changelog

All notable changes to LUONVUITUOI-CERT. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); project uses [SemVer](https://semver.org/).

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
