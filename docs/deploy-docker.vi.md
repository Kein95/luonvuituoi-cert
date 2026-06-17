# Deploy với Docker

Hãy tự host khi bạn muốn dùng SQLite lưu trữ bền vững thay vì phải xoay xở với `/tmp` tạm thời của Vercel, hoặc khi môi trường deploy không có serverless Python runtime.

## Image có sẵn

Root repo cung cấp sẵn `Dockerfile`, cài core engine cùng gunicorn và serve Flask dev server trên port 8000. Phù hợp cho production quy mô nhỏ: một worker xử lý khoảng 30 req/s trên phần cứng giá rẻ.

```bash
docker build -t my-portal:latest .
```

## Runtime

```bash
docker run --rm -p 8000:8000 \
  -e JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  -e ADMIN_DEFAULT_PASSWORD="change-me" \
  -e PUBLIC_BASE_URL="https://mycerts.example" \
  -e ALLOWED_ORIGINS="https://mycerts.example" \
  -e TRUST_PROXY_HEADERS=1 \
  -e FORCE_HSTS=1 \
  -v "$(pwd)/data:/app/project/data" \
  -v "$(pwd)/private_key.pem:/app/project/private_key.pem:ro" \
  my-portal:latest
```

### Checklist env

| Tên | Tại sao |
|-----|---------|
| `JWT_SECRET` | Bắt buộc. Không có fallback. |
| `PUBLIC_BASE_URL` | Ghim magic-link + URL QR. |
| `ALLOWED_ORIGINS` | CORS whitelist; thu hẹp từ `*` khi biết origin front-end. |
| `TRUST_PROXY_HEADERS=1` | Chỉ bật khi có reverse proxy Nginx/Caddy như mô tả bên dưới. Nếu không có proxy ghi đè `X-Forwarded-For`, hãy để `0`; nếu không, client có thể giả mạo IP và vượt qua rate limit. |
| `FORCE_HSTS=1` | Bật khi reverse proxy đã terminate TLS. |
| `WEB_CONCURRENCY` | Mặc định `2`. Với `KV_BACKEND=local` và nhiều hơn 1 worker, startup sẽ log cảnh báo, vì local file KV không an toàn khi chạy đa tiến trình. Hãy chuyển sang `upstash` khi cần scale. |
| `GSHEET_WEBHOOK_URL` | Tùy chọn. Phải `https://…`. |

### Volume mount

- `data/`: SQLite lưu trữ bền vững và (tùy chọn) local KV store, tồn tại qua các lần restart container.
- `private_key.pem`: khóa ký QR. Không bao giờ bake vào image.

### User container

Image chạy as non-root `app:app` (system UID/GID). Nếu bind-mount `data/` từ host, đảm bảo directory writable bởi UID đó (`chown $(id -u):$(id -g) data/` trên host work vì Docker daemon map host UID 1:1 mặc định).

## Healthcheck

`/health` trả `{"ok": true}` không ghi KV, không đọc DB, không chạm rate-limit. Healthcheck Dockerfile + compose probe mỗi 30s.

## docker-compose

`docker-compose.yml` ở root repo là điểm khởi đầu tốt. Đặt `.env` bên cạnh và chạy `docker compose up -d`. Mount project directory (config + templates + fonts) dưới `/app/project`; entrypoint đọc `cert.config.json` từ đó.

## Sau reverse proxy

Gunicorn nói HTTP plain; đặt Caddy hoặc Nginx phía trước để terminate TLS và pass `X-Forwarded-For` để rate limiter key theo IP client thật.

```nginx
location / {
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_pass http://127.0.0.1:8000;
}
```

## Backup

Dừng container (hoặc dùng lệnh `.backup` SQLite trên DB đang live), tar up `data/`, và ship off-host. DB là artifact stateful duy nhất.

## Scale

Flask dev server là single-process; gunicorn spawn nhiều worker nhưng chúng không share memory. Ổn vì:

- Rate limiter + CAPTCHA sống trong KV backend cấu hình (Upstash REST, Vercel KV REST, hoặc `LocalFileKV` mount share). Dùng Upstash nếu muốn multi-host.
- SQLite tuần tự hóa các lần ghi theo từng file database, đủ nhanh cho các thao tác chỉnh sửa của admin trong dưới một giây.
- FontRegistry là per-process, nên worker thêm chỉ re-register fonts ở request đầu.

Nếu vượt quá khả năng của SQLite (khoảng vài trăm lượt ghi mỗi giây), hãy chuyển data layer sang Postgres; pattern repository trong `luonvuitoi_cert.storage` là điểm thay đổi nhỏ gọn để gắn backend mới.
