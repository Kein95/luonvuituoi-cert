# Vận hành

Cách chạy một deployment LUONVUITUOI-CERT hàng ngày: health probe, log surface, chọn KV backend, thu hồi session, checklist ứng cứu sự cố.

## Health probe

```http
GET /health
```

Trả về `{"ok": true}` với HTTP 200. Endpoint này:

- **Không** đọc database.
- **Không** ghi KV.
- **Không** chạm rate limiter.
- Không yêu cầu auth.

`HEALTHCHECK` của Docker, liveness probe của Kubernetes, và load balancer probe đều nên trỏ vào path này. Các deploy cũ vốn probe `POST /api/captcha` như một tín hiệu health thì nên chuyển sang đây, vì mỗi lần probe sẽ tạo một KV entry và làm đầy rate-limit bucket.

## KV backend

`KV_BACKEND` quyết định state ephemeral sống ở đâu: CAPTCHA challenge, counter rate-limit, mã OTP, hash magic-link, JWT denylist. Chọn một:

| Backend | Khi nào dùng | Multi-worker safe? |
|---------|--------------|---------------------|
| `local` | Dev local, một Docker container đơn lẻ | **Không**: file-lock chỉ có phạm vi trong một process. Startup log cảnh báo khi `WEB_CONCURRENCY > 1`. |
| `upstash` | Mọi nơi (khuyến nghị cho production) | Có: `kv.consume()` được hậu thuẫn bởi lệnh atomic `GETDEL` của Redis. |
| `vercel-kv` | Deploy Vercel | Có: tự inject qua Vercel KV integration. |

Chạy gunicorn nhiều worker với `local`, theo dõi log startup:

```
KV_BACKEND=local with 2 workers is unsafe. Concurrent reads can lose writes.
```

Hoặc drop về 1 worker (`WEB_CONCURRENCY=1`), hoặc chuyển sang `upstash`.

## Logs

Mọi thứ flow qua module stdlib `logging` ở `WARNING` trở lên. Trong Docker, log vào stdout và capture bởi `docker logs`. Trên Vercel, `vercel logs --follow` stream.

Message loud đáng alert:

| Logger | Message | Ý nghĩa |
|--------|---------|---------|
| `luonvuitoi_cert_cli.server.app` | `RESEND_API_KEY not set` | Email OTP/magic-link đang bị drop âm thầm. |
| `luonvuitoi_cert.storage.kv.factory` | `KV_BACKEND=local with N workers is unsafe` | Worker concurrent race trên single file KV. |
| `luonvuitoi_cert.auth.activity_log` | `must be https://` | Ai đó set `GSHEET_WEBHOOK_URL` sang target không HTTPS; forward disable. |
| `luonvuitoi_cert.auth.activity_log` | `activity log webhook POST failed` | Endpoint GSheet down. Record SQLite local vẫn là chính thức. |

Các lỗi đã được xử lý (429 rate-limit, CAPTCHA bị từ chối, 404 search) **không** ghi log, vì đó là traffic bình thường.

## Audit log

Action admin lưu trong bảng SQLite `admin_activity`:

| Cột | Ghi chú |
|-----|---------|
| `id` | UUID4 per entry. |
| `timestamp` | ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`). |
| `user_id` / `user_email` | Claim JWT `sub` + `email`. |
| `action` | `admin.login.success`, `admin.login.failure`, `student.update`, `shipment.upsert`, v.v. |
| `target_id` | Chủ thể thay đổi (ví dụ `students:12345`). |
| `metadata` | JSON blob, _không bao giờ chứa PII_; `student.update` ghi `{column, changed, value_length_delta}`, không ghi giá trị cũ/mới ở dạng thô. |
| `ip` | Client IP (tôn trọng `TRUST_PROXY_HEADERS`). |

Nếu `GSHEET_WEBHOOK_URL` được set (và là `https://`), mỗi entry sẽ được POST theo kiểu fire-and-forget lên sheet thông qua một `ThreadPoolExecutor(4)` có giới hạn. Bản ghi SQLite mới là chính thức, nên webhook lỗi không bao giờ làm hỏng flow admin.

### Recipe truy vấn

