# Xác thực quản trị

Ba phương thức login dùng chung một entry-point cấp JWT. Chọn trong `cert.config.json#admin.auth_mode`:

| Mode | Flow |
|------|------|
| `password` | Email + mật khẩu, một bước. |
| `otp_email` | Email trước → mã 6 số qua email → submit mã. Hai bước. |
| `magic_link` | Email trước → URL một-click qua email → landing `/admin?token=…`. Hai bước. |

Mỗi lần login thành công trả về JWT encode `sub` (user id), `email`, `role`, và `exp` (mặc định 8h). Token ký HS256 với `JWT_SECRET`.

## `JWT_SECRET`

**Bắt buộc.** Không có fallback — thiếu secret sẽ raise `TokenError('JWT_SECRET is not set')` ngay lập tức. Dùng 32+ ký tự random; xoay khi bị compromise.

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

User OTP / magic-link không cần mật khẩu — truyền `password=None`.

## Roles

| Role | Quyền |
|------|-------|
| `super-admin` | Mọi thứ + tạo/xóa admin khác + bật/tắt [feature gate cho public surface](operations.md#feature-gate-cho-public-surface). |
| `admin` | CRUD học viên, quản lý shipment, xem activity log. |
| `viewer` | Read-only. Không cập nhật student hay shipment. |

Handler check role bằng **allowlist** — `token.role in (ADMIN, SUPER_ADMIN)` — nên role tương lai mặc định read-only cho đến khi được thêm explicit. Surface chỉ-super-admin (quản lý user, feature gate) dùng equality check thay vì allowlist.

## Tra cứu timing-safe

`verify_admin_password()` chạy hash PBKDF2 **ngay cả với email unknown** để observer wall-clock không phân biệt được tài khoản không tồn tại với mật khẩu sai. Pattern tương tự trong flow OTP/magic-link bước 1: email unknown nhận decoy KV write + hash, shape response giống hệt, không gửi email.

## OTP (`otp_email`)

- Mã: 6 số, `secrets.SystemRandom`.
- Lưu trữ: `SHA-256(email + "|" + code)` trong KV với key `otp:<email>`, TTL 5 phút. Plaintext không chạm disk.
- Verify: atomic `kv.consume()` — submit concurrent không race được thành double-use.
- Provider: `features.otp_email.provider` — chỉ có adapter `resend`. Set `RESEND_API_KEY` và `CERT_EMAIL_FROM` trong `.env`.

Bootstrap provider trong transport code:

```python
from luonvuitoi_cert.auth import ResendProvider

with ResendProvider(api_key=os.environ["RESEND_API_KEY"], from_address="no-reply@example.org") as mailer:
    …
```

## Magic link (`magic_link`)

- Token: 32-byte url-safe random.
- Lưu trữ: `SHA-256(token)` → email, TTL 15 phút.
- Verify: atomic consume — click link hai lần chỉ work một lần.
- Caller cung cấp callback `link_builder(token) -> str` để ghép click URL (dev server Phase 11 dùng `PUBLIC_BASE_URL + "/admin?token="`).

## Đăng xuất / thu hồi session

JWT là stateless — xoay `JWT_SECRET` vô hiệu hóa mọi session active. Cho trường hợp "một admin bị compromise, cần đăng xuất họ mà không nuke mọi người," portal ship revocation list dựa trên KV.

### Flow client

```http
POST /api/admin/logout
Content-Type: application/json

{"token": "<jwt-hiện-tại>"}
```

Response luôn `200`:

- `{"revoked": true, "jti": "<jti>"}` — token chấp nhận, `jti` thêm vào denylist với TTL = remaining-life
- `{"revoked": false, "error": "admin session expired"}` — token đã invalid, không cần làm gì (client vẫn đăng xuất)

### Enforcement phía server

Bất kỳ handler nào truyền `kv=` vào `verify_admin_token` sẽ từ chối session bị thu hồi với `TokenError("admin session revoked")`. Trong repo này, Flask shim truyền `kv` vào:

- `/api/admin/search` (tra cứu admin mode)
- `/api/shipment/upsert`
- `/api/admin/logout` (idempotent — lời gọi revoke không block trên denylist hit trước đó)

Handler không truyền `kv` giữ hành vi pre-M7 (token valid tới `exp`). Có chủ đích: transport code custom của bạn có thể opt-in revocation từng endpoint khi bạn truyền KV instance qua.

### Storage denylist

Entry lưu trong KV backend cấu hình dưới `jwt_denylist:<jti>` với TTL = `exp - now`. Denylist tự hết hạn — không cần cron. Với TTL session mặc định 8h, kích thước denylist worst-case bị giới hạn bởi số lần logout trong bất kỳ cửa sổ 8h nào.

### Thu hồi programmatic

```python
from luonvuitoi_cert.auth import revoke_admin_token

jti = revoke_admin_token(kv, token=caller_jwt, env={"JWT_SECRET": "..."})
# Lời gọi verify_admin_token(jwt, kv=kv) sau đó sẽ raise TokenError('revoked').
```

## Activity log

Khi truyền `ActivityLog` vào `perform_login`, nó ghi:

- `admin.login.success` — user_id, email, role, IP.
- `admin.login.failure` — email (nếu có), lý do (`bad-password`, `bad-otp`, `bad-magic-link`, `missing-email`, …), IP.

Entry nằm trong bảng SQLite `admin_activity` và nếu có `GSHEET_WEBHOOK_URL`, được forward async trên daemon thread để webhook chậm hoặc down không block login response.

## Hợp đồng transport-layer

Ai wire `perform_login` vào HTTP (dev server làm ở `/api/admin/login`) **phải**:

1. Gọi `validate_request_size(body, max_bytes=32 * 1024)` trước khi parse JSON.
2. Bắt `LoginError` và translate thành HTTP 401. Không bắt `Exception` — bug internal nên bubble lên 500 handler của platform, không leak thành 401 body.
3. Emit `Content-Security-Policy: script-src 'self' 'nonce-…'` trên `/admin` (hoặc bất kỳ page render JS xử lý JWT) để reflected XSS sink không exfiltrate token khỏi `sessionStorage`.
