# Architecture

A high-level map of the system so you can predict where to look for a given concern.

## One-diagram view

```mermaid
flowchart LR
    Config[cert.config.json] -->|loaded at startup| Engine
    subgraph Engine [Python package]
        API[api/<br/>pure handlers]
        Auth[auth/<br/>JWT + OTP + ML]
        QR[qr/<br/>RSA-PSS signer]
        PDF[engine/<br/>reportlab + pypdf]
        Storage[storage/kv/<br/>+ sqlite_schema]
    end
    Flask[Flask dev server<br/>cli/server/app.py] -->|wraps| API
    Vercel[api/*.py<br/>serverless handler] -->|wraps| API
    API --> Auth
    API --> QR
    API --> PDF
    API --> Storage
    Storage --> SQLite[(SQLite<br/>students + audit + admins)]
    Storage --> KV[(KV backend<br/>local / Upstash / Vercel)]
    Students((public)) -->|CAPTCHA + rate-limit| Flask
    Admins((admin)) -->|JWT + body| Flask

    style Config fill:#fbbf24,stroke:#d97706,color:#0f172a
    style Engine fill:#0d6e6e,stroke:#0a5757,color:#fff
    style API fill:#14b8a6,stroke:#0d6e6e,color:#fff
```

## Package layout

```text
packages/
├── core/luonvuitoi_cert/
│   ├── api/          # handlers — pure functions, no Flask
│   │   ├── search.py, download.py, verify.py, shipment.py
│   │   ├── admin_update.py, captcha.py
│   │   ├── rate_limiter.py, security.py
│   ├── auth/         # tokens, passwords, OTP, magic link, activity log
│   ├── qr/           # signer + canonical-JSON codec + payload model
│   ├── engine/       # PDF overlay + font registry
│   ├── config/       # Pydantic models + loader
│   ├── storage/kv/   # local / Upstash / Vercel-KV adapters
│   ├── storage/sqlite_schema.py
│   ├── shipment/     # per-round shipment repository
│   ├── ingest/       # CSV / Excel / JSON readers
│   ├── locale/       # en + vi strings
│   ├── ui/           # jinja page renderers
│   └── templates/    # base / index / admin / certificate-checker .html.j2
└── cli/luonvuitoi_cert_cli/
    ├── server/app.py # Flask shim around the api/ handlers
    ├── scaffolds/    # templates for `lvt-cert init`
    └── commands/     # init, seed, gen-keys, dev
```

Everything in `luonvuitoi_cert.api` is a **plain function** that takes config + DB path + KV + params and returns a dataclass. Flask (dev) and the Vercel entrypoint (prod) are thin wrappers. This is the golden rule: **no Flask imports in `luonvuitoi_cert.*`**.

## Request flow — public search

```mermaid
sequenceDiagram
    participant Browser
    participant Flask
    participant Handler as search_student
    participant KV
    participant DB as SQLite

    Browser->>Flask: POST /api/search {sbd, name, dob, captcha_id, answer}
    Flask->>Flask: validate size ≤ 32 KB
    Flask->>Handler: search_student(config, db, kv, params, client_id)
    Handler->>KV: consume(captcha:<id>) — atomic
    KV-->>Handler: ok / miss
    Handler->>KV: check_rate_limit(search, client_id, 20/60s)
    Handler->>DB: SELECT across rounds (capped at 20)
    DB-->>Handler: rows
    Handler-->>Flask: SearchResult
    Flask-->>Browser: 200 {sbd, name, certificates[]}
```

Rate limit comes **after** CAPTCHA on purpose — a user typo shouldn't burn their quota.

## Request flow — admin sign-out + revocation

```mermaid
sequenceDiagram
    participant Browser
    participant Flask
    participant Revoke as revoke_admin_token
    participant Verify as verify_admin_token
    participant KV

    Browser->>Flask: POST /api/admin/logout {token}
    Flask->>Revoke: revoke_admin_token(kv, token)
    Revoke->>Verify: decode (kv=None, skip denylist)
    Verify-->>Revoke: AdminToken{jti, exp}
    Revoke->>KV: set("jwt_denylist:<jti>", "1", ttl=exp-now)
    Revoke-->>Flask: jti
    Flask-->>Browser: 200 {revoked: true, jti}

    Note over Browser,KV: later request with the same token…
    Browser->>Flask: POST /api/admin/search {token}
    Flask->>Verify: verify_admin_token(token, kv=kv)
    Verify->>KV: get("jwt_denylist:<jti>")
    KV-->>Verify: "1"
    Verify-->>Flask: raise TokenError("revoked")
    Flask-->>Browser: 401
```

## Data model

```mermaid
erDiagram
    STUDENTS ||--o{ SHIPMENTS : has
    STUDENTS {
        text sbd PK
        text full_name
        text dob
        text school
        text phone
        text result
        text extra_col_1
    }
    SHIPMENTS {
        int id PK
        text sbd FK
        text round_id
        text status
        text tracking_number
        text created_at
        text updated_at
    }
    ADMIN_USERS {
        text id PK
        text email UK
        text password_hash
        text role
        int is_active
        text created_at
    }
    ADMIN_ACTIVITY {
        text id PK
        text timestamp
        text user_id
        text user_email
        text action
        text target_id
        text metadata
        text ip
    }
```

- **One SQLite file per project** — students + admins + audit live together, because the whole point is "config + data dir = entire deployment."
- **Students table name is per-round** (`rounds[].table`), so the config can model "qualifier" vs "finals" as parallel tables with the same schema.
- **No foreign-key enforcement** — config-author is trusted; we validate identifiers at load time.

## KV usage

| Key prefix | Purpose | TTL |
|------------|---------|-----|
| `rl:<scope>:<ip>:<window>` | Rate-limit counters | 2× window_seconds |
| `captcha:<id>` | Pending challenges | 5 min |
| `otp:<email>` | OTP hashes (atomic consume) | 5 min |
| `magic:<hash>` | Magic-link tokens | 15 min |
| `jwt_denylist:<jti>` | Revoked admin sessions (M7) | matches token remaining-life |

All writes either `set(ttl)` or `consume()` — no orphan keys, no cron.

## Design axes

- **Config-driven, not code-driven.** Adding a new project = new `cert.config.json` + template + data. Zero Python.
- **Stateless handlers.** Any handler in `luonvuitoi_cert.api` can be moved behind a different transport (AWS Lambda, Cloud Functions) with a one-line wrapper.
- **KV is the synchronization primitive.** Nothing shares in-process state — workers scale horizontally by sharing KV and SQLite.
- **Fail loud, not silent.** Missing `JWT_SECRET`, unknown config keys, non-HTTPS webhook URLs — every one raises or logs a warning at startup. Production surprises are debt.

## Where to go next

- [Operations](operations.md) — health probe, logs, audit
- [Security](security.md) — user-facing hardening checklist
- [Configuration reference](config-reference.md) — every config key
- [Admin auth](admin-auth.md) — login flows + revocation
- [PDF overlay guide](pdf-overlay-guide.md) — coordinate measurement + fonts
