# End-user guide

How to use the three surfaces a deployed portal exposes. Screenshots omitted — pages are plain, accessible HTML with no brand chrome beyond your configured CSS variables.

## Who reads this

- **Recipients** (students, participants, awardees) — section [Student portal](#student-portal).
- **Operators** (competition staff, training admins) — section [Admin panel](#admin-panel).
- **Third parties** (employers, schools, anyone verifying a certificate) — section [Certificate-Checker](#certificate-checker).

If you are a developer deploying the portal, start at [quickstart.md](quickstart.md) instead.

## Student portal

URL: `https://<your-portal>/`

### Look up your certificate

1. Pick a search mode from the dropdown. Available modes depend on the deploy's `features.student_search_modes` config; typical choices:
   - **Name + date of birth** — default for most deploys
   - **Name + registration number (SBD)** — when the organizer only issued an SBD, not a birth date
   - **SBD + phone** — when privacy rules require self-proven contact
2. Fill the form. Name matching is accent-tolerant (`Nguyễn` matches `nguyen`). DOB accepts `DD/MM/YYYY` or `YYYY-MM-DD`.
3. Solve the math CAPTCHA shown below the form. Click **Refresh** if the numbers are unreadable.
4. Press **Search**. If a match is found, the page reveals a **Download certificate** button.

### Download

Click **Download certificate**. The browser saves a PDF named `<your-name>-<round>.pdf`. If QR verification is enabled on this portal, the PDF embeds a signed QR linking to the Certificate-Checker page — anyone scanning it lands on the verify result directly.

### Troubleshooting

| Symptom | What to try |
| --- | --- |
| "Not found" but you are registered | Check name spelling (diacritics optional, but typos matter). Confirm DOB format. Try an alternate search mode if available. |
| "Too many attempts" | Wait the displayed cooldown (usually 60 s). Rate limit is per-IP + per-session; reloading the page does not reset it. |
| CAPTCHA keeps rejecting | Refresh the CAPTCHA. Each CAPTCHA is single-use; submitting twice without a refresh fails the second time. |
| Download starts but file is 0 bytes | The server rendered an error. Contact the organizer — this is a template / font issue on their side, not yours. |

## Admin panel

URL: `https://<your-portal>/admin`

Access requires an admin account. Three login modes exist; the deploy's `admin.auth_mode` decides which one you see:

- **password** — email + password you were assigned. Default super-admin password is set via `ADMIN_DEFAULT_PASSWORD` at first boot; change it immediately.
- **otp** — enter email, receive a 6-digit code, paste it back. Code expires in 5 minutes.
- **magic_link** — enter email, receive a one-click link. Link expires in 15 minutes and is single-use.

Sessions persist in `sessionStorage` and expire after the JWT TTL (default 8 hours). Closing the browser tab logs you out.

### Student lookup (admin mode)

Search by **SBD** (registration number) only — admin search bypasses the student-facing accent-tolerant name match. Results show every field in the record, including fields excluded from the student portal by `features.student_fields`.

### Record updates

If your role is `super-admin` or `admin` (not `viewer`), the result card exposes **Edit** on editable fields defined in `admin.editable_fields`. Updates are persisted to the KV store as overrides — the original ingest data stays untouched.

Every write is logged to the activity log (SQLite local + optional Google Sheets webhook forwarding). You cannot delete log entries from the UI.

### Shipment tracking

If `features.shipment.enabled` is true, the admin panel shows a shipment form:

1. Enter SBD, status (from the configured list, e.g. `packed` / `in_transit` / `delivered`), and any extra fields the config maps (`tracking_number`, `carrier`, `notes`, …).
2. Submit. The record upserts — same SBD + round updates the existing row.

Recipients then look up shipment status on the student portal (if `features.shipment.public_fields` exposes the relevant columns) via the same CAPTCHA-protected lookup.

### Sign out

Click **Sign out** in the header. The JWT is cleared from `sessionStorage` and a server-side token revocation is recorded. Even if someone copies the token, subsequent requests fail.

## Certificate-Checker

URL: `https://<your-portal>/certificate-checker`

### Verify a QR blob

Three ways to land on this page:

1. **Scan the QR** on a printed certificate → URL opens with `?blob=<...>` pre-filled → page auto-submits → verdict shows immediately.
2. **Click the QR link** in the digital PDF → same auto-submit flow.
3. **Paste the blob manually** — useful when the recipient sent you just the blob string (e.g. via email). Paste into the textarea, click **Verify**.

### Reading the verdict

- **Valid** (green badge) — signature verifies against the portal's public key, the payload is structurally correct, and if a TTL was configured (`features.qr_verify.max_age_seconds`), the certificate has not expired. Below the badge: the recipient name, round, result, and issue date.
- **Tampered** (red badge) — signature does not verify. Either the QR was altered, the blob was corrupted in transit, or the certificate was signed by a different portal. Do not accept the certificate as genuine.
- **Expired** (amber badge) — signature is valid but the TTL has elapsed. The certificate was genuine but the organizer flagged it as short-lived (e.g. scholarship offers). Ask the recipient for a fresh copy.

### What the checker does NOT do

- It does not hit the portal's student database. Verification is purely cryptographic: the public key embedded in the page validates the signature. You can verify a blob offline once the page has loaded.
- It does not confirm the recipient's current status (enrolled, graduated, revoked). The QR was a snapshot at issue time.
- It does not reveal any data beyond what was signed into the payload — typically just name + round + result + issue date. Private fields (DOB, phone, email) are never in the QR.

## Privacy notes for recipients

- The CAPTCHA, OTP, and magic-link tokens are single-use. If you submit a form twice, the second submission will fail — this is intentional.
- Your search queries are rate-limited per-IP. The portal logs search attempts (not the content of the search) for abuse detection.
- The QR on your certificate contains only the fields the organizer chose to sign. It is signed, not encrypted — anyone can read the fields by decoding the blob. If you do not want a field to be publicly readable from the QR, ask the organizer to exclude it from `features.qr_verify.payload_fields`.

## Report issues

Found a bug in the portal behavior? Contact the organizer. If you are the organizer and suspect a bug in the toolkit itself, see the `SECURITY.md` file at the repo root for the threat-model contact, or open an issue at the repo.
