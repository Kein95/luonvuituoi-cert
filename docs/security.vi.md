# Bảo mật (hướng dẫn người dùng)

Trang này là hướng dẫn bảo mật cho **người triển khai**: cần chỉnh cấu hình nào, phải theo dõi điều gì, và những gì đã được xử lý sẵn. Phần dành cho người duy trì chính sách (báo cáo lỗ hổng, threat model, lựa chọn thuật toán mã hóa), xin xem [`SECURITY.md`](https://github.com/Kein95/luonvuituoi-cert/blob/main/SECURITY.md) ở gốc repo.

## Những gì đã được bảo vệ sẵn

Bạn không cần làm gì với các mục này; chúng có hiệu lực ngay từ lần triển khai đầu tiên:

- **Rate limit và CAPTCHA** trên mọi endpoint công khai (`/api/search`, `/api/download`, `/api/verify`, `/api/captcha`, `/api/shipment/lookup`). Ngưỡng burst mặc định: 20 request mỗi phút trên mỗi IP cho tra cứu, 30 request mỗi phút cho CAPTCHA.
- **Request quá lớn bị từ chối ngay tại socket.** Werkzeug áp `MAX_CONTENT_LENGTH = 32 KB` trước khi parse, nên một request POST 1 GB không thể làm cạn bộ nhớ của bộ phân tích.
- **Chặn dò tìm tài khoản.** Bước 1 của OTP và magic link đều thực hiện cùng một lần ghi KV và cùng một phép băm giả lập cho cả email có thật lẫn không có thật, nên kẻ quan sát thời gian phản hồi không thể dò ra địa chỉ hợp lệ.
- **Chữ ký QR** dùng RSA-PSS trên canonical JSON. Chữ ký bao phủ cả payload lẫn project slug, nên chứng chỉ cấp cho project A không thể đem dùng lại cho project B.
- **Việc tiêu thụ CAPTCHA, OTP và magic link là nguyên tử.** Mỗi token chỉ dùng một lần và đi qua `kv.consume()`, dựa trên lệnh `GETDEL` của Redis trên Upstash. Không có race TOCTOU.
- **CSP cho trang admin.** `/admin` được phục vụ kèm `script-src 'self' 'nonce-…'` riêng cho từng request, nên điểm chèn reflected XSS không thể thực thi mã.
- **Audit log không chứa PII.** `student.update` chỉ ghi tên cột và cờ đánh dấu thay đổi, không ghi giá trị cũ hay mới. Số điện thoại, ngày sinh, địa chỉ không bao giờ rời khỏi cơ sở dữ liệu qua webhook chuyển tiếp audit.
- **Security header.** Mọi response đều mang `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`.
- **Thu hồi JWT.** Khi đăng xuất, hệ thống thêm JTI vào denylist trong KV với TTL bằng phần thời gian sống còn lại; không cần xoay `JWT_SECRET` chỉ để buộc một admin đăng xuất.

## Những gì bạn phải cấu hình

### 1. `JWT_SECRET`

**Bắt buộc.** Chuỗi ngẫu nhiên từ 32 ký tự trở lên. Nếu thiếu, ứng dụng từ chối cấp admin token.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Hãy xoay khóa khi bị lộ, nhưng lưu ý việc xoay sẽ vô hiệu hóa mọi session. Nếu chỉ một admin bị lộ, dùng `POST /api/admin/logout` thay cho việc xoay khóa (xem [thu hồi](admin-auth.md#ang-xuat-thu-hoi-session)).

### 2. `PUBLIC_BASE_URL`

**Bắt buộc cho production.** Ghim cứng origin được nhúng vào email magic link và URL xác thực QR, qua đó chống lại `Host` header do kẻ tấn công điều khiển. Đặt đúng origin HTTPS, ví dụ `https://mycerts.example`, không có dấu gạch chéo ở cuối.

### 3. `ALLOWED_ORIGINS`

**Khuyến nghị.** Danh sách origin được phép cho `/api/*`, phân cách bằng dấu phẩy. Chỉ giữ giá trị mặc định `*` khi cổng hoàn toàn công khai và không bao giờ phục vụ request có kèm thông tin xác thực. Khi đã biết origin của front-end, hãy ghim nó:

```bash
ALLOWED_ORIGINS=https://mycerts.example
```

Origin không khớp sẽ không nhận được header `Access-Control-Allow-Origin`, và trình duyệt sẽ từ chối lệnh fetch khác origin.

### 4. `TRUST_PROXY_HEADERS`

Đặt `1` **chỉ khi** bản triển khai đứng sau một reverse proxy có ghi đè `X-Forwarded-For` (Nginx, Caddy, Vercel, Cloud Run). Nếu không có proxy đáng tin cậy, client kết nối trực tiếp có thể tự gửi header này và giả mạo IP, qua đó vượt qua bộ giới hạn tần suất.

Mặc định là `0` (dùng trực tiếp `request.remote_addr`).

### 5. `FORCE_HSTS`

Đặt `1` khi site **chỉ** truy cập được qua HTTPS. Trình duyệt lưu cache `Strict-Transport-Security` trong suốt một năm, nên nếu bật nhầm trên môi trường dev chạy HTTP, người dùng sẽ bị chặn khi quay lại.

### 6. Nhà cung cấp email

Nếu `admin.auth_mode` là `otp_email` hoặc `magic_link`, hãy đặt cả hai biến:

- `RESEND_API_KEY`: lấy từ dashboard Resend.
- `CERT_EMAIL_FROM` (hoặc `RESEND_FROM_ADDRESS`): địa chỉ gửi đã được xác minh.

Nếu thiếu khóa, ứng dụng sẽ chuyển sang `NullEmailProvider` và ghi cảnh báo vào log. Luồng đăng nhập vẫn báo thành công ở mức HTTP nhưng âm thầm bỏ qua việc gửi email, khiến người dùng bị kẹt.

### 7. Khóa ký QR

`lvt-cert gen-keys` tạo `private_key.pem` và `public_key.pem` tại thư mục gốc của project. Cách xử lý:

- `private_key.pem`: siết quyền truy cập trên hệ thống tệp (`chmod 0400`), loại khỏi mọi bản sao lưu không được mã hóa.
- `public_key.pem`: phân phối thoải mái. Bên xác thực cần file này để kiểm tra chữ ký.

Nếu khóa riêng bị lộ, hãy tạo lại và ký lại (mọi chứng chỉ trước đó sẽ mất bảo đảm về chữ ký; hãy lên kế hoạch cho một đợt cấp lại nếu người dùng thực sự dựa vào việc xác thực QR).

### 8. `GSHEET_WEBHOOK_URL`

Nếu bật chuyển tiếp activity log, URL **bắt buộc** phải là `https://`. Scheme khác sẽ bị từ chối kèm cảnh báo. Bảng audit SQLite cục bộ luôn là nguồn chính thức, nên việc tắt webhook không làm gián đoạn luồng quản trị.

## Cần theo dõi gì

Xem [vận hành, phần logs](operations.md#logs) để biết những thông báo nổi bật đáng cảnh báo. Tóm tắt:

- `RESEND_API_KEY not set`: email đăng nhập đang bị bỏ qua.
- `KV_BACKEND=local with N workers`: nguy cơ race condition trên trạng thái CAPTCHA và rate limit.
- `must be https://`: webhook bị tắt do sai scheme.

## Những điều cố ý không làm

Liệt kê những việc chúng tôi không làm, để bạn không bị bất ngờ:

- **Không lưu session admin qua cookie.** JWT nằm trong `sessionStorage` phía client và được gửi qua trường `token` trong body. Trình duyệt không tự gửi tham số body khi khác origin, nên CSRF không khai thác được. Đừng chuyển sang dùng cookie nếu chưa bổ sung middleware kiểm tra CSRF token.
- **Không dùng CAPTCHA của bên thứ ba.** CAPTCHA dạng toán đủ để xử lý mối đe dọa bot thu thập dữ liệu mà không cần phụ thuộc bên ngoài. Có thể tích hợp hCaptcha hoặc Turnstile chỉ với một PR nếu threat model đòi hỏi.
- **Không mã hóa payload của QR.** Payload không chứa dữ liệu nhạy cảm (SBD, round, môn, kết quả, issued_at). Chỉ riêng chữ ký đã đủ chống giả mạo.
- **Không thu hồi JWT xuyên triển khai trên Vercel KV.** Denylist nằm trong KV mà bạn cấu hình; khi đổi KV backend, denylist session hiện tại sẽ quay về trạng thái "còn hiệu lực cho đến khi hết hạn". Hãy tận dụng lần chuyển đổi đó như một cơ hội bắt buộc để xoay `JWT_SECRET`.

## Danh sách kiểm tra gia cố

Sao chép và rà soát trước khi lên production:

- [ ] `JWT_SECRET` từ 32 ký tự ngẫu nhiên trở lên.
- [ ] `PUBLIC_BASE_URL` khớp đúng origin HTTPS thật.
- [ ] `ALLOWED_ORIGINS` đã được ghim (không để `*`).
- [ ] `TRUST_PROXY_HEADERS=1` nếu đứng sau reverse proxy, ngược lại để `0`.
- [ ] `FORCE_HSTS=1` sau khi đã chuyển hẳn sang TLS.
- [ ] `KV_BACKEND=upstash` hoặc `vercel-kv` (không phải `local`) cho bản triển khai nhiều worker.
- [ ] `ADMIN_DEFAULT_PASSWORD` đã đổi sau lần đăng nhập admin đầu tiên.
- [ ] `private_key.pem` không nằm trong bản sao lưu công khai và đã `chmod 0400`.
- [ ] Reverse proxy đảm nhận việc kết thúc TLS.
- [ ] Rà soát các PR của Dependabot hàng tuần.
- [ ] Xuất audit log định kỳ (kể cả khi `gsheet_log` bị tắt).
