# Tài liệu cấu hình

Mỗi deployment được mô tả bởi một file `cert.config.json` duy nhất. Trang này là danh sách key chính thức; JSON Schema tại `cert.schema.json` hỗ trợ autocomplete trong editor.

## Cấu trúc top-level

```jsonc
{
  "$schema": "…/cert.schema.json",
  "project":       { "name": "DEMO", "slug": "demo", "locale": "en", "branding": { … } },
  "rounds":        [{ "id": …, "label": …, "table": …, "pdf": … }],
  "subjects":      [{ "code": …, "en": …, "vi": …, "db_col": … }],
  "results":       { "<subject_code>": { "<result_name>": <page_number> } },
  "data_mapping":  { "sbd_col": …, "name_col": …, … },
  "layout":        { "page_size": [842, 595], "fields": { "<field>": { … } } },
  "fonts":         { "<font_key>": "<relative/path.ttf>" },
  "student_search": { "mode": …, "admin_mode": … },
  "admin":         { "auth_mode": …, "multi_user": …, "roles": […] },
  "features":      { "qr_verify": { … }, "shipment": { … }, "otp_email": { … }, "gsheet_log": { … }, "kv_backend": … }
}
```

## `project`

| Key | Kiểu | Ghi chú |
|-----|------|---------|
| `name` | string | Hiển thị ở header trang. 1–120 ký tự. |
| `slug` | string | kebab-case chữ thường, dùng trong QR payload để bind chứng chỉ với bên phát hành. |
| `locale` | `"en"` / `"vi"` | Ngôn ngữ UI mặc định. |
| `branding.primary_color` | hex | Giá trị CSS `--primary`. |
| `branding.accent_color` | hex | Giá trị CSS `--accent`. |
| `branding.logo_url` | string hoặc null | Phải bắt đầu bằng `/`, `http(s)://`, hoặc `data:image/`. `javascript:` bị từ chối. |

## `rounds` và `subjects`

Mỗi **round** là một bộ chứng chỉ (ví dụ vòng loại và vòng chung kết); mỗi **subject** là một môn song song (ví dụ Toán / Khoa học). Mọi round dùng chung danh sách subject.

- `rounds[].id` + `subjects[].code` phải unique và khớp `^[A-Za-z0-9][A-Za-z0-9_-]*$`.
- `rounds[].table` + `subjects[].db_col` phải là SQL identifier (`^[A-Za-z_][A-Za-z0-9_]*$`).
- `rounds[].pdf` là đường dẫn tương đối đến project root; đường dẫn tuyệt đối và `..` bị từ chối.

## `results`

Map `subject_code → { result_name: page_number }`. Ví dụ:

```json
"results": {
  "S": { "GOLD": 1, "SILVER": 2, "BRONZE": 3 },
  "E": { "GOLD": 4, "SILVER": 5, "BRONZE": 6 }
}
```

Quy tắc: mọi `subjects[].code` phải xuất hiện như key top-level; số trang ≥ 1 và unique trong mỗi subject. Tên kết quả trong file Excel nguồn được so khớp không phân biệt dấu và hoa/thường.

## `data_mapping`

Map vai trò logic với tên cột nguồn (tức là Excel/CSV header gọi là gì). Mọi giá trị phải pass regex SQL identifier.

| Key | Bắt buộc |
|-----|----------|
| `sbd_col` | có |
| `name_col` | có |
| `dob_col`, `school_col`, `grade_col`, `phone_col` | tùy chọn — bật chế độ tra cứu tương ứng |
| `extra_cols` | `string[]` — các trường linh hoạt được ingest vào schema |

## `layout`

```jsonc
{
  "page_size": [842, 595],
  "fields": {
    "name":   { "x": 421, "y": 330, "font": "script", "size": 40, "color": "#1E3A8A", "align": "center", "wrap": null },
    "school": { "x": 421, "y": 280, "font": "serif",  "size": 18, "align": "center", "wrap": 60 }
  }
}
```

Key của field là tên logic mà engine điền (ví dụ `name`, `school`, `grade`, `dob`, `phone`). `font` phải trỏ đến key trong registry `fonts` top-level; `align` là `left` / `center` / `right`; `wrap` (tùy chọn) wrap dòng ở số ký tự đó.

## `fonts`

`{ "<key>": "<relative_ttf_path>" }`. Đường dẫn không được tuyệt đối, chứa `..`, hoặc bắt đầu bằng ký tự ổ đĩa. Key là token được tham chiếu bởi `layout.fields[*].font`.

## `student_search`

- `mode`: `name_dob_captcha` (mặc định) / `name_sbd_captcha` / `sbd_phone`.
- `admin_mode`: `sbd_auth` (mặc định) / `sbd_phone` — dùng bởi form tra cứu trong trang admin.

## `admin`

| Key | Ghi chú |
|-----|---------|
| `auth_mode` | `password`, `otp_email`, hoặc `magic_link`. Quyết định shape của flow login. |
| `multi_user` | Hiện mang tính thông báo; bảng auth luôn hỗ trợ nhiều user. |
| `roles` | Danh sách không rỗng; built-in là `super-admin`, `admin`, `viewer`. |

## `features`

