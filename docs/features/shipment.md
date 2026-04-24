# Shipment tracking

Opt-in table for tracking physical delivery of certificates. Admins upsert records; students look up the status of their own.

## Enabling

```jsonc
"features": {
  "shipment": {
    "enabled": true,
    "statuses": ["pending", "packed", "shipped", "delivered", "returned"],
    "fields":   ["tracking_code", "carrier", "shipped_at", "note"],
    "public_fields": ["carrier"]
  }
}
```

- `statuses` — the allowed values for the `status` column. Must be non-empty and case-insensitive-unique.
- `fields` — extra TEXT columns on the `shipments` table. Each must be a SQL identifier. Reserved names (`id`, `round_id`, `sbd`, `status`, `created_at`, `updated_at`) are rejected to avoid collisions with the fixed schema.
- `public_fields` — subset of `fields` that the public lookup endpoint is allowed to return. **Default empty.** Students see only `status` and `updated_at` unless you allowlist more.

## Table layout

`shipments`:

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID. |
| `round_id` | TEXT | From your rounds list. |
| `sbd` | TEXT | Student's registration number. |
| `status` | TEXT | One of `features.shipment.statuses`. |
| `created_at` / `updated_at` | TEXT | ISO 8601 UTC. |
| …`fields[]` | TEXT | Your declared extras. |
| `UNIQUE(round_id, sbd)` | | Composite key — one row per cert per student. |

## Admin API

`POST /api/shipment/upsert` (requires JWT; viewer role rejected):

```json
{
  "token": "<admin JWT>",
  "sbd": "12345",
  "round_id": "main",
  "status": "shipped",
  "updates": { "tracking_code": "VN123", "carrier": "GHN" }
}
```

Uses SQLite's `INSERT ... ON CONFLICT DO UPDATE` so two admins pressing Save on the same row simultaneously don't race into `IntegrityError`. Patch semantics on conflict: only caller-supplied fields overwrite; untouched columns keep their prior values.

Activity log records `shipment.upsert` with `status` + `fields_touched` (the list of keys, **not** their values — keeps tracking codes and addresses out of the webhook stream).

## Public lookup

`POST /api/shipment/lookup`:

```json
{
  "sbd": "12345",
  "round_id": "main",
  "captcha_id": "...",
  "captcha_answer": 8
}
```

Goes through the same CAPTCHA + rate-limit gate as student search. Response shape:

```json
{
  "status": "shipped",
  "updated_at": "2026-04-20T11:23:00Z",
  "fields": { "carrier": "GHN" }
}
```

`fields` carries only keys in `features.shipment.public_fields`. `id`, `created_at`, and other internals are not exposed.

## Status discipline

`upsert_shipment` validates `status` against the configured list before writing. A typo in the admin UI surfaces as a 400 with a listing of the allowed values.

## Listing shipments

`list_shipments(db, config, status=..., round_id=..., limit=200)` returns the most recent N (capped at `MAX_LIST_LIMIT = 500`) sorted by `updated_at DESC`. The admin panel uses this for the "shipments" tab (Phase 10+).

## Feature flag guards

All three entry points (`upsert_shipment_record`, `lookup_shipment`, `build_shipment_schema`) raise if `features.shipment.enabled` is false — you can toggle the feature off without dropping the table.

## Migration note

Adding a new entry to `features.shipment.fields` works on an existing database — SQLite's dynamic typing is forgiving enough that the `CREATE TABLE IF NOT EXISTS` approach doesn't alter the existing schema. If you need to add columns to a populated DB, use `ALTER TABLE` manually; there's no migration framework.

## Draft → export → ship → import lifecycle

Full shipping workflow has four states: `draft` → `exported` → `in_transit` (via import) → `delivered/failed`. Admins curate drafts, hit **export** to produce a carrier-ready Excel + hard-lock the batch, upload to the carrier portal, and let the bulk-import pipeline close the loop when tracking data comes back.

### Draft table

A dedicated `shipment_draft` table is created on first use. PK: `(round_id, sbd, status)` — one active draft per student per round. Status values:

- `draft` — admin added, editable, not yet exported
- `exported` — included in an export batch; HARD-LOCKED (cannot edit; cancel only)
- `cancelled` — voided before or after export
- `promoted` — a carrier tracking code matched this draft; see `shipment_history` for live status

### Add drafts

```bash
# By column value
lvt-cert shipment draft add --round main --filter ship_method=CA_NHAN --token $TOK

# By result tier (matches any subject column carrying the result)
lvt-cert shipment draft add --round main --result GOLD --token $TOK

# From an Excel/CSV with SBDs in column 1
lvt-cert shipment draft add --round main --from-file ships.xlsx --token $TOK

# Combined
lvt-cert shipment draft add --round main \
    --filter ship_method=CA_NHAN --result GOLD --token $TOK
```

At least one of `--filter`, `--result`, `--from-file` is required — no accidental full-round targeting.

### List / cancel

```bash
lvt-cert shipment draft list --round main --status draft
lvt-cert shipment draft cancel <draft-id-1> <draft-id-2>
```

### Export

Carrier profiles need an `export_template` block:

```jsonc
"viettel": {
  "column_mapping": { ... },   // as before (import)
  "success_keywords": [ ... ],
  "export_template": {
    "sbd": "Mã học viên",
    "full_name": "Họ tên",
    "phone": "SĐT",
    "address": "Địa chỉ nhận",
    "recipient": "Người nhận"
  }
}
```

