# LUONVUITUOI-CERT

> Config-driven certificate portal toolkit. Bring your own PDF template + student list → ship a search / download / QR-verify / admin portal to Vercel or Docker in an afternoon.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)
[![Tests: 383](https://img.shields.io/badge/tests-383%20passing-brightgreen.svg)](#)

## Why

Running a competition, issuing training diplomas, or distributing awards to a cohort? You typically need:

- A **public page** where recipients look up and download their personalized PDF.
- An **admin backend** to manage records, corrections, and shipments.
- A **verification page** so third parties (employers, schools) can confirm a certificate is genuine.

LUONVUITUOI-CERT ships all three — config-driven, zero-code — deployable to Vercel's free tier or a Docker host.

## Features

- Three public surfaces: student portal (`/`), admin panel (`/admin`), Certificate-Checker (`/certificate-checker`).
- Student search: name + DOB + CAPTCHA (or name + SBD, or SBD + phone — configurable).
- PDF overlay: reportlab + pypdf, TrueType fonts, per-field positioning.
- RSA-PSS-signed QR verification with optional expiry.
- Multi-user admin: RBAC (`super-admin` / `admin` / `viewer`), JWT sessions, 3 auth modes (password / OTP email / magic link).
- Shipment tracking with a `public_fields` allowlist.
- Activity log: SQLite local + optional Google Sheets webhook forwarding.
- Rate limiting + CAPTCHA + security headers (CSP with per-request nonce on admin).
- Ingest Excel / CSV / JSON with config-mapped column names.
- i18n: English + Vietnamese out-of-the-box, extensible per project.

## Quickstart

```bash
# Pre-PyPI: install from source
git clone https://github.com/Kein95/luonvuituoi-cert
cd luonvuituoi-cert
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ./packages/core -e ./packages/cli

# (once published: pip install luonvuitoi-cert-cli)

lvt-cert init my-award
cd my-award
cp .env.example .env                     # set JWT_SECRET + ADMIN_DEFAULT_PASSWORD
lvt-cert gen-keys                        # QR signing keys (if features.qr_verify.enabled)
lvt-cert seed --count 10                 # fake students in data/students.xlsx
lvt-cert dev                             # http://localhost:5000
```

Want every feature wired up against a fabricated "DEMO ACADEMY"?

```bash
cd examples/demo-academy
python prepare_demo.py
lvt-cert gen-keys
lvt-cert dev
```

## Deploy

- **Vercel** — `vercel deploy` against the scaffolded `api/index.py` + `vercel.json`. See [docs/deploy-vercel.md](docs/deploy-vercel.md).
- **Docker** — `docker compose up -d` against the repo-root Dockerfile + compose file. See [docs/deploy-docker.md](docs/deploy-docker.md).

## Repo layout

```text
packages/
  core/                # luonvuitoi-cert — engine + handlers + UI templates
  cli/                 # luonvuitoi-cert-cli — lvt-cert scaffolder + Flask dev server
examples/
  demo-academy/        # full-feature reference project
docs/                  # MkDocs Material source
```

## Documentation

Quickstart, configuration reference, PDF overlay guide, admin auth, deploy guides, QR verify + shipment feature docs live under [docs/](docs/) and build to **<https://kein95.github.io/luonvuituoi-cert>** once the Pages workflow publishes.

## Security

This is a public-facing portal. See [SECURITY.md](SECURITY.md) for the threat model, hardening checklist, and how to report vulnerabilities.

Highlights:

- `JWT_SECRET` mandatory (no ephemeral fallback).
- `PUBLIC_BASE_URL` pins magic-link + QR URLs against Host-header injection.
- CAPTCHA / OTP / magic-link use atomic `kv.consume()` — no race.
- PBKDF2 passwords, RSA-PSS QR signatures, CSP nonce on admin.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). One rule worth calling out: this repo was extracted from three internal certificate portals, and nothing of theirs ships in the public code. Please keep it that way.

## License

MIT © LUONVUITUOI-CERT contributors. See [LICENSE](LICENSE).
