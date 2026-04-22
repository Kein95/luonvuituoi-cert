# Theo dõi vận chuyển

Bảng opt-in theo dõi giao chứng chỉ vật lý. Admin upsert record; học viên tra cứu trạng thái của mình.

## Bật

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

- `statuses` — các giá trị cho phép cho cột `status`. Phải không rỗng và unique không phân biệt hoa/thường.
- `fields` — cột TEXT extra trên bảng `shipments`. Mỗi cột phải là SQL identifier. Tên reserved (`id`, `round_id`, `sbd`, `status`, `created_at`, `updated_at`) bị từ chối để tránh va chạm với schema cố định.
- `public_fields` — subset của `fields` mà public lookup endpoint được phép trả về. **Default rỗng.** Học viên chỉ thấy `status` và `updated_at` trừ khi bạn allowlist thêm.

## Bố cục bảng

`shipments`:

| Cột | Kiểu | Ghi chú |
|-----|------|---------|
| `id` | TEXT PK | UUID. |
| `round_id` | TEXT | Từ danh sách rounds của bạn. |
| `sbd` | TEXT | Số báo danh học viên. |
| `status` | TEXT | Một trong `features.shipment.statuses`. |
| `created_at` / `updated_at` | TEXT | ISO 8601 UTC. |
| …`fields[]` | TEXT | Các extra bạn khai báo. |
| `UNIQUE(round_id, sbd)` | | Composite key — một row per cert per student. |

## API admin

`POST /api/shipment/upsert` (yêu cầu JWT; viewer role bị từ chối):

```json
{
  "token": "<admin JWT>",
  "sbd": "12345",
  "round_id": "main",
  "status": "shipped",
  "updates": { "tracking_code": "VN123", "carrier": "GHN" }
}
```

Dùng `INSERT ... ON CONFLICT DO UPDATE` của SQLite nên hai admin bấm Save trên cùng row đồng thời không race thành `IntegrityError`. Semantic patch khi conflict: chỉ field caller-supplied ghi đè; cột không chạm giữ giá trị trước.

Activity log ghi `shipment.upsert` với `status` + `fields_touched` (danh sách key, **không** phải giá trị — giữ tracking code và địa chỉ khỏi stream webhook).

## Tra cứu công khai

`POST /api/shipment/lookup`:

```json
{
  "sbd": "12345",
  "round_id": "main",
  "captcha_id": "...",
  "captcha_answer": 8
}
```

Đi qua cùng cửa CAPTCHA + rate-limit như tra cứu student. Shape response:

```json
{
  "status": "shipped",
  "updated_at": "2026-04-20T11:23:00Z",
  "fields": { "carrier": "GHN" }
}
```

`fields` chỉ chứa key trong `features.shipment.public_fields`. `id`, `created_at`, và internal khác không bị expose.

## Kỷ luật status

`upsert_shipment` validate `status` với danh sách cấu hình trước khi ghi. Typo trong UI admin surface thành 400 với listing giá trị cho phép.

## Listing shipment

`list_shipments(db, config, status=..., round_id=..., limit=200)` trả N gần nhất (cap ở `MAX_LIST_LIMIT = 500`) sort theo `updated_at DESC`. Trang admin dùng cho tab "shipments" (Phase 10+).

## Guard feature flag

Cả ba entry point (`upsert_shipment_record`, `lookup_shipment`, `build_shipment_schema`) raise nếu `features.shipment.enabled` là false — có thể toggle feature off mà không drop bảng.

## Lưu ý migration

Thêm entry mới vào `features.shipment.fields` work với database hiện có — dynamic typing của SQLite đủ dễ dãi để cách `CREATE TABLE IF NOT EXISTS` không alter schema hiện có. Nếu cần thêm cột cho DB đã có data, dùng `ALTER TABLE` thủ công; không có framework migration.
