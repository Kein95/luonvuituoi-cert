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

## Import hàng loạt từ Excel/CSV của carrier

Các đơn vị vận chuyển (Viettel Post, GHN, GHTK, …) giao cho ban tổ chức bản Excel báo cáo giao hàng theo tháng. Lệnh CLI `lvt-cert import-shipments` và endpoint `POST /api/admin/shipments/import` parse các file này qua profile riêng mỗi carrier và ghi vào bảng `shipment_history` (PK `(round_id, sbd, tracking_code)` — giữ mọi lần gửi cho audit).

### Cấu hình

Thêm vào `cert.config.json#features.shipment`:

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

Mỗi field nhận single string hoặc list fallback — carrier đổi header tháng sau, chỉ cần update list, không phải sửa code.

### Cách dùng CLI

```bash
# dry run — xem stats trước, không ghi DB
lvt-cert import-shipments path/to/carrier.xlsx --round main --carrier viettel

# commit sau khi review
lvt-cert import-shipments path/to/carrier.xlsx --round main --carrier viettel --commit

# JSON output cho automation
lvt-cert import-shipments path/to/carrier.xlsx --carrier viettel --json
```

Dry-run là default có chủ đích — admin nhìn status breakdown + match rate trước khi write. Chạy lại với `--commit` để persist.

### Cách dùng API

```bash
curl -F file=@carrier.xlsx \
     -F token="$ADMIN_JWT" \
     -F round_id=main \
     -F carrier=viettel \
     -F commit=true \
     https://mycerts.example/api/admin/shipments/import
```

- Chỉ admin (viewer role → 403)
- Rate-limit: 5 request/phút/IP
- Max file: 10 MB (tune qua env `SHIPMENT_IMPORT_MAX_BYTES`)
- Chỉ chấp nhận `.xlsx`, `.xlsm`, `.csv`

### Cách matching hoạt động

1. Parse mỗi row qua `column_mapping` — header name đầu tiên match thắng
2. Normalize phone (strip non-digit + zero đầu, VN convention)
3. Dedup theo `tracking_code` — row trước thắng khi trùng
4. Query `students.phone` resolve SBDs (một phone có thể map nhiều SBDs; mỗi match một row shipment)
5. Row có status bắt đầu bằng `skip_status_prefixes` bị loại
6. Status substring không phân biệt hoa/thường với `success_keywords` → flag `is_success`

### Audit trail

Mỗi import emit 1 entry `shipment.bulk_import` trong `admin_activity` với metadata `{parsed, matched_sbds, inserted, success_count, unmatched_phones, committed}`. Không có row data thô vào log — PII chỉ nằm trong bảng SQLite `shipment_history`.

### Khắc phục sự cố

- **Match rate thấp** — phần lớn SBD gửi qua trường bulk, không qua carrier cá nhân. Bình thường.
- **Status không được coi là success** — thêm keyword vào `success_keywords`. Section `Status breakdown` của dry-run CLI hiển thị mọi giá trị raw.
- **Lỗi `data_mapping.phone_col`** — import cần cột phone trên students; set nó và re-ingest.
- **Header không resolve** — `first_matching_header` không tìm ra. Chạy file qua CLI; error liệt kê field logic nào chưa resolve + header file hiện có.
