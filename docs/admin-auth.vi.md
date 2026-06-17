# Xác thực quản trị

Ba phương thức login dùng chung một entry-point cấp JWT. Chọn trong `cert.config.json#admin.auth_mode`:

| Mode | Flow |
|------|------|
| `password` | Email + mật khẩu, một bước. |
| `otp_email` | Email trước → mã 6 số qua email → submit mã. Hai bước. |
| `magic_link` | Email trước → URL một-click qua email → landing `/admin?token=…`. Hai bước. |

Mỗi lần login thành công trả về JWT encode `sub` (user id), `email`, `role`, và `exp` (mặc định 8h). Token ký HS256 với `JWT_SECRET`.

## `JWT_SECRET`

**Bắt buộc.** Không có giá trị fallback: nếu thiếu secret, hệ thống raise `TokenError('JWT_SECRET is not set')` ngay lập tức. Dùng chuỗi ngẫu nhiên từ 32 ký tự trở lên, và xoay lại khi bị lộ.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Tạo admin đầu tiên

CLI chưa có lệnh tạo admin one-shot (roadmap). Dùng Python API:

```python
from luonvuitoi_cert.auth import Role, create_admin_user

create_admin_user(
    "data/my-portal.db",              # cùng DB mà handler đọc
    email="you@example.org",
    role=Role.SUPER_ADMIN,
    password="mat-khau-that-su",
)
```

User dùng OTP hoặc magic link không cần mật khẩu, hãy truyền `password=None`.

## Roles

| Role | Quyền |
|------|-------|
| `super-admin` | Mọi thứ + tạo/xóa admin khác + bật/tắt [feature gate cho public surface](operations.md#feature-gate-cho-public-surface). |
| `admin` | CRUD học viên, quản lý shipment, xem activity log. |
| `viewer` | Read-only. Không cập nhật student hay shipment. |

Handler kiểm tra role bằng **allowlist** (`token.role in (ADMIN, SUPER_ADMIN)`), nên mọi role thêm về sau sẽ mặc định ở chế độ read-only cho đến khi được cấp quyền tường minh. Các chức năng chỉ dành cho super-admin (quản lý user, feature gate) dùng phép so sánh bằng (equality check) thay vì allowlist.

## Tra cứu timing-safe

`verify_admin_password()` luôn chạy hash PBKDF2 **kể cả khi email không tồn tại**, để người quan sát thời gian phản hồi không phân biệt được trường hợp tài khoản không tồn tại với trường hợp sai mật khẩu. Flow OTP và magic link ở bước 1 cũng áp dụng cách tương tự: với email không tồn tại, hệ thống vẫn thực hiện một thao tác ghi KV giả và hash, trả về response có cấu trúc giống hệt, chỉ khác là không gửi email.

## OTP (`otp_email`)

- Mã: 6 số, `secrets.SystemRandom`.
- Lưu trữ: `SHA-256(email + "|" + code)` trong KV với key `otp:<email>`, TTL 5 phút. Plaintext không bao giờ chạm tới disk.
- Verify: `kv.consume()` thực hiện atomic, nên các lần submit đồng thời không thể chạy đua để dùng mã hai lần (double-use).
- Provider: `features.otp_email.provider` hiện chỉ có adapter `resend`. Set `RESEND_API_KEY` và `CERT_EMAIL_FROM` trong `.env`.

Bootstrap provider trong transport code:

```python
from luonvuitoi_cert.auth import ResendProvider

with ResendProvider(api_key=os.environ["RESEND_API_KEY"], from_address="no-reply@example.org") as mailer:
    …
```

## Magic link (`magic_link`)

- Token: 32-byte url-safe random.
- Lưu trữ: `SHA-256(token)` → email, TTL 15 phút.
- Verify: consume thực hiện atomic, nên click link hai lần thì chỉ lần đầu có hiệu lực.
- Caller cung cấp callback `link_builder(token) -> str` để ghép URL click (dev server Phase 11 dùng `PUBLIC_BASE_URL + "/admin?token="`).

## Đăng xuất / thu hồi session

JWT vốn là stateless, nên việc xoay `JWT_SECRET` sẽ vô hiệu hóa mọi session đang hoạt động. Cho tình huống "một admin bị lộ, cần đăng xuất riêng tài khoản đó mà không ảnh hưởng những người khác", portal cung cấp sẵn revocation list dựa trên KV.

### Flow client

```http
POST /api/admin/logout
Content-Type: application/json

{"token": "<jwt-hiện-tại>"}
```

Response luôn `200`:

- `{"revoked": true, "jti": "<jti>"}`: token được chấp nhận, `jti` đã thêm vào denylist với TTL bằng thời gian sống còn lại của token
- `{"revoked": false, "error": "admin session expired"}`: token đã hết hiệu lực, không cần làm gì thêm (client vẫn đăng xuất)

### Enforcement phía server

Bất kỳ handler nào truyền `kv=` vào `verify_admin_token` sẽ từ chối session bị thu hồi với `TokenError("admin session revoked")`. Trong repo này, Flask shim truyền `kv` vào:

- `/api/admin/search` (tra cứu ở chế độ admin)
- `/api/shipment/upsert`
- `/api/admin/logout` (idempotent: lời gọi revoke không bị chặn dù `jti` đã có sẵn trong denylist từ trước)

Handler không truyền `kv` giữ nguyên hành vi trước M7 (token còn hiệu lực cho tới mốc `exp`). Đây là thiết kế có chủ đích: transport code tùy biến của bạn có thể bật revocation cho từng endpoint bằng cách truyền vào một KV instance.

### Storage denylist

Mỗi entry được lưu trong KV backend đã cấu hình dưới key `jwt_denylist:<jti>` với TTL bằng `exp - now`. Denylist tự hết hạn nên không cần cron. Với TTL session mặc định 8h, kích thước denylist trong trường hợp xấu nhất chỉ bị giới hạn bởi số lần logout trong bất kỳ khoảng thời gian 8h nào.

### Thu hồi programmatic

```python
from luonvuitoi_cert.auth import revoke_admin_token

jti = revoke_admin_token(kv, token=caller_jwt, env={"JWT_SECRET": "..."})
# Lời gọi verify_admin_token(jwt, kv=kv) sau đó sẽ raise TokenError('revoked').
```

## Activity log

Khi truyền `ActivityLog` vào `perform_login`, nó ghi:

- `admin.login.success`: user_id, email, role, IP.
- `admin.login.failure`: email (nếu có), lý do (`bad-password`, `bad-otp`, `bad-magic-link`, `missing-email`, …), IP.

Mỗi entry nằm trong bảng SQLite `admin_activity`; nếu có cấu hình `GSHEET_WEBHOOK_URL`, entry còn được forward bất đồng bộ qua một daemon thread, để webhook chậm hoặc chết không làm nghẽn login response.

## Hợp đồng transport-layer

Ai wire `perform_login` vào HTTP (dev server làm ở `/api/admin/login`) **phải**:

1. Gọi `validate_request_size(body, max_bytes=32 * 1024)` trước khi parse JSON.
2. Bắt `LoginError` và chuyển thành HTTP 401. Không bắt `Exception` chung chung: lỗi nội bộ nên được đẩy lên 500 handler của nền tảng, tránh để lộ ra ngoài qua 401 body.
3. Emit `Content-Security-Policy: script-src 'self' 'nonce-…'` trên `/admin` (hoặc bất kỳ trang nào render JS có xử lý JWT), để các điểm reflected XSS không thể đánh cắp token khỏi `sessionStorage`.
