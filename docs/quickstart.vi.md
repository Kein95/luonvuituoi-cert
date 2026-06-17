# Bắt đầu nhanh

Từ con số không đến một cổng chứng chỉ đang chạy chỉ trong năm phút.

## Yêu cầu

- Python 3.11 trở lên.
- Một file PDF template, mỗi trang tương ứng một biến thể (môn, kết quả). Hoặc dùng ví dụ `demo-academy` có sẵn, nó tự dựng template khi chạy.
- Một font TrueType cho mỗi kiểu chữ bạn muốn (ví dụ một font serif, một font script).

## 1. Cài đặt

Khi packages đã có trên PyPI:

```bash
pip install luonvuitoi-cert-cli
```

Khi chưa có trên PyPI (cài từ mã nguồn, nên dùng khi bản v1.0.0 chưa được phát hành):

```bash
git clone https://github.com/Kein95/luonvuituoi-cert
cd luonvuituoi-cert
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ./packages/core -e ./packages/cli
```

Cả hai cách đều cung cấp lệnh `lvt-cert`. CLI phụ thuộc vào engine (`luonvuitoi-cert`) và engine này được cài kèm tự động.

## 2. Scaffold project

```bash
lvt-cert init my-portal
cd my-portal
```

Trả lời các câu hỏi (tên, slug, locale) hoặc dùng `--non-interactive` kèm `--name`/`--slug`/`--locale` để bỏ qua. Trình tạo khung sẽ sinh ra:

```text
my-portal/
├── cert.config.json      # điền rounds / subjects / layout
├── vercel.json
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── (templates/, assets/fonts/, data/ : bạn tự điền)
```

## 3. Cấu hình biến môi trường

```bash
cp .env.example .env
```

Chỉnh `.env` và set ít nhất:

- `JWT_SECRET`: chuỗi ngẫu nhiên từ 32 ký tự trở lên. Server từ chối cấp admin token nếu thiếu biến này.
- `ADMIN_DEFAULT_PASSWORD`: dùng cho script khởi tạo admin; hãy đổi ngay khi triển khai thật.
- `PUBLIC_BASE_URL`: origin HTTPS của bản triển khai; được ghim vào magic link và URL của QR.

Với môi trường production, bạn cần thêm `ALLOWED_ORIGINS`, `TRUST_PROXY_HEADERS=1` (nếu đứng sau reverse proxy) và `FORCE_HSTS=1` (sau khi đã chuyển hẳn sang TLS). Xem [hướng dẫn bảo mật](security.md) để có danh sách kiểm tra việc gia cố đầy đủ.

## 4. Thêm PDF template + fonts

1. Đặt file PDF chứng chỉ vào `templates/main.pdf`. Mỗi trang tương ứng một ô trong `cert.config.json#results` (ví dụ `G.GOLD` ứng với trang 1).
2. Đặt font TTF vào `assets/fonts/` với tên file khớp với `cert.config.json#fonts`.

Nếu muốn dùng thử mà chưa cần tài nguyên thật, hãy chạy ví dụ demo-academy (xem [Deploy bằng Docker](deploy-docker.md) hoặc `examples/demo-academy/README.md`).

## 5. Seed dữ liệu test + chạy

```bash
lvt-cert seed --count 10 --seed 42     # ghi data/students.xlsx
lvt-cert gen-keys                      # chỉ khi features.qr_verify.enabled
lvt-cert dev                           # http://127.0.0.1:5000
```

Các đường dẫn truy cập:

- `/`: cổng học viên công khai (tra cứu và tải về).
- `/admin`: trang quản trị (tạo admin đầu tiên bằng `luonvuitoi_cert.auth.create_admin_user`; xem [Xác thực quản trị](admin-auth.md)).
- `/certificate-checker`: trang xác thực QR công khai.

## Tiếp theo

- [Kiến trúc](architecture.md): các thành phần ghép nối với nhau ra sao.
- [Cấu hình](config-reference.md): mọi khóa trong `cert.config.json` cùng các biến môi trường.
- [Bảo mật](security.md): danh sách kiểm tra gia cố cho production.
- [Hướng dẫn PDF overlay](pdf-overlay-guide.md): tọa độ, fonts, định vị trường.
- [Xác thực quản trị](admin-auth.md): các chế độ đăng nhập và cách thu hồi session.
- [Vận hành](operations.md): health probe, logs, audit trail.
- [Khắc phục sự cố](troubleshooting.md): các lỗi thường gặp.
- [Deploy lên Vercel](deploy-vercel.md) hoặc [Docker](deploy-docker.md).
