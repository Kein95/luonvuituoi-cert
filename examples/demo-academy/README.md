# demo-academy

A full-feature LUONVUITUOI-CERT example: QR verification + shipment tracking + multi-role admin, all wired against a generated two-page certificate template and 10 Faker-invented students.

The repository deliberately does not ship binary PDFs or licensed font files. Running `prepare_demo.py` bootstraps the local copies from Apache-2.0 fonts bundled with ReportLab and a reproducible template drawn at script time.

## Setup

```bash
cd examples/demo-academy
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ../../packages/core -e ../../packages/cli
python prepare_demo.py
cp .env.example .env                                  # edit JWT_SECRET + ADMIN_DEFAULT_PASSWORD
lvt-cert gen-keys                                     # RSA keypair for QR signing
lvt-cert dev                                          # http://127.0.0.1:5000
```

After `prepare_demo.py` runs, the layout is:

```
demo-academy/
├── cert.config.json
├── prepare_demo.py
├── templates/main.pdf         # 2-page GOLD / SILVER template drawn by reportlab
├── assets/fonts/{serif,script}.ttf   # Bitstream Vera copies (Apache-2.0)
├── data/students.xlsx         # 10 fake students, seed=42 so reproducible
├── private_key.pem            # from gen-keys — do not commit
└── public_key.pem             # safe to ship
```

## What you can exercise

- **Student portal** (`/`): enter a name + DOB + SBD from `data/students.xlsx`, solve the math CAPTCHA, download a PDF.
- **Certificate-Checker** (`/certificate-checker`): scan the QR printed onto the downloaded PDF (or open the URL it encodes) to confirm authenticity.
- **Admin panel** (`/admin`): sign in with an account you create via `python -c "from luonvuitoi_cert.auth import create_admin_user, Role; create_admin_user('data/students.db', email='you@demo', role=Role.SUPER_ADMIN, password='hunter2')"`, then use SBD search + shipment upsert.

## Zero-leak note

Nothing here references the internal exam portals this toolkit was extracted from. Subject codes, round names, fonts, and student data are all invented.
