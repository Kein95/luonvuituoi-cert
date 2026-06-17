<div align="center">

# 📜 LUONVUITUOI-CERT

**Config-driven certificate portal toolkit.**
Bring your own PDF template and student list, then ship a search, download, QR-verify, and admin portal to Vercel or Docker in an afternoon.

[![Docs](https://img.shields.io/badge/Docs-luonvuituoi--cert-0d6e6e?style=for-the-badge&logo=materialformkdocs&logoColor=white)](https://kein95.github.io/luonvuituoi-cert/)
[![Tests](https://img.shields.io/github/actions/workflow/status/Kein95/luonvuituoi-cert/test.yml?style=for-the-badge&label=tests&logo=github)](https://github.com/Kein95/luonvuituoi-cert/actions/workflows/test.yml)
&nbsp;

![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB?style=flat-square&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-server-000000?style=flat-square&logo=flask&logoColor=white)
![QR](https://img.shields.io/badge/QR-RSA--PSS%20signed-0d6e6e?style=flat-square)
![Bilingual](https://img.shields.io/badge/UI-VI%20%2F%20EN-0ea5e9?style=flat-square)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)

### [📖 Docs →](https://kein95.github.io/luonvuituoi-cert/) &nbsp;·&nbsp; [⚡ Quickstart](https://kein95.github.io/luonvuituoi-cert/quickstart/) &nbsp;·&nbsp; [🔐 QR Verify](https://kein95.github.io/luonvuituoi-cert/features/qr-verify/) &nbsp;·&nbsp; [🚚 Shipment](https://kein95.github.io/luonvuituoi-cert/features/shipment/) &nbsp;·&nbsp; [⭐ GitHub](https://github.com/Kein95/luonvuituoi-cert)

</div>

---

> 🤝 Farewell to our teammate [@Liamlenguyen](https://github.com/Liamlenguyen). Wishing you success on the path you've chosen ✨

Sibling project of [**LUONVUITUOI-HONOR ROLL**](https://github.com/Kein95/luonvuituoi-honor-roll), the student honor-roll toolkit. Where HONOR ROLL publishes and celebrates achievements, CERT **issues and verifies** the certificates.

## 💡 Why

Running a competition, issuing training diplomas, or distributing awards to a cohort? You typically need:

- A **public page** where recipients look up and download their personalized PDF.
- An **admin backend** to manage records, corrections, and shipments.
- A **verification page** so third parties (employers, schools) can confirm a certificate is genuine.

LUONVUITUOI-CERT ships all three. It is config-driven and zero-code, deployable to Vercel's free tier or a Docker host.

## ✨ Features

- **🖥️ Three public surfaces**: student portal (`/`), admin panel (`/admin`), Certificate-Checker (`/certificate-checker`).
- **🔍 Student search**: name + DOB + CAPTCHA (or name + SBD, or SBD + phone; configurable).
- **📄 PDF overlay**: reportlab + pypdf, TrueType fonts, per-field positioning.
- **🔐 QR verification**: RSA-PSS signatures with optional expiry.
- **👥 Multi-user admin**: RBAC (`super-admin` / `admin` / `viewer`), JWT sessions, three auth modes (password / OTP email / magic link).
- **🚚 Shipment tracking** with a `public_fields` allowlist.
- **📋 Activity log**: SQLite local plus optional Google Sheets webhook forwarding.
- **🛡️ Hardening**: rate limiting, CAPTCHA, and security headers (CSP with a per-request nonce on admin).
- **📥 Flexible ingest**: Excel / CSV / JSON with config-mapped column names.
- **🌏 Bilingual UI (VI / EN)** out of the box, extensible per project.

## ⚡ Quickstart

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

## ☁️ Deploy

- **Vercel**: run `vercel deploy` against the scaffolded `api/index.py` and `vercel.json`. See [docs/deploy-vercel.md](docs/deploy-vercel.md).
- **Docker**: run `docker compose up -d` against the repo-root Dockerfile and compose file. See [docs/deploy-docker.md](docs/deploy-docker.md).

## 📁 Repo layout

```text
packages/
  core/                # luonvuitoi-cert: engine + handlers + UI templates
  cli/                 # luonvuitoi-cert-cli: lvt-cert scaffolder + Flask dev server
examples/
  demo-academy/        # full-feature reference project
docs/                  # MkDocs Material source
```

## 📚 Documentation

Quickstart, configuration reference, PDF overlay guide, admin auth, deploy guides, plus the QR verify and shipment feature docs live under [docs/](docs/) and build to **<https://kein95.github.io/luonvuituoi-cert>**.

## 🔒 Security

This is a public-facing portal. See [SECURITY.md](SECURITY.md) for the threat model, hardening checklist, and how to report vulnerabilities.

Highlights:

- `JWT_SECRET` mandatory (no ephemeral fallback).
- `PUBLIC_BASE_URL` pins magic-link and QR URLs against Host-header injection.
- CAPTCHA / OTP / magic-link use atomic `kv.consume()` with no race.
- PBKDF2 passwords, RSA-PSS QR signatures, CSP nonce on admin.

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). One rule worth calling out: this repo was extracted from three internal certificate portals, and nothing of theirs ships in the public code. Please keep it that way.

## 📫 Contact

- **Email**: [htkien95@gmail.com](mailto:htkien95@gmail.com)
- **Phone / Zalo**: [+84 348 635 408](tel:+84348635408)
- **GitHub**: [@Kein95](https://github.com/Kein95)

Farewell to our teammate [@Liamlenguyen](https://github.com/Liamlenguyen). Wishing you success on the path you've chosen ✨

## 🔗 Sibling projects

- [**LUONVUITUOI-HONOR ROLL**](https://github.com/Kein95/luonvuituoi-honor-roll): config-driven student honor-roll toolkit (search, Hall of Fame, team awards, admin).
- [**LUONVUITUOI-LPR-DATAHUB**](https://github.com/Kein95/luonvuituoi-lpr-datahub): all-in-one gateway for License Plate Recognition research (16+ datasets across 10+ countries).

## 📄 License

MIT © LUONVUITUOI-CERT contributors. See [LICENSE](LICENSE).
