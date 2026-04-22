# Quickstart

From zero to a running certificate portal in five minutes.

## Prerequisites

- Python 3.11 or newer
- A PDF template with one page per (subject, result) variant — or use the `demo-academy` example, which draws one at runtime.
- A TrueType font per role you want to style (e.g. one serif, one script).

## 1. Install

Once the packages are on PyPI:

```bash
pip install luonvuitoi-cert-cli
```

Pre-PyPI (install from source — recommended while v1.0.0 is not yet published):

```bash
git clone https://github.com/Kein95/luonvuituoi-cert
cd luonvuituoi-cert
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ./packages/core -e ./packages/cli
```

Either path gives you the `lvt-cert` command. The CLI depends on the engine (`luonvuitoi-cert`), so that lands transitively.

## 2. Scaffold a project

```bash
lvt-cert init my-portal
cd my-portal
```

Answer the prompts (name, slug, locale) or pass `--non-interactive` with `--name`/`--slug`/`--locale` to skip them. The scaffolder writes:

```text
my-portal/
├── cert.config.json      # fill in rounds / subjects / layout
├── vercel.json
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── (templates/, assets/fonts/, data/ — you populate these)
```

## 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

- `JWT_SECRET` — 32+ random characters. The server refuses to issue admin tokens without this.
- `ADMIN_DEFAULT_PASSWORD` — used by one-off admin bootstrap scripts; change for real deploys.
- `PUBLIC_BASE_URL` — your deploy's HTTPS origin; pins magic-link + QR URLs.

For production you'll also want `ALLOWED_ORIGINS`, `TRUST_PROXY_HEADERS=1` (if
behind a reverse proxy), and `FORCE_HSTS=1` (after TLS cutover). See the
[security guide](security.md) for the full hardening checklist.

## 4. Add your PDF template + fonts

1. Drop your certificate template PDF into `templates/main.pdf`. Each page corresponds to one cell in `cert.config.json#results` (e.g. `G.GOLD → page 1`).
2. Drop your font TTFs into `assets/fonts/` using the filenames referenced by `cert.config.json#fonts`.

For a taste without real assets, run the demo-academy example (see [Deploy — Docker](deploy-docker.md) or the repo's `examples/demo-academy/README.md`).

## 5. Seed test data + run

```bash
lvt-cert seed --count 10 --seed 42     # writes data/students.xlsx
lvt-cert gen-keys                      # only if features.qr_verify.enabled
lvt-cert dev                           # http://127.0.0.1:5000
```

Visit:

- `/` — public student portal (search + download)
- `/admin` — admin panel (create the first admin via `luonvuitoi_cert.auth.create_admin_user`; see [Admin auth](admin-auth.md))
- `/certificate-checker` — public QR verification page

## Next

- [Architecture](architecture.md) — how the pieces fit
- [Configuration reference](config-reference.md) — every key in `cert.config.json` + env vars
- [Security guide](security.md) — hardening checklist for production
- [PDF overlay guide](pdf-overlay-guide.md) — coordinates, fonts, field positioning
- [Admin auth](admin-auth.md) — login modes + session revocation
- [Operations](operations.md) — health probe, logs, audit trail
- [Troubleshooting](troubleshooting.md) — common failure modes
- [Deploy to Vercel](deploy-vercel.md) or [Docker](deploy-docker.md)
