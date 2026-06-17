# Khắc phục sự cố

Các kiểu lỗi thường gặp cùng nguyên nhân gốc. Sắp xếp theo triệu chứng, không theo từng hệ thống con.

## "Đăng nhập admin trả về 200 nhưng tôi không nhận được email"

**Nguyên nhân**: Thiếu `RESEND_API_KEY` (hoặc `CERT_EMAIL_FROM`). Ứng dụng chuyển sang `NullEmailProvider` và âm thầm nuốt thông báo. Log lúc khởi động:

```
RESEND_API_KEY not set, OTP / magic-link emails will be swallowed.
```

**Khắc phục**: Đặt cả hai biến môi trường:

```bash
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxx
CERT_EMAIL_FROM=no-reply@yourdomain.com  # phải là địa chỉ gửi đã xác minh trên Resend
```

Khởi động lại container hoặc serverless function.

## "Mọi client dùng chung một rate-limit bucket" (ai cũng bị 429)

**Nguyên nhân**: Bản triển khai đứng sau proxy (Nginx, Caddy, Vercel) nhưng chưa đặt `TRUST_PROXY_HEADERS`, nên ứng dụng tính khóa rate limiter theo IP của proxy (luôn là 127.0.0.1 hoặc IP của bộ cân bằng tải).

**Khắc phục**:

```bash
TRUST_PROXY_HEADERS=1
```

**Nguyên nhân ngược lại**: Đặt `TRUST_PROXY_HEADERS=1` khi bind **trực tiếp** (không có proxy phía trước). Lúc đó client có thể giả mạo `X-Forwarded-For` và vượt qua bộ giới hạn.

**Khắc phục**: Để `0`, trừ khi có proxy đáng tin cậy ghi đè header.

## "Trình duyệt từ chối request CORS đến /api/*"

**Nguyên nhân**: `ALLOWED_ORIGINS` không bao gồm origin của front-end.

**Kiểm tra**:

```bash
curl -H "Origin: https://myapp.example" -I https://mycerts.example/api/captcha
# Tìm dòng: Access-Control-Allow-Origin: https://myapp.example
```

Nếu thiếu dòng này, origin không nằm trong danh sách cho phép.

**Khắc phục**:

```bash
ALLOWED_ORIGINS=https://myapp.example,https://admin.mycerts.example
```

Mặc định là `*`, tức phản hồi lại mọi origin. Hãy giới hạn lại khi đã biết domain của front-end.

## "Docker healthcheck báo unhealthy"

**Nguyên nhân**: Bản triển khai cũ thăm dò bằng `POST /api/captcha` (trước giai đoạn P2). Endpoint đó nay đã có rate limit và ghi trạng thái vào KV, nên việc thăm dò mỗi 30 giây nhanh chóng làm đầy bucket rate của captcha rồi tự trả về `429`.

**Khắc phục**: Dockerfile hiện tại đã dùng `GET /health`. Nếu bạn mở rộng nó, hãy bảo đảm thăm dò trỏ vào `/health`, không phải `/api/captcha`.

## "Ghi KV chập chờn trên Docker khi có hơn 1 worker"

**Nguyên nhân**: `KV_BACKEND=local` kết hợp `WEB_CONCURRENCY > 1`. KV dạng file cục bộ chỉ đồng bộ trong một process; hai worker tranh chấp trên chu trình đọc-sửa-ghi và làm mất dữ liệu ghi.

**Cảnh báo lúc khởi động**:

```
KV_BACKEND=local with 2 workers is unsafe, concurrent reads can lose writes.
```

**Khắc phục**: Chọn một trong hai:

- Hạ xuống một worker duy nhất: `WEB_CONCURRENCY=1`.
- Chuyển sang backend dùng chung: `KV_BACKEND=upstash` và đặt `UPSTASH_REDIS_REST_URL` cùng `UPSTASH_REDIS_REST_TOKEN`.

## "Email magic link chứa origin sai"

**Nguyên nhân**: `PUBLIC_BASE_URL` chưa đặt (hoặc đặt sai). Phương án dự phòng dùng `request.host_url`, vốn phản hồi lại đúng Host header mà client gửi, nên kẻ tấn công có thể đầu độc email bằng domain của họ.

**Khắc phục**:

