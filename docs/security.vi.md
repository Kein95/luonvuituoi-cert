# Bảo mật (hướng dẫn người dùng)

Trang này là hướng dẫn bảo mật cho **người deploy** — knob nào cần chỉnh, phải theo dõi gì, đã được handle sẵn những gì. Cho policy maintainer (báo cáo lỗ hổng, threat model, lựa chọn crypto), xem [`SECURITY.md`](https://github.com/Kein95/luonvuituoi-cert/blob/main/SECURITY.md) ở gốc repo.

## Những gì đã được bảo vệ sẵn

Bạn không cần làm gì cho những điều này — chúng active từ lần deploy đầu tiên:

- **Rate limit + CAPTCHA** trên mọi endpoint công khai (`/api/search`, `/api/download`, `/api/verify`, `/api/captcha`, `/api/shipment/lookup`). Burst mặc định: 20 req/phút per IP cho tra cứu, 30 req/phút cho CAPTCHA.
- **Request oversized bị reject tại socket.** Werkzeug enforce `MAX_CONTENT_LENGTH = 32 KB` trước khi parse, nên POST 1 GB không exhaust memory của parser.
- **User enumeration bị block.** OTP / magic-link bước 1 chạy cùng KV write + dummy hash cho cả email biết và không biết, nên timing observer không probe được địa chỉ hợp lệ.
- **Chữ ký QR** dùng RSA-PSS trên canonical JSON. Chữ ký bao phủ payload và project slug, nên cert cấp cho project A không thể replay cho project B.
- **CAPTCHA / OTP / magic-link consume atomic.** Mỗi token single-use đi qua `kv.consume()`, backed bởi Redis `GETDEL` trên Upstash. Không có race TOCTOU.
- **CSP admin.** `/admin` ship với `script-src 'self' 'nonce-…'` per request, nên reflected-XSS sink không execute được code.
- **Audit log không PII.** `student.update` ghi column + flag thay đổi, không ghi giá trị cũ/mới. Số điện thoại, DOB, địa chỉ không bao giờ rời DB qua webhook audit forward.
- **Security header.** Mọi response carry `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`.
- **Thu hồi JWT.** Đăng xuất thêm JTI vào KV denylist với TTL = remaining-life; không cần xoay `JWT_SECRET` để log một admin ra.

## Những gì bạn phải cấu hình

### 1. `JWT_SECRET`

**Bắt buộc.** 32+ ký tự random. Thiếu, app từ chối cấp admin token.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Xoay khi bị compromise — lưu ý xoay vô hiệu mọi session. Cho single-admin compromise, dùng `POST /api/admin/logout` thay vào đó (xem [thu hồi](admin-auth.md#ang-xuat-thu-hoi-session)).

### 2. `PUBLIC_BASE_URL`

**Bắt buộc cho production.** Ghim origin bake vào email magic-link và URL QR verify chống `Host` header do attacker control. Set chính xác origin HTTPS — `https://mycerts.example`, không có trailing slash.

### 3. `ALLOWED_ORIGINS`

**Khuyến nghị.** Danh sách whitelist origin cho `/api/*`, phân cách bằng phẩy. Chỉ để default `*` khi cổng hoàn toàn công khai và không bao giờ serve credentialed request. Khi đã biết origin front-end, ghim nó:

```bash
ALLOWED_ORIGINS=https://mycerts.example
```

Origin không khớp sẽ không nhận header `Access-Control-Allow-Origin` — browser sẽ reject fetch cross-origin.

### 4. `TRUST_PROXY_HEADERS`

Set `1` **chỉ khi** deploy đứng sau reverse proxy ghi đè `X-Forwarded-For` (Nginx, Caddy, Vercel, Cloud Run). Không có proxy tin cậy, client trực tiếp có thể tự gửi header và spoof IP — bypass rate limiter.

Mặc định `0` (dùng `request.remote_addr` trực tiếp).

### 5. `FORCE_HSTS`

Set `1` khi site **chỉ** reachable qua HTTPS. Browser cache `Strict-Transport-Security` cả năm — bật trên dev HTTP sẽ khóa user khi họ quay lại.

### 6. Email provider

Nếu `admin.auth_mode` là `otp_email` hoặc `magic_link`, set cả hai:

- `RESEND_API_KEY` — từ dashboard Resend
- `CERT_EMAIL_FROM` (hoặc `RESEND_FROM_ADDRESS`) — sender đã verify

Thiếu key, app fallback về `NullEmailProvider` và log warning. Flow login success ở HTTP level nhưng âm thầm drop email gửi ra, user bị stuck.

### 7. Khóa ký QR

`lvt-cert gen-keys` tạo `private_key.pem` + `public_key.pem` tại project root. Xử lý:

- `private_key.pem` → ACL filesystem (`chmod 0400`), exclude khỏi backup không được mã hóa.
- `public_key.pem` → ship thoải mái. Verifier cần nó để check chữ ký.

Nếu private key leak, regen và re-sign (mọi cert trước đó mất đảm bảo chữ ký, lên kế hoạch window re-issue nếu user thật dựa vào QR verify).

### 8. `GSHEET_WEBHOOK_URL`

Nếu bật forward activity-log, URL **phải** là `https://`. Scheme khác bị reject với warning — bảng SQLite audit local luôn là chính thức, nên webhook bị disable không break flow admin.

## Theo dõi gì

Xem [vận hành — logs](operations.md#logs) để biết message loud đáng alert. Ngắn gọn:

- `RESEND_API_KEY not set` → email login đang drop.
- `KV_BACKEND=local with N workers` → race condition trên state CAPTCHA / rate-limit.
- `must be https://` → webhook disable do scheme.

## Non-feature (có chủ đích)

Điều chúng tôi không làm, để bạn không bị ngạc nhiên:

- **Không session admin qua cookie.** JWT nằm trong `sessionStorage` client-side, gửi qua body `token`. Browser không tự gửi body param cross-origin, nên CSRF không exploit được. Không refactor sang cookie mà không thêm CSRF-token middleware.
- **Không vendor CAPTCHA.** Math CAPTCHA xử lý threat scrape-bot mà không cần dep bên thứ ba. hCaptcha/Turnstile là PR away nếu threat model yêu cầu.
- **Không mã hóa QR payload.** Payload là non-sensitive (SBD + round + subject + result + issued_at). Chữ ký đủ chống forgery.
- **Không thu hồi JWT cross-deploy trên Vercel KV.** Denylist nằm trong KV bạn config; chuyển KV backend, session denylist hiện tại flip về "valid until exp." Dùng cutover làm forcing function để xoay `JWT_SECRET`.

## Checklist hardening

Copy-paste trước khi production:

- [ ] `JWT_SECRET` ≥ 32 ký tự random
- [ ] `PUBLIC_BASE_URL` khớp origin HTTPS thật
- [ ] `ALLOWED_ORIGINS` đã ghim (không phải `*`)
- [ ] `TRUST_PROXY_HEADERS=1` nếu sau reverse proxy, `0` nếu không
- [ ] `FORCE_HSTS=1` sau cutover TLS
- [ ] `KV_BACKEND=upstash` hoặc `vercel-kv` (không `local`) cho deploy multi-worker
- [ ] `ADMIN_DEFAULT_PASSWORD` xoay sau lần login admin đầu
- [ ] `private_key.pem` khỏi backup công khai, `chmod 0400`
- [ ] Reverse proxy terminate TLS
- [ ] PR Dependabot review hàng tuần
- [ ] Audit log export định kỳ (ngay cả khi `gsheet_log` disable)
