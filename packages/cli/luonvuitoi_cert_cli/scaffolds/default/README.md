# {{ project_name }}

A certificate portal scaffolded by [`lvt-cert init`](https://github.com/luonvuitoi/cert).

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in JWT_SECRET + ADMIN_DEFAULT_PASSWORD
lvt-cert gen-keys           # RSA keypair for QR signing (only needed if QR is enabled)
lvt-cert seed               # generate 10 fake students into data/students.xlsx
lvt-cert dev                # local dev server at http://localhost:5000
```

## Structure

- `cert.config.json` — the single source of truth (project name, rounds, subjects, layout, features).
- `templates/` — your certificate PDF template(s). Each page corresponds to one (subject, result) cell per `cert.config.json#results`.
- `assets/fonts/` — TrueType fonts referenced by `cert.config.json#fonts`.
- `data/` — SQLite + ingested Excel data lives here.
- `api/` — Vercel-compatible serverless entrypoints (see the deploy guide).

## Next steps

- Add your certificate template to `templates/` and update `cert.config.json#rounds[*].pdf` + `layout.fields` coordinates.
- Ingest your real student Excel: `lvt-cert seed --from-excel path/to/your.xlsx` (coming in Phase 12; for now use the generic ingest helper from the Python package).
- Deploy: `vercel deploy` (after customizing `vercel.json`) or build the Docker image.