```bash
PUBLIC_BASE_URL=https://mycerts.example  # origin HTTPS chính xác, không có dấu gạch chéo cuối
```

## "Session admin không đăng xuất được, JWT vẫn dùng được sau `/api/admin/logout`"

**Nguyên nhân**: Route vẫn chấp nhận token mà không truyền `kv` vào `verify_admin_token`. Việc thu hồi phải được bật riêng cho từng endpoint.

**Kiểm tra** xem route nào có áp dụng thu hồi trong repo này:

- `/api/admin/search` ✓
- `/api/shipment/upsert` ✓

Mọi đoạn mã transport tùy chỉnh (lớp đệm Vercel, cách dùng nhúng) bắt buộc phải truyền `kv=` vào `verify_admin_token` thì denylist mới có hiệu lực.

**Cách khắc phục thay thế**: Xoay `JWT_SECRET`. Việc này vô hiệu hóa mọi session và buộc admin đăng nhập lại.

## "mkdocs build lỗi trong CI"

**Nguyên nhân 1**: Liên kết nội bộ bị hỏng. Chế độ `--strict` sẽ làm hỏng quá trình build nếu có bất kỳ tham chiếu trang nào không phân giải được.

**Khắc phục**: Chạy `mkdocs build --strict` ở máy cục bộ rồi sửa theo thông báo lỗi.

**Nguyên nhân 2**: Trang mới chưa được thêm vào `nav` trong `mkdocs.yml`. Trang mồ côi sẽ phát sinh cảnh báo và khiến `--strict` thất bại.

**Khắc phục**: Thêm trang vào đúng mục `nav`.

## "Xác thực QR luôn báo không hợp lệ"

**Nguyên nhân** (xếp theo xác suất giảm dần):

1. **Sai `public_key.pem`**. Bên xác thực nhận khóa không khớp với bên ký. Kiểm tra `sha256sum public_key.pem` ở cả hai phía.
2. **Project slug không khớp**. Payload của QR gắn với `project.slug`, nên chứng chỉ ký cho `demo-2025` không xác thực được với cấu hình `slug: demo-2026`.
3. **Lệch đồng hồ vượt ngưỡng cho phép**. Chữ ký payload chấp nhận sai lệch ±60 giây. Nếu đồng hồ của máy xác thực lệch quá 60 giây thì mọi request đều thất bại.
4. **`max_age_seconds` được kích hoạt**. Nếu `features.qr_verify.max_age_seconds` khác 0, chứng chỉ cũ hơn ngưỡng đó sẽ bị từ chối bất kể chữ ký.

## "`test_search_rate_limit_kicks_in` thất bại trong CI"

Lỗi này đã được sửa: test hiện lặp với biên dự phòng để vượt qua thời điểm chuyển ranh giới cửa sổ. Nếu vẫn thất bại, có thể bộ rate limiter dạng cửa sổ cố định đã bị thay đổi mà chưa cập nhật test. Hãy kiểm tra giới hạn vòng lặp (nên ở mức `2 × STUDENT_RATE_LIMIT` trở lên).

## "Pydantic từ chối cấu hình với lỗi `rounds: List should have at most 20 items`"

Đây là chủ ý. `rounds` bị giới hạn ở 20 để tra cứu công khai không phát sinh truy vấn lan tỏa không giới hạn.

**Khắc phục**: Nếu bạn thực sự cần hơn 20 round, hãy tách thành nhiều cổng (khác `project.slug`) hoặc nâng giới hạn trong `packages/core/luonvuitoi_cert/config/models.py` sau khi đã cân nhắc chi phí truy vấn trong trường hợp xấu nhất.

## "Dependabot mở PR mỗi tuần"

Đúng như chủ ý: pip hàng tuần, còn actions và docker hàng tháng. Hãy merge sớm; `reportlab`, `pypdf`, `cryptography` đều là các phụ thuộc nhạy cảm về chuỗi cung ứng. Nếu muốn nhịp chậm hơn, hãy sửa `.github/dependabot.yml` (`schedule.interval`).

## Vẫn chưa giải quyết được?

- Xem trang [vận hành](operations.md) để phân loại các thông báo log.
- Mở issue kèm log lúc khởi động, các thay đổi trong `mkdocs.yml`, danh sách biến môi trường (đã che thông tin bí mật) và request cụ thể bị lỗi.
