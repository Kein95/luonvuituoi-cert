---
hide:
  - navigation
  - toc
---

<p class="lvt-credits">🧭 Mentor <a href="https://github.com/duongtruongbinh" target="_blank" rel="noopener">@duongtruongbinh</a> &nbsp;·&nbsp; 🤝 Teammate <a href="https://github.com/Liamlenguyen" target="_blank" rel="noopener">@Liamlenguyen</a> — stay tuned for more collabs from <strong>LUONVUITUOI TEAM</strong> ✨<br>
📧 <a href="mailto:htkien95@gmail.com">htkien95@gmail.com</a> &nbsp;·&nbsp; 📱 <a href="tel:+84348635408">+84 348 635 408</a></p>

<div class="lvt-hero" markdown>

<img src="assets/logo.svg" alt="LUONVUITUOI-CERT logo" class="lvt-hero-logo">

# LUONVUITUOI-CERT

<p class="lvt-hero-tagline">
Config-driven certificate portal toolkit. Bring your PDF template and student list — get a full portal with search, download, admin panel, and QR verification in minutes.
</p>

<div class="lvt-cta-row">
  <a href="quickstart/" class="lvt-btn lvt-btn-primary">🚀 Quickstart (10 min)</a>
  <a href="https://github.com/Kein95/luonvuituoi-cert" class="lvt-btn lvt-btn-ghost" target="_blank" rel="noopener">⭐ View on GitHub</a>
</div>

<div class="lvt-badges">
  <img src="https://img.shields.io/github/v/release/Kein95/luonvuituoi-cert?style=flat-square&color=0d6e6e&label=release" alt="release">
  <img src="https://img.shields.io/github/license/Kein95/luonvuituoi-cert?style=flat-square&color=0d6e6e" alt="license">
  <img src="https://img.shields.io/github/actions/workflow/status/Kein95/luonvuituoi-cert/test.yml?style=flat-square&color=0d6e6e&label=tests" alt="tests">
  <img src="https://img.shields.io/github/stars/Kein95/luonvuituoi-cert?style=flat-square&color=fbbf24" alt="stars">
</div>

</div>

## Why this exists

Running a competition, awarding diplomas to a cohort, issuing completion certificates? You typically need a public lookup page, an admin backend, and a verification endpoint — all wired together correctly. **LUONVUITUOI-CERT gives you all three**, deployable to Vercel's free tier or any Docker host, with zero boilerplate.

<div class="lvt-features" markdown>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🎨</span>
### Bring your own template
Drop in a PDF + coordinates file. The engine overlays student names, dates, and QR codes pixel-perfect — no redesign required.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🔍</span>
### Public lookup portal
Recipients search by name or ID, preview their certificate, download signed PDF. Mobile-first, multilingual-ready.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🔐</span>
### Admin panel built in
Manage records, apply corrections, track shipments, audit log. Password-protected with JWT + rate limiting.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">📱</span>
### QR verification
Every certificate carries a QR code linking to a public verify page — third parties confirm authenticity in one scan.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">⚡</span>
### Deploy anywhere
One-command Vercel deploy (free tier), production Dockerfile, docker-compose — pick your infra.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">📦</span>
### Config over code
Single `cert.config.json` drives everything: branding, fields, overlay coords, auth, shipment rules. No forking required.
</div>

</div>

<div class="lvt-stats" markdown>

<div class="lvt-stat">
<div class="lvt-stat-num">10min</div>
<div class="lvt-stat-label">First deploy</div>
</div>

<div class="lvt-stat">
<div class="lvt-stat-num">0</div>
<div class="lvt-stat-label">Boilerplate code</div>
</div>

<div class="lvt-stat">
<div class="lvt-stat-num">$0</div>
<div class="lvt-stat-label">Vercel free tier</div>
</div>

<div class="lvt-stat">
<div class="lvt-stat-num">MIT</div>
<div class="lvt-stat-label">License</div>
</div>

</div>

## Architecture

```mermaid
flowchart LR
    A[cert.config.json] --> B[Python serverless API]
    B --> C[Student portal<br/>/ + /verify]
    B --> D[Admin panel<br/>/admin]
    B --> E[(SQLite<br/>students)]
    B --> F[(KV backend<br/>overrides)]
    C -.QR scan.-> G[Verify page]

    style A fill:#fbbf24,stroke:#d97706,color:#0f172a
    style B fill:#0d6e6e,stroke:#0a5757,color:#fff
    style C fill:#14b8a6,stroke:#0d6e6e,color:#fff
    style D fill:#14b8a6,stroke:#0d6e6e,color:#fff
    style G fill:#ccfbf1,stroke:#0d6e6e,color:#0a5757
```

## Next steps

<div class="lvt-features" markdown>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🚀</span>
### [Quickstart →](quickstart.md)
Deploy your first portal in 10 minutes — CLI scaffold, config tour, local run.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🏛️</span>
### [Architecture →](architecture.md)
How the pieces fit — handlers, transport, KV, signing, data model.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">⚙️</span>
### [Configuration →](config-reference.md)
Every `cert.config.json` field + environment variable documented.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🔐</span>
### [Security →](security.md)
Hardening checklist for production deploys.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🛠️</span>
### [Operations →](operations.md)
Health probe, log triage, audit trail, incident checklist.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🧭</span>
### [Troubleshooting →](troubleshooting.md)
Common failure modes and their root causes.
</div>

</div>
