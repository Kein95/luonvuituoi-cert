# QR verification

Signs every downloaded certificate with an RSA-PSS-SHA256 signature, embeds a scannable QR on the PDF, and exposes a public `/certificate-checker` page that validates the signature. Gives third parties (employers, schools) confidence that a printed cert wasn't tampered with.

## Enabling

```jsonc
"features": {
  "qr_verify": {
    "enabled": true,
    "x": 720, "y": 40, "size_pt": 80,
    "max_age_seconds": 0,
    "public_key_path": "public_key.pem",
    "private_key_path": "private_key.pem"
  }
}
```

Then generate the key pair:

```bash
lvt-cert gen-keys
```

- `private_key.pem` — the signer. Never commit; treat it like a DB password.
- `public_key.pem` — safe to ship; the verifier endpoint only needs this.

## The payload

Each QR encodes a URL of the form:

```
https://mycerts.example/certificate-checker?blob=<base64url(payload)>.<base64url(signature)>
```

The payload is a canonical-JSON object:

```json
{
  "project_slug": "demo-academy",
  "round_id":     "main",
  "subject_code": "G",
  "result":       "GOLD",
  "sbd":          "12345",
  "issued_at":    1700000000
}
```

Non-sensitive fields only — a student holding the printed cert can already read all of this. The signature prevents *forgery*, not disclosure.

## Verification

`/api/verify` accepts `{"blob": "..."}` and returns:

```json
{
  "valid": true,
  "payload": {
    "project_slug": "demo-academy",
    "round_id": "main",
    "subject_code": "G",
    "result": "GOLD",
    "sbd": "12345",
    "issued_at": 1700000000
  }
}
```

On failure: `valid: false` plus a user-facing `reason` (`malformed QR payload`, `project mismatch`, `signature does not match payload`, `certificate expired`).

## Expiry

Set `max_age_seconds` to a non-zero value if you want certs to stop verifying after a while — a poor-man's revocation that saves you from running a revocation list:

```json
"max_age_seconds": 31536000
```

= 1 year. Requests older than that are rejected as expired. Also rejects payloads dated more than 60 seconds in the future (clock skew guard).

## Project-slug binding

`payload.project_slug` is compared against `config.project.slug` **before** the signature is verified. If two portals accidentally share a public key, a cert minted for portal A won't validate against portal B — the project_slug mismatch fails early.

## No Fernet / encryption layer

The QR payload is not encrypted. Earlier in-house portals layered Fernet on top for "defense in depth," but the threat model doesn't justify it: there's no secret data in the payload. Signature alone is sufficient for tamper detection, and we skip the complexity. If your payload ever carries sensitive fields, add your own encryption at the handler layer.

## Operational notes

- Keys are reloaded from disk on every verify request (no in-memory cache). Cold-start cost is ~10 ms — acceptable.
- `render_qr_png` caps QR text at 2000 chars. A signed payload + URL wrapper typically lands ~500 chars.
- The renderer stays crypto-agnostic — the download handler does the signing + PNG generation and passes bytes to the engine via `OverlayRequest.qr_png_bytes`.

## Testing

```bash
pytest -m e2e packages/core/tests/e2e/test_portal_flow.py::test_download_emits_pdf_with_qr_and_verifies
```

Signs a payload directly, embeds it in the downloaded PDF, extracts the blob, round-trips through `/api/verify`, and asserts `valid: true`.