Run:

```bash
lvt-cert shipment export --round main --carrier viettel \
    -o orders-thang-4.xlsx --token $TOK
```

Produces an Excel file with headers from the template; `address` and `recipient` columns start empty so admins can fill in before uploading to the carrier portal.

**Hard lock**: after export, the participating drafts flip to `exported` and cannot be edited. If admin catches a mistake, `draft cancel` is the only way out — carrier-side void is manual.

### API endpoints (same behaviors)

```bash
# Add
curl -X POST -H "Content-Type: application/json" \
     -d '{"token":"...","round_id":"main","filters":{"ship_method":"CA_NHAN"}}' \
     https://mycerts.example/api/admin/shipments/draft

# List
curl -X POST -H "Content-Type: application/json" \
     -d '{"token":"...","round_id":"main","status":"draft"}' \
     https://mycerts.example/api/admin/shipments/draft/list

# Cancel
curl -X POST -H "Content-Type: application/json" \
     -d '{"token":"...","ids":["<id1>","<id2>"]}' \
     https://mycerts.example/api/admin/shipments/draft/cancel

# Export (downloads xlsx)
curl -X POST -H "Content-Type: application/json" \
     -d '{"token":"...","round_id":"main","carrier":"viettel"}' \
     https://mycerts.example/api/admin/shipments/export -o orders.xlsx
```

### Promotion hook

When the carrier returns tracking data and admin runs `lvt-cert import-shipments ... --commit`, the import pipeline looks up each inserted row's `(round_id, sbd)` against `shipment_draft` — any `exported` draft matching gets flipped to `promoted` with the new `tracking_code` stamped. This closes the state-machine loop.

## Bulk import from carrier Excel/CSV

Carriers (Viettel Post, GHN, GHTK, …) hand operators monthly delivery exports. The `lvt-cert import-shipments` CLI and the `POST /api/admin/shipments/import` endpoint parse those files via per-carrier profiles and write rows into a dedicated `shipment_history` table (PK `(round_id, sbd, tracking_code)` — every attempt kept for audit).

### Config

Add to `cert.config.json#features.shipment`:

```jsonc
"import": {
  "default": "viettel",
  "profiles": {
    "viettel": {
      "column_mapping": {
        "tracking_code": ["Mã vận đơn", "Tracking"],
        "phone":         ["SĐT", "Phone"],
        "status":        ["Trạng thái", "Status"],
        "sent_at":       ["Ngày gửi"],
        "address":       ["Địa chỉ"],
        "recipient":     ["Người nhận"]
      },
      "success_keywords":    ["GIAO THÀNH CÔNG", "PHÁT THÀNH CÔNG"],
      "skip_status_prefixes": ["CH"],
      "header_row": 0
    },
    "ghn": {
      "column_mapping": {
        "tracking_code": "Order Code",
        "phone":         "Phone",
        "status":        "Status"
      },
      "success_keywords": ["DELIVERED"]
    }
  }
}
```

Each field accepts a single string or a fallback list — if the carrier renames a header next month, update the list, no code change.

### CLI usage

```bash
# dry run — preview stats, no DB change
lvt-cert import-shipments path/to/carrier.xlsx --round main --carrier viettel

# commit after review
lvt-cert import-shipments path/to/carrier.xlsx --round main --carrier viettel --commit

# JSON output for scripting
lvt-cert import-shipments path/to/carrier.xlsx --carrier viettel --json
```

Dry-run is the default on purpose — operator eyeballs the status breakdown + match rate before writing. Re-run with `--commit` to persist.

### API usage

```bash
curl -F file=@carrier.xlsx \
     -F token="$ADMIN_JWT" \
     -F round_id=main \
     -F carrier=viettel \
     -F commit=true \
     https://mycerts.example/api/admin/shipments/import
```

- Admin-only (viewer role → 403)
- Rate-limit: 5 requests/min/IP
- Max file: 10 MB (tunable via `SHIPMENT_IMPORT_MAX_BYTES` env)
- Only `.xlsx`, `.xlsm`, `.csv` accepted

### How matching works

1. Parse each row via `column_mapping` — first header name present wins
2. Normalize phone (strip non-digits + leading zero, VN convention)
3. Dedup by `tracking_code` — earlier row wins on conflict
4. Query `students.phone` to resolve SBDs (one phone may map to multiple SBDs; one shipment row per match)
5. Rows with status starting from `skip_status_prefixes` are excluded
6. Status case-insensitive substring match against `success_keywords` → `is_success` flag

### Audit trail

Each import emits one `shipment.bulk_import` entry in `admin_activity` with metadata `{parsed, matched_sbds, inserted, success_count, unmatched_phones, committed}`. No raw row data leaks into the log — PII stays in the SQLite `shipment_history` table only.

### Troubleshooting

- **Low match rate** — most SBDs often ship via school bulk, not individual carrier. Expected.
- **Status not detected as success** — add keyword to `success_keywords`. CLI's dry-run `Status breakdown` section shows all raw values.
- **`data_mapping.phone_col` error** — import requires a phone column on students; set it and re-ingest.
- **Unknown headers** — `first_matching_header` couldn't resolve. Run the file through the CLI; error lists which logical fields are unresolved + file's headers.
