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
