# Deploy lên Vercel

Runtime Python serverless của Vercel là target production khuyến nghị cho cổng quy mô nhỏ-trung — free tier xử lý hàng nghìn học viên/tháng.

## Yêu cầu

- Tài khoản Vercel.
- Vercel CLI: `npm i -g vercel`.
- Một instance Upstash Redis hoặc Vercel KV (file SQLite trong `/tmp` là ephemeral trên Vercel).

## Bố cục project

`lvt-cert init` tạo cây tương thích Vercel:

```text
my-portal/
├── cert.config.json
├── api/                  # entrypoint serverless (Phase 15 tạo)
├── templates/
├── assets/fonts/
├── data/                 # bundle cùng deploy
├── public_key.pem
├── requirements.txt
├── vercel.json
└── .gitignore
```

> Phase 15 wire handler `api/*.py` mà Vercel gọi. Tạm thời, mirror
> route Flask trong `packages/cli/luonvuitoi_cert_cli/server/app.py` —
> mỗi handler là wrapper một dòng quanh hàm thuần từ
> `luonvuitoi_cert.api`.

## Biến môi trường

Set trong dashboard Vercel hoặc qua `vercel env add`:

| Tên | Bắt buộc | Ghi chú |
|-----|----------|---------|
| `JWT_SECRET` | có | 32+ ký tự random. |
| `ADMIN_DEFAULT_PASSWORD` | bootstrap | Dùng bởi seed script; xoay ngay. |
| `PUBLIC_BASE_URL` | có | Ví dụ `https://mycerts.example`. Ghim magic-link + URL QR chống Host-header injection. |
| `KV_BACKEND` | có | `upstash` hoặc `vercel-kv` (không bao giờ `local` trên Vercel — `/tmp` là ephemeral). |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | nếu `KV_BACKEND=upstash` | |
| `KV_REST_API_URL` / `KV_REST_API_TOKEN` | nếu `KV_BACKEND=vercel-kv` | Vercel auto-inject khi bạn link Vercel KV store. |
| `RESEND_API_KEY` / `CERT_EMAIL_FROM` | nếu `admin.auth_mode` là `otp_email` hoặc `magic_link` | Thiếu key → fallback `NullEmailProvider` với warning; OTP bị drop âm thầm. |
| `GSHEET_WEBHOOK_URL` | tùy chọn | Phải `https://…`. Scheme khác bị reject với warning (guard SSRF). |
| `ALLOWED_ORIGINS` | khuyến nghị | Whitelist CORS, phân cách dấu phẩy; ví dụ `https://mycerts.example`. Default `*` — ghim khi biết domain front-end. |
| `TRUST_PROXY_HEADERS` | **có cho Vercel** | Set `1`. Vercel terminate TLS và forward `X-Forwarded-For`; không có flag này, rate limiter key theo IP proxy Vercel, mọi request share chung một bucket. |
| `FORCE_HSTS` | khuyến nghị | Set `1`. Vercel là HTTPS-only; emit HSTS để browser từ chối downgrade. |

## `vercel.json`

File scaffolded route root / admin / verify đến serverless handler và set timeout 30 giây mỗi invocation:

```json
{
  "rewrites": [
    { "source": "/", "destination": "/api/index" },
    { "source": "/admin", "destination": "/api/admin" },
    { "source": "/certificate-checker", "destination": "/api/certificate-checker" }
  ],
  "functions": {
    "api/*.py": { "maxDuration": 30 }
  }
}
```

## Pattern `/tmp` SQLite

Vercel runtime cung cấp `/tmp` writable mỗi warm container. Khi cold start, copy DB bundle vào đó:

```python
_SRC = Path(__file__).parent.parent / "data" / "my-portal.db"
_TMP = Path("/tmp/my-portal.db")

def get_db_path() -> Path:
    if not _TMP.exists():
        shutil.copy2(_SRC, _TMP)
    return _TMP
```

Admin mutation write vào `/tmp` và mirror qua Upstash/Vercel KV (xem `luonvuitoi_cert.storage.kv`) để cold start sau replay delta.

## Deploy

```bash
vercel --prod
```

Lần đầu prompt bạn link project và set env var. Deploy sau chỉ một lệnh.

## Verify

```bash
curl https://mycerts.example/api/captcha -X POST
# → {"id":"…","question":"3 + 5 = ?"}
```

Mở `https://mycerts.example/admin` và tạo admin đầu tiên với script one-off (xem [Xác thực quản trị](admin-auth.md)).

## Lưu ý CSP

`/admin` phải emit `Content-Security-Policy: script-src 'self' 'nonce-…'; default-src 'self'; frame-ancestors 'none'`. Flask dev server làm tự động; wrapper handler Vercel phải replicate để sessionStorage JWT an toàn chống reflected XSS.

## Logs

`vercel logs` stream các invocation gần đây. Lỗi admin và webhook retry đến đây qua module stdlib `logging`.
