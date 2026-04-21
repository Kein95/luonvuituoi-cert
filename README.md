# LUONVUITUOI-CERT

> Config-driven certificate portal toolkit — build your own certificate distribution + QR verification website in minutes.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## What is it?

A batteries-included toolkit for organizations (schools, competitions, training centers) who need to:

- Let students **search and download their personalized certificate PDF** (auto-overlay of name/school/grade onto a pre-designed template)
- Provide a **public QR verification page** so anyone holding a printed certificate can check authenticity
- Manage students, shipments, and access via a **multi-user admin panel**
- Deploy to **Vercel serverless** (free tier) or **Docker** (self-host)

No coding required for the basics — just prepare a PDF template, an Excel/CSV of students, and a `cert.config.json`.

## Features

- Student portal: search by name+DOB+CAPTCHA or name+ID+CAPTCHA
- Certificate download: dynamic PDF overlay (name, school, grade, subject)
- **Certificate-Checker page**: public QR scan → Fernet decrypt + RSA signature verify
- Multi-user admin: RBAC (super-admin / admin / viewer), JWT, 3 auth modes (password / OTP email / magic-link)
- Shipment tracking: config-driven statuses and fields
- Activity log: SQLite local + optional Google Sheets webhook
- Rate limiting + CAPTCHA + security headers
- i18n: English + Vietnamese out-of-the-box, extensible
- Config-mapped DB: import Excel/CSV/Google Sheets/JSON with your own column names

## Quickstart

```bash
pip install luonvuitoi-cert-cli
lvt-cert init my-award
cd my-award
lvt-cert gen-keys          # QR signing keys
lvt-cert seed              # Generate 10 fake students
lvt-cert dev               # Local Flask server at http://localhost:5000
```

Deploy to Vercel:

```bash
vercel deploy
```

Full docs: **https://luonvuitoi.github.io/cert**

## Repo Layout

```text
packages/
  core/               # luonvuitoi-cert — engine + handlers + templates
  cli/                # luonvuitoi-cert-cli — lvt-cert scaffolder
examples/
  demo-academy/       # 10 fake students, custom PDF, full-feature demo
docs/                 # MkDocs Material
```

## Status

Alpha — v0.1.0. See [plan.md](https://github.com/luonvuitoi/cert/blob/main/PLAN.md) for roadmap.

## License

MIT © LUONVUITUOI-CERT contributors
