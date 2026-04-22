# Khắc phục sự cố

Các failure mode thường gặp và nguyên nhân gốc. Tổ chức theo triệu chứng, không theo subsystem.

## "Admin login trả về 200 nhưng tôi không nhận được email"

**Nguyên nhân**: Thiếu `RESEND_API_KEY` (hoặc `CERT_EMAIL_FROM`). App fallback về `NullEmailProvider` và âm thầm nuốt message. Log startup:

```
RESEND_API_KEY not set — OTP / magic-link emails will be swallowed.
```

**Khắc phục**: Set cả hai biến env:

```bash
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxx
CERT_EMAIL_FROM=no-reply@yourdomain.com  # phải là sender đã verify trên Resend
```

Restart container/serverless function.

## "Mọi client share chung một rate-limit bucket" (ai cũng bị 429)

**Nguyên nhân**: Deploy đứng sau proxy (Nginx, Caddy, Vercel), nhưng `TRUST_PROXY_HEADERS` chưa set, nên app key rate limiter theo IP của proxy (luôn là 127.0.0.1 hoặc IP của LB).

**Khắc phục**:

```bash
TRUST_PROXY_HEADERS=1
```

**Nguyên nhân ngược**: `TRUST_PROXY_HEADERS=1` trên bind **trực tiếp** (không proxy phía trước). Client có thể forge `X-Forwarded-For` và bypass limiter.

**Khắc phục**: Để `0` trừ khi proxy tin cậy ghi đè header.

## "Browser từ chối request CORS đến /api/*"

**Nguyên nhân**: `ALLOWED_ORIGINS` không bao gồm origin của front-end.

**Kiểm tra**:

```bash
curl -H "Origin: https://myapp.example" -I https://mycerts.example/api/captcha
# Tìm: Access-Control-Allow-Origin: https://myapp.example
```

Nếu thiếu, origin không trong whitelist.

**Khắc phục**:

```bash
ALLOWED_ORIGINS=https://myapp.example,https://admin.mycerts.example
```

Mặc định là `*`, echo mọi origin. Restrict khi bạn đã biết domain front-end.

## "Docker healthcheck báo unhealthy"

**Nguyên nhân**: Deploy cũ probe `POST /api/captcha` (pre-P2). Endpoint đó giờ có rate-limit và ghi KV state — probe mỗi 30s nhanh chóng fill captcha rate bucket và tự `429`.

**Khắc phục**: Dockerfile hiện tại đã dùng `GET /health`. Nếu bạn extend nó, đảm bảo probe trỏ vào `/health`, không phải `/api/captcha`.

## "KV write flaky trên Docker với >1 worker"

**Nguyên nhân**: `KV_BACKEND=local` + `WEB_CONCURRENCY > 1`. Local file KV chỉ sync trong một process; hai worker race trên chu trình read-modify-write và mất write.

**Warning startup**:

```
KV_BACKEND=local with 2 workers is unsafe — concurrent reads can lose writes.
```

**Khắc phục**: Chọn một:

- Drop xuống single worker: `WEB_CONCURRENCY=1`
- Chuyển backend shared: `KV_BACKEND=upstash` + set `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN`

## "Email magic-link chứa origin sai"

**Nguyên nhân**: `PUBLIC_BASE_URL` chưa set (hoặc sai). Fallback dùng `request.host_url`, echo lại header Host client gửi — attacker có thể poison email bằng domain của họ.

**Khắc phục**:

```bash
PUBLIC_BASE_URL=https://mycerts.example  # origin HTTPS chính xác, không trailing slash
```

## "Session admin không logout được — JWT vẫn work sau `/api/admin/logout`"

**Nguyên nhân**: Route vẫn accept token không truyền `kv` vào `verify_admin_token`. Revocation là opt-in per endpoint.

**Kiểm tra** route nào enforce revocation trong repo này:

- `/api/admin/search` ✓
- `/api/shipment/upsert` ✓

Transport code custom (Vercel shim, embedded usage) phải truyền `kv=` vào `verify_admin_token` để denylist áp dụng.

**Fix thay thế**: Xoay `JWT_SECRET` — vô hiệu mọi session, admin phải login lại.

## "mkdocs build fail trong CI"

**Nguyên nhân 1**: Link nội bộ bị hỏng. `--strict` mode fail build với mọi page reference không resolve được.

**Khắc phục**: Chạy `mkdocs build --strict` local, theo error message.

**Nguyên nhân 2**: Page mới chưa thêm vào `nav` trong `mkdocs.yml`. Page mồ côi trigger warning → `--strict` fail.

**Khắc phục**: Thêm page vào section `nav` phù hợp.

## "QR verify luôn báo invalid"

**Nguyên nhân** (theo xác suất giảm dần):

1. **`public_key.pem` sai**. Verifier nhận key không khớp signer. Check `sha256sum public_key.pem` ở cả hai đầu.
2. **Project slug không khớp**. QR payload bind vào `project.slug` — cert ký cho `demo-2025` không validate được với config `slug: demo-2026`.
3. **Clock skew vượt tolerance**. Chữ ký payload chấp nhận ±60s. Clock host verify lệch hơn 60s, mọi request fail.
4. **`max_age_seconds` trigger**. Nếu `features.qr_verify.max_age_seconds` non-zero, cert cũ hơn số đó bị từ chối bất kể chữ ký.

## "`test_search_rate_limit_kicks_in` fail trong CI"

Đã được fix — test giờ loop với headroom để survive window-boundary rollover. Nếu vẫn fail, fixed-window rate limiter có thể đã bị thay mà không update test. Check bound loop (nên ≥ `2 × STUDENT_RATE_LIMIT`).

## "Pydantic reject config với `rounds: List should have at most 20 items`"

Có chủ đích. `rounds` cap ở 20 (H3 từ eval 2026-04-22) để public search không fan-out query không giới hạn.

**Khắc phục**: Nếu bạn thực sự cần >20 round, split thành nhiều portal (khác `project.slug`) hoặc nâng cap trong `packages/core/luonvuitoi_cert/config/models.py` sau khi nghĩ qua cost worst-case của query.

## "Dependabot mở PR mỗi tuần"

Đúng ý định — hàng tuần pip / hàng tháng actions+docker. Merge nhanh; `reportlab`, `pypdf`, `cryptography` là supply-chain-sensitive. Muốn cadence chậm hơn, sửa `.github/dependabot.yml` (`schedule.interval`).

## Vẫn bí?

- Check trang [vận hành](operations.md) cho triage log-message.
- File issue với log startup, thay đổi `mkdocs.yml`, danh sách env var (redact secret), và request cụ thể fail.
