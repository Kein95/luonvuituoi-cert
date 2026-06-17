# Theo dõi vận chuyển

Bảng tùy chọn để theo dõi việc giao chứng chỉ bản cứng. Admin upsert bản ghi; học viên tra cứu trạng thái của mình.

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

- `statuses`: các giá trị cho phép của cột `status`. Danh sách phải khác rỗng và không trùng nhau khi bỏ qua hoa thường.
- `fields`: các cột TEXT bổ sung trên bảng `shipments`. Mỗi cột phải là một SQL identifier hợp lệ. Các tên dành riêng (`id`, `round_id`, `sbd`, `status`, `created_at`, `updated_at`) bị từ chối để tránh xung đột với schema cố định.
- `public_fields`: tập con của `fields` mà endpoint tra cứu công khai được phép trả về. **Mặc định là rỗng.** Học viên chỉ thấy `status` và `updated_at`, trừ khi bạn đưa thêm cột vào danh sách cho phép.

## Bố cục bảng

`shipments`:

| Cột | Kiểu | Ghi chú |
|-----|------|---------|
| `id` | TEXT PK | UUID. |
| `round_id` | TEXT | Lấy từ danh sách rounds của bạn. |
| `sbd` | TEXT | Số báo danh học viên. |
| `status` | TEXT | Một trong các giá trị `features.shipment.statuses`. |
| `created_at` / `updated_at` | TEXT | ISO 8601 UTC. |
| …`fields[]` | TEXT | Các cột bổ sung bạn khai báo. |
| `UNIQUE(round_id, sbd)` | | Khóa tổ hợp: mỗi học viên một dòng cho mỗi chứng chỉ. |

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

Hàm này dùng `INSERT ... ON CONFLICT DO UPDATE` của SQLite, nên hai admin cùng bấm Lưu trên một dòng đồng thời sẽ không tranh chấp dẫn tới `IntegrityError`. Khi xảy ra xung đột, cơ chế cập nhật theo kiểu vá: chỉ những trường do người gọi cung cấp mới bị ghi đè, còn cột không đụng tới vẫn giữ giá trị cũ.

Activity log ghi `shipment.upsert` kèm `status` và `fields_touched` (danh sách các khóa, **không** phải giá trị, để giữ mã vận đơn và địa chỉ không lọt vào luồng webhook).

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

Đi qua cùng lớp CAPTCHA và rate limit như tra cứu của học viên. Cấu trúc response:

```json
{
  "status": "shipped",
  "updated_at": "2026-04-20T11:23:00Z",
  "fields": { "carrier": "GHN" }
}
```

`fields` chỉ chứa các khóa nằm trong `features.shipment.public_fields`. Các cột `id`, `created_at` và các cột nội bộ khác không bị để lộ.

## Ràng buộc giá trị status

`upsert_shipment` kiểm tra `status` so với danh sách cấu hình trước khi ghi. Lỗi gõ sai trong giao diện admin sẽ làm phát sinh mã 400 kèm danh sách các giá trị được phép.

## Liệt kê shipment

`list_shipments(db, config, status=..., round_id=..., limit=200)` trả về N bản ghi gần nhất (giới hạn ở `MAX_LIST_LIMIT = 500`), sắp xếp theo `updated_at DESC`. Trang admin dùng hàm này cho tab "shipments" (từ Phase 10 trở đi).

## Bảo vệ bằng cờ tính năng

Cả ba điểm vào (`upsert_shipment_record`, `lookup_shipment`, `build_shipment_schema`) đều phát sinh lỗi nếu `features.shipment.enabled` là false, nhờ đó bạn có thể tắt tính năng mà không cần xóa bảng.

## Lưu ý về migration

Thêm mục mới vào `features.shipment.fields` vẫn hoạt động với cơ sở dữ liệu hiện có, vì kiểu dữ liệu động của SQLite đủ linh hoạt để cách `CREATE TABLE IF NOT EXISTS` không làm thay đổi schema sẵn có. Nếu cần thêm cột cho một cơ sở dữ liệu đã có dữ liệu, hãy dùng `ALTER TABLE` thủ công; toolkit không có framework migration.

