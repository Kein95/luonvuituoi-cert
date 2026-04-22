# Bắt đầu nhanh

Từ zero đến một cổng chứng chỉ đang chạy trong năm phút.

## Yêu cầu

- Python 3.11 trở lên
- Một file PDF template với mỗi trang tương ứng một biến thể (môn, kết quả) — hoặc dùng example `demo-academy` sẵn có, nó tự vẽ template khi chạy.
- Một font TrueType cho mỗi style bạn muốn (ví dụ một serif, một script).

## 1. Cài đặt

Khi packages đã có trên PyPI:

```bash
pip install luonvuitoi-cert-cli
```

Pre-PyPI (cài từ source — nên dùng khi v1.0.0 chưa được publish):

```bash
git clone https://github.com/Kein95/luonvuituoi-cert
cd luonvuituoi-cert
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ./packages/core -e ./packages/cli
```

Cả hai cách đều cung cấp lệnh `lvt-cert`. CLI phụ thuộc vào engine (`luonvuitoi-cert`), được cài kèm tự động.

## 2. Scaffold project

```bash
lvt-cert init my-portal
cd my-portal
```

Trả lời các câu hỏi (name, slug, locale) hoặc dùng `--non-interactive` kèm `--name`/`--slug`/`--locale` để bỏ qua. Scaffolder sẽ tạo:

```text
my-portal/
├── cert.config.json      # điền rounds / subjects / layout
├── vercel.json
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── (templates/, assets/fonts/, data/ — bạn tự điền)
```

## 3. Cấu hình biến môi trường

```bash
cp .env.example .env
```

Chỉnh `.env` và set ít nhất:

- `JWT_SECRET` — 32+ ký tự random. Server từ chối cấp admin token nếu thiếu biến này.
- `ADMIN_DEFAULT_PASSWORD` — dùng cho script bootstrap admin; đổi ngay cho deploy thật.
- `PUBLIC_BASE_URL` — origin HTTPS của deploy; ghim magic-link + URL QR.

Với production, bạn cần thêm `ALLOWED_ORIGINS`, `TRUST_PROXY_HEADERS=1` (nếu đứng sau reverse proxy), và `FORCE_HSTS=1` (sau khi cutover TLS). Xem [hướng dẫn bảo mật](security.md) để có checklist hardening đầy đủ.

## 4. Thêm PDF template + fonts

1. Đặt file PDF chứng chỉ vào `templates/main.pdf`. Mỗi trang tương ứng một ô trong `cert.config.json#results` (ví dụ `G.GOLD → trang 1`).
2. Đặt font TTF vào `assets/fonts/` với tên file khớp với `cert.config.json#fonts`.

Nếu muốn dùng thử mà không cần asset thật, chạy example demo-academy (xem [Deploy — Docker](deploy-docker.md) hoặc `examples/demo-academy/README.md`).

## 5. Seed dữ liệu test + chạy

```bash
lvt-cert seed --count 10 --seed 42     # ghi data/students.xlsx
lvt-cert gen-keys                      # chỉ khi features.qr_verify.enabled
lvt-cert dev                           # http://127.0.0.1:5000
```

Truy cập:

- `/` — cổng học viên công khai (tra cứu + tải về)
- `/admin` — trang quản trị (tạo admin đầu tiên bằng `luonvuitoi_cert.auth.create_admin_user`; xem [Xác thực quản trị](admin-auth.md))
- `/certificate-checker` — trang xác thực QR công khai

## Tiếp theo

- [Kiến trúc](architecture.md) — các thành phần ghép lại thế nào
- [Cấu hình](config-reference.md) — mọi key trong `cert.config.json` + biến env
- [Bảo mật](security.md) — checklist hardening cho production
- [Hướng dẫn PDF overlay](pdf-overlay-guide.md) — tọa độ, fonts, định vị trường
- [Xác thực quản trị](admin-auth.md) — các chế độ login + thu hồi session
- [Vận hành](operations.md) — health probe, logs, audit trail
- [Khắc phục sự cố](troubleshooting.md) — các lỗi thường gặp
- [Deploy Vercel](deploy-vercel.md) hoặc [Docker](deploy-docker.md)