### `qr_verify`

| Key | Ghi chú |
|-----|---------|
| `enabled` | bool |
| `private_key_path` | mặc định `private_key.pem`. Tương đối, không traversal. |
| `public_key_path` | mặc định `public_key.pem`. |
| `x`, `y`, `size_pt` | Engine vẽ QR ở đâu trên mỗi trang overlay (PDF points). |
| `max_age_seconds` | `0` (mặc định) tắt expiry; non-zero từ chối verify request cũ hơn N giây. |

### `shipment`

| Key | Ghi chú |
|-----|---------|
| `enabled` | bool |
| `statuses` | Danh sách status không rỗng, không phân biệt hoa/thường. |
| `fields` | Cột TEXT mở rộng trên bảng shipments. Mỗi cột phải là SQL identifier; xung đột với tên reserved (`id`, `round_id`, `sbd`, `status`, `created_at`, `updated_at`) bị từ chối. |
| `public_fields` | Subset của `fields` mà public lookup endpoint được phép trả về. Mặc định rỗng — học viên chỉ thấy `status` + `updated_at`. |

### `kv_backend`

`local` (mặc định), `upstash`, hoặc `vercel-kv`. Xem [Deploy — Vercel](deploy-vercel.md) để biết biến env mỗi backend cần.

### Các feature flag khác

- `otp_email.enabled` + `otp_email.provider: "resend"` — wire login OTP. Cần biến env `RESEND_API_KEY` và `CERT_EMAIL_FROM`.
- `gsheet_log.enabled` — forward activity admin đến `GSHEET_WEBHOOK_URL` trên background thread.

## Biến môi trường

Config file quyết định _cái gì_ cổng làm; biến env quyết định _ở đâu_ nó chạy. Danh sách đầy đủ với default:

### Bắt buộc

| Tên | Ghi chú |
|-----|---------|
| `JWT_SECRET` | 32+ ký tự random. Không có fallback — thiếu sẽ raise `TokenError` khi startup. Xoay khi bị compromise (mọi session bị vô hiệu). |
| `PUBLIC_BASE_URL` | Ghim magic-link email + URL QR verify chống Host-header injection. Set chính xác origin HTTPS. |

### Thường set

| Tên | Mặc định | Ghi chú |
|-----|----------|---------|
| `ALLOWED_ORIGINS` | `*` | Danh sách origin CORS, phân cách bằng dấu phẩy. Chỉ để `*` khi cổng hoàn toàn công khai. |
| `TRUST_PROXY_HEADERS` | `0` | Set `1` khi deploy sau Nginx / Caddy / Vercel / Cloud Run để app đọc `X-Forwarded-For` cho rate-limit. KHÔNG bật khi bind trực tiếp — client có thể spoof header để bypass limiter. |
| `FORCE_HSTS` | `0` | Set `1` khi site chỉ reachable qua HTTPS. Emit `Strict-Transport-Security` trên mọi response. Browser cache HSTS — bật khi HTTP sẽ khóa user. |
| `WEB_CONCURRENCY` | `2` | Số gunicorn worker. Dockerfile set; nếu ghép với `KV_BACKEND=local` và >1 worker, startup warning fire (local KV không an toàn cross-process). |
| `KV_BACKEND` | `local` | `local` / `upstash` / `vercel-kv`. Xem [vận hành](operations.md#kv-backend). |

### Auth / email

| Tên | Ghi chú |
|-----|---------|
| `ADMIN_DEFAULT_PASSWORD` | Dùng bởi script bootstrap admin. Xoay ngay sau lần login đầu. |
| `RESEND_API_KEY` | Bắt buộc cho auth mode `otp_email` / `magic_link`. Thiếu key → `_resolve_email_provider` fallback về `NullEmailProvider` và log warning — flow OTP / magic-link sẽ âm thầm drop message. |
| `RESEND_FROM_ADDRESS` / `CERT_EMAIL_FROM` | Sender đã verify trên Resend. Cả hai tên đều work (alias cho backwards-compat với `.env.example`). |

### Storage backend

| Tên | Khi nào set |
|-----|-------------|
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | `KV_BACKEND=upstash` |
| `KV_REST_API_URL` / `KV_REST_API_TOKEN` | `KV_BACKEND=vercel-kv` (Vercel tự inject) |
| `KV_LOCAL_PATH` | Override vị trí default `./.kv/store.json` |

### Tích hợp tùy chọn

| Tên | Ghi chú |
|-----|---------|
| `GSHEET_WEBHOOK_URL` | Phải là `https://…`. Scheme khác bị từ chối với warning (guard SSRF). Fire-and-forget — bảng audit local là nguồn chính. |
| `GUNICORN_WORKERS` / `UVICORN_WORKERS` | Được KV factory detect cùng với `WEB_CONCURRENCY` cho cảnh báo multi-worker. |

## Lỗi validation

Nếu giá trị bị từ chối khi load config, bạn sẽ thấy message như:

```
cert.config.json failed validation (…/cert.config.json):
  - rounds.0.pdf: round.pdf must be a relative path (got absolute '/etc/passwd')
```

Đường dẫn file luôn được include; giá trị input thô không bao giờ (giữ secret khỏi error stream).