```bash
sqlite3 data/portal.db "SELECT timestamp, user_email, action, target_id FROM admin_activity ORDER BY timestamp DESC LIMIT 20;"

# Login fail trong 1 giờ gần nhất:
sqlite3 data/portal.db "SELECT timestamp, user_email, metadata FROM admin_activity WHERE action = 'admin.login.failure' AND timestamp > datetime('now', '-1 hour');"
```

## Thu hồi session

Xem [admin-auth.md](admin-auth.md#ang-xuat-thu-hoi-session) cho flow đầy đủ. Tóm tắt:

- `POST /api/admin/logout` với JWT hiện tại của user → `jti` thêm vào KV denylist với TTL khớp remaining-life.
- Bất kỳ endpoint nào truyền `kv=` vào `verify_admin_token` sẽ từ chối token.
- Denylist tự hết hạn, không cần cron.

Dùng cái này thay vì xoay `JWT_SECRET` (vô hiệu _mọi_ session cùng lúc và mọi admin phải login lại).

## Feature gate cho public surface

Hai công tắc super-admin-only điều khiển xem surface công khai có sống hay không. State lưu trong KV nên bật/tắt có hiệu lực ngay, không cần redeploy.

- **Công tắc tra cứu**: kiểm soát `POST /api/search` (mode student). Khi tắt, endpoint trả `503` với `{"error": "public lookup is currently disabled by the operator"}`. Mode admin (`mode=admin`, cần JWT) không bị ảnh hưởng, để operator vẫn làm việc được trong thời gian đóng băng.
- **Công tắc tải chứng nhận**: kiểm soát `POST /api/download` (mode student). Khi tắt, endpoint trả `503`. Mode admin không bị ảnh hưởng.

Ràng buộc: **download phụ thuộc lookup**. Lookup tắt ⇒ download bị ép tắt theo. Được enforce cả khi ghi (API toggle tự clamp) và khi đọc (gate check cả hai flag).

### Cách bật/tắt

Login với quyền super-admin → thẻ **Public surface** hiện ra phía trên form tra cứu → tick checkbox → **Save**. Checkbox download tự disable khi lookup tắt.

REST tương đương:

```bash
curl -X POST https://your.host/api/admin/features/update \
  -H 'Content-Type: application/json' \
  -d '{"token": "<super-admin JWT>", "lookup_enabled": false, "download_enabled": false}'
```

Chỉ role `super-admin` được chấp nhận; `admin` / `viewer` trả `403`. Mỗi lần bật/tắt đều ghi vào audit log với action `admin.features.update` và state mới trong `metadata`.

### Mặc định

Deploy hoàn toàn mới: cả hai công tắc đều bật (giữ nguyên hành vi như trước khi có gate). KV chỉ được ghi khi super-admin lưu lần đầu, nên một deploy chưa đụng tới sẽ đọc giá trị mặc định được nhúng sẵn (baked-in).

## Update dependency

Dependabot quét hàng tuần (pip) và hàng tháng (github-actions, docker) rồi tự mở PR. Hãy review và merge sớm, vì `reportlab`, `pypdf`, `cryptography` là những mục tiêu của tấn công chuỗi cung ứng (supply-chain).

## Backup

```bash
# Dừng container để snapshot consistent:
docker compose stop
tar czf "backup-$(date +%Y%m%d).tar.gz" data/
docker compose start
```

Hoặc với container đang chạy, dùng SQLite online backup:

```bash
sqlite3 data/portal.db ".backup '/tmp/portal.db.bak'"
```

DB là artifact stateful duy nhất; các entry KV (counter rate-limit, CAPTCHA challenge) chỉ là tạm thời.

## Checklist ứng cứu sự cố

Session một admin có vẻ bị compromise:

1. `POST /api/admin/logout` với token của họ (thu hồi JTI).
2. `UPDATE admin_users SET is_active = 0 WHERE email = '…';` (đai và nịt).
3. Xoay mật khẩu admin (hoặc reset qua OTP).
4. Grep `admin_activity` cho `target_id` họ chạm trong window gần đây.

`JWT_SECRET` leak:

1. Tạo secret mới.
2. Redeploy với giá trị mới (vô hiệu mọi session).
3. Xoay **khóa ký QR** nếu secret bị lộ qua cùng một kênh: `private_key.pem` là artifact riêng nhưng thường nằm chung chỗ với secret.
