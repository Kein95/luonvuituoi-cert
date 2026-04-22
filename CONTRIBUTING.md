# Contributing to LUONVUITUOI-CERT

Thanks for taking an interest. This project is a small-surface toolkit; the bar for new features is "would I want this in my own deploy tomorrow?" If yes, read on.

## Dev setup

```bash
git clone https://github.com/luonvuitoi/cert
cd cert
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ./packages/core[dev] -e ./packages/cli
```

Run the full suite:

```bash
export JWT_SECRET=pytest-default-secret-padded-32-bytes-min
pytest -ra
```

Run only the fast unit tests:

```bash
pytest -m "not e2e"
```

Lint:

```bash
ruff check packages scripts
ruff format --check packages scripts
```

Re-export the JSON schema after editing `luonvuitoi_cert/config/models.py`:

```bash
python scripts/export_schema.py
```

The `test_schema_export` test fails if you forget.

## Zero-leak policy

This repo was extracted from three internal exam-certificate portals. Nothing in the public source may be traceable to them. Specifically:

- Don't copy strings verbatim from private codebases — reword to generic language.
- Don't ship PDFs, fonts, data files, or real student records.
- Config samples should use fabricated names like "DEMO ACADEMY," "demo-award," "Science / Math / English."
- If a feature was motivated by a private issue, describe it in your PR without naming the source portal.

CI (`build-examples` + `test_example_demo_academy`) greps for the private portals' short names and fails if they land in tracked files.

## Pull requests

Before opening a PR:

- All tests pass locally.
- `ruff check` and `ruff format --check` clean.
- If you touched `models.py`, re-ran `scripts/export_schema.py` and committed the new `cert.schema.json`.
- If you added a feature, there's a regression test for the happy path + one adversarial input.
- PR description mentions the threat model consideration for any endpoint-touching change (see `SECURITY.md`).

Keep PRs focused. One behavioral change per PR, one commit if possible. Use conventional-commit prefixes: `feat:`, `fix:`, `test:`, `docs:`, `ci:`, `chore:`.

## Architectural guardrails

- **Pure handlers.** Everything under `luonvuitoi_cert.api` is a plain function; transport (Flask/Vercel) wraps without adding logic. Don't add Flask imports to `luonvuitoi_cert.*`.
- **Config is the single source of truth.** No hardcoded project name / subject / round / status string should leak into the engine or handlers.
- **Atomic KV primitives.** Anything that "needs to be single-use" (CAPTCHA, OTP, magic link) must go through `kv.consume()`, not `get + delete`.
- **SQL identifiers are validated.** Any string that ends up interpolated into SQL (column name, table name) must pass through `_SQL_IDENT` at config time.
- **Secrets never leak into errors.** When wrapping exceptions, strip raw input; log the detail to the stdlib `logging` module for operators.

## What a "no" looks like

Features we've deliberately declined:

- QR payload encryption. Payload is non-sensitive; signature alone prevents forgery.
- Playwright browser tests. httpx gives equivalent coverage for the JS-free API surface.
- A per-endpoint file layout for the Vercel handler. One `api/index.py` dispatches everything — fewer cold starts, less duplication.
- A CAPTCHA vendor SDK (hCaptcha / Turnstile). Math CAPTCHA covers the scrape-bot threat without adding a dependency; vendors are a PR away if your threat model demands them.

## Releasing

Maintainers only:

1. Update `CHANGELOG.md` under a new version heading.
2. Bump `version` in `packages/core/pyproject.toml` and `packages/cli/pyproject.toml`; bump `__version__` in both `__init__.py`s.
3. `git tag vX.Y.Z` and push the tag.
4. CI builds wheels; a release workflow publishes to PyPI (manually trigger until we add a trusted-publisher action).
5. GitHub Pages docs update automatically on `main` push.

## License

MIT. By contributing you agree your changes are licensed the same way.
