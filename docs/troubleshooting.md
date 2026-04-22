# Troubleshooting

Common failure modes and their root causes. Organized by symptom, not by subsystem.

## "Admin login returns 200 but I never receive the email"

**Cause**: `RESEND_API_KEY` (or `CERT_EMAIL_FROM`) is missing. The app falls back to `NullEmailProvider` and silently swallows messages. Startup logs:

```
RESEND_API_KEY not set — OTP / magic-link emails will be swallowed.
```

**Fix**: Set both env vars:

```bash
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxx
CERT_EMAIL_FROM=no-reply@yourdomain.com  # must be a verified Resend sender
```

Restart the container/serverless function.

## "All clients share one rate-limit bucket" (everyone gets 429)

**Cause**: Deploy is behind a proxy (Nginx, Caddy, Vercel), but `TRUST_PROXY_HEADERS` is not set, so the app keys the rate limiter off the proxy's IP (always 127.0.0.1 or the LB IP).

**Fix**:

```bash
TRUST_PROXY_HEADERS=1
```

**Counter-cause**: `TRUST_PROXY_HEADERS=1` on a **direct** bind (no proxy in front). Clients can forge `X-Forwarded-For` and bypass the limiter.

**Fix**: Leave at `0` unless a trusted proxy overwrites the header.

## "Browser refuses CORS requests to /api/*"

**Cause**: `ALLOWED_ORIGINS` doesn't include the front-end origin.

**Check**:

```bash
curl -H "Origin: https://myapp.example" -I https://mycerts.example/api/captcha
# Look for: Access-Control-Allow-Origin: https://myapp.example
```

If missing, the origin isn't on the whitelist.

**Fix**:

```bash
ALLOWED_ORIGINS=https://myapp.example,https://admin.mycerts.example
```

Default is `*`, which echoes every origin. Restrict only when you know your front-end domain.

## "Docker healthcheck reports unhealthy"

**Cause**: Old deploy probing `POST /api/captcha` (pre-P2). That endpoint is now rate-limited and writes KV state — a probe every 30s quickly fills the captcha rate bucket and `429`s itself.

**Fix**: The current Dockerfile already uses `GET /health`. If you've extended it, make sure your probe points at `/health`, not `/api/captcha`.

## "KV writes are flaky on Docker with >1 worker"

**Cause**: `KV_BACKEND=local` + `WEB_CONCURRENCY > 1`. The local file KV only syncs inside one process; two workers race on the read-modify-write cycle and lose writes.

**Startup warning**:

```
KV_BACKEND=local with 2 workers is unsafe — concurrent reads can lose writes.
```

**Fix**: Pick one:

- Drop to a single worker: `WEB_CONCURRENCY=1`
- Switch to a shared backend: `KV_BACKEND=upstash` + set `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN`

## "Magic-link email carries the wrong origin"

**Cause**: `PUBLIC_BASE_URL` not set (or wrong). The fallback uses `request.host_url`, which echoes whatever Host header the client sent — an attacker can poison the email with their own domain.

**Fix**:

```bash
PUBLIC_BASE_URL=https://mycerts.example  # exact HTTPS origin, no trailing slash
```

## "Admin session won't log out — JWT still works after `/api/admin/logout`"

**Cause**: The route that's still accepting the token doesn't pass `kv` to `verify_admin_token`. Revocation is opt-in per endpoint.

**Check** which routes enforce revocation in this repo:

- `/api/admin/search` ✓
- `/api/shipment/upsert` ✓

Custom transport code (Vercel shim, embedded usage) must pass `kv=` to `verify_admin_token` for the denylist to apply.

**Alternative fix**: Rotate `JWT_SECRET` — invalidates every session, all admins need to log back in.

## "The mkdocs build fails in CI"

**Cause 1**: Broken internal link. `--strict` mode fails the build on any unresolved page reference.

**Fix**: `mkdocs build --strict` locally, follow the error message.

**Cause 2**: New page not added to `nav` in `mkdocs.yml`. Orphan pages trigger a warning → `--strict` fails.

**Fix**: Add the page under the appropriate `nav` section.

## "QR verify always says invalid"

**Causes** (in order of likelihood):

1. **Wrong `public_key.pem`**. The verifier was given a key that doesn't match the signer. Check `sha256sum public_key.pem` on both ends.
2. **Project slug mismatch**. QR payload binds to `project.slug` — a cert signed for `demo-2025` won't validate against a config with `slug: demo-2026`.
3. **Clock skew beyond tolerance**. Payload signatures accept ±60s. If the verifying host's clock is more than 60s off, every request fails.
4. **`max_age_seconds` triggered**. If `features.qr_verify.max_age_seconds` is non-zero, certs older than that are rejected regardless of signature.

## "`test_search_rate_limit_kicks_in` fails in CI"

Already fixed — the test now loops with headroom to survive a window-boundary rollover. If it's still failing, the fixed-window rate limiter may have been replaced without updating the test. Check the loop bound (should be ≥ `2 × STUDENT_RATE_LIMIT`).

## "Pydantic rejects my config with `rounds: List should have at most 20 items`"

Intentional. `rounds` is capped at 20 (H3 from the 2026-04-22 eval) so public search can't fan out an unbounded query count.

**Fix**: If you genuinely need >20 rounds, split into multiple portals (different `project.slug`) or raise the cap in `packages/core/luonvuitoi_cert/config/models.py` after thinking through the worst-case query cost.

## "Dependabot opens a PR every week"

Working as intended — weekly pip / monthly actions+docker. Merge promptly; `reportlab`, `pypdf`, `cryptography` are supply-chain-sensitive. If you want a quieter cadence, edit `.github/dependabot.yml` (`schedule.interval`).

## Still stuck?

- Check the [operations](operations.md) page for log-message triage.
- File an issue with the startup log, `mkdocs.yml` changes, env var list (with secrets redacted), and the exact request that fails.