## Import hàng loạt từ Excel/CSV của carrier

Các đơn vị vận chuyển (Viettel Post, GHN, GHTK và những hãng khác) gửi cho ban tổ chức bản Excel báo cáo giao hàng hằng tháng. Lệnh CLI `lvt-cert import-shipments` và endpoint `POST /api/admin/shipments/import` phân tích các file này qua profile riêng cho từng hãng vận chuyển rồi ghi vào bảng `shipment_history` (khóa chính là `(round_id, sbd, tracking_code)`, lưu lại mọi lần gửi để phục vụ audit).

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

Mỗi trường nhận một chuỗi đơn hoặc một danh sách phương án thay thế, nên khi hãng vận chuyển đổi tiêu đề cột vào tháng sau, bạn chỉ cần cập nhật danh sách chứ không phải sửa code.

### Cách dùng CLI

```bash
# chạy thử: chỉ xem thống kê trước, không ghi vào cơ sở dữ liệu
lvt-cert import-shipments path/to/carrier.xlsx --round main --carrier viettel

# ghi nhận sau khi đã rà soát
lvt-cert import-shipments path/to/carrier.xlsx --round main --carrier viettel --commit

# xuất JSON để tự động hóa
lvt-cert import-shipments path/to/carrier.xlsx --carrier viettel --json
```

Chế độ chạy thử là mặc định một cách có chủ đích, để admin xem phân tích trạng thái và tỷ lệ khớp trước khi ghi. Chạy lại với `--commit` để lưu lại.

### Cách dùng API

```bash
curl -F file=@carrier.xlsx \
     -F token="$ADMIN_JWT" \
     -F round_id=main \
     -F carrier=viettel \
     -F commit=true \
     https://mycerts.example/api/admin/shipments/import
```

- Chỉ admin được phép (vai trò viewer sẽ nhận 403).
- Giới hạn tần suất: 5 request mỗi phút trên mỗi IP.
- Dung lượng file tối đa: 10 MB (điều chỉnh qua biến môi trường `SHIPMENT_IMPORT_MAX_BYTES`).
- Chỉ chấp nhận `.xlsx`, `.xlsm`, `.csv`.

### Cơ chế khớp dữ liệu

1. Phân tích từng dòng qua `column_mapping`; tên tiêu đề khớp đầu tiên được chọn.
2. Chuẩn hóa số điện thoại (bỏ ký tự không phải số và số 0 ở đầu, theo quy ước Việt Nam).
3. Khử trùng lặp theo `tracking_code`; khi trùng thì dòng xuất hiện trước được giữ.
4. Truy vấn `students.phone` để phân giải ra SBD (một số điện thoại có thể ứng với nhiều SBD; mỗi lần khớp tạo một dòng shipment).
5. Dòng có status bắt đầu bằng `skip_status_prefixes` sẽ bị loại.
6. Nếu status chứa chuỗi con khớp với `success_keywords` (không phân biệt hoa thường) thì được gắn cờ `is_success`.

### Audit trail

Mỗi lần nhập sẽ phát sinh một bản ghi `shipment.bulk_import` trong `admin_activity` với metadata `{parsed, matched_sbds, inserted, success_count, unmatched_phones, committed}`. Không có dữ liệu dòng thô nào lọt vào log; PII chỉ nằm trong bảng SQLite `shipment_history`.

### Khắc phục sự cố

- **Tỷ lệ khớp thấp**: phần lớn SBD được gửi qua trường gộp chứ không qua từng hãng riêng lẻ. Đây là điều bình thường.
- **Status không được coi là thành công**: hãy thêm từ khóa vào `success_keywords`. Mục `Status breakdown` của chế độ chạy thử trên CLI hiển thị mọi giá trị thô.
- **Lỗi `data_mapping.phone_col`**: quá trình nhập cần cột số điện thoại trên bảng students; hãy thiết lập cột này rồi nhập lại dữ liệu.
- **Tiêu đề không phân giải được**: `first_matching_header` không tìm thấy cột phù hợp. Hãy chạy file qua CLI; thông báo lỗi sẽ liệt kê trường logic nào chưa phân giải được cùng các tiêu đề hiện có trong file.
