# LUONVUITUOI-CERT

**Config-driven certificate portal toolkit** — bring your own PDF template + student list, get a full portal with search, download, admin panel, and QR verification page.

## Why?

Running a competition, awarding certificates to a cohort, or issuing completion diplomas? You typically need:

- A public page where recipients look up and download their personalized PDF
- An admin backend to manage records, corrections, shipments
- A verification page so third parties (employers, schools) can confirm a certificate is genuine

LUONVUITUOI-CERT gives you all three, deployable to Vercel's free tier or a Docker host, with zero boilerplate.

## Architecture

```text
         ┌──────────────────┐
         │  cert.config.json│  ← you write this
         └────────┬─────────┘
                  │
      ┌───────────┴───────────┐
      │                       │
      ▼                       ▼
  Student portal         Admin panel
  (/ + /verify)          (/admin)
      │                       │
      └───────────┬───────────┘
                  ▼
         Python serverless API
                  │
           ┌──────┴──────┐
           ▼             ▼
        SQLite       KV backend
     (students)    (overrides)
```

## Next steps

- [Quickstart](quickstart.md) — deploy your first portal in 10 minutes
- [Configuration reference](config-reference.md) — every `cert.config.json` field
- [PDF overlay guide](pdf-overlay-guide.md) — designing your template + coordinates
