# Hướng dẫn người dùng cuối

Cách sử dụng ba giao diện mà một cổng đã deploy hiển thị. Không kèm screenshot — các trang là HTML đơn giản, accessible, không có brand chrome ngoài biến CSS bạn cấu hình.

## Ai đọc trang này

- **Người nhận** (học viên, thí sinh, người được khen thưởng) — phần [Cổng học viên](#cong-hoc-vien).
- **Người vận hành** (ban tổ chức, admin khóa học) — phần [Trang quản trị](#trang-quan-tri).
- **Bên thứ ba** (nhà tuyển dụng, trường học, bất kỳ ai xác thực chứng chỉ) — phần [Trang xác thực](#trang-xac-thuc).

Nếu bạn là developer đang deploy cổng, bắt đầu tại [quickstart.md](quickstart.md) thay vào đó.

## Cổng học viên

URL: `https://<cong-cua-ban>/`

### Tra cứu chứng chỉ

1. Chọn chế độ tra cứu từ dropdown. Các chế độ khả dụng phụ thuộc vào cấu hình `features.student_search_modes` của deploy; lựa chọn phổ biến:
   - **Tên + ngày sinh** — mặc định cho hầu hết deploy
   - **Tên + số báo danh (SBD)** — khi ban tổ chức chỉ cấp SBD, không cấp ngày sinh
   - **SBD + số điện thoại** — khi quy tắc riêng tư yêu cầu tự chứng minh liên hệ
2. Điền form. So khớp tên không phân biệt dấu (`Nguyễn` khớp với `nguyen`). Ngày sinh chấp nhận `DD/MM/YYYY` hoặc `YYYY-MM-DD`.
3. Giải CAPTCHA toán học bên dưới form. Bấm **Làm mới** nếu số bị mờ.
4. Bấm **Tìm kiếm**. Nếu tìm thấy khớp, trang hiển thị nút **Tải chứng chỉ**.

### Tải về

Bấm **Tải chứng chỉ**. Trình duyệt lưu file PDF tên `<ten-ban>-<round>.pdf`. Nếu xác thực QR được bật trên cổng này, PDF nhúng QR đã ký liên kết đến trang Xác thực — bất kỳ ai quét nó đều chuyển thẳng đến kết quả xác thực.

### Khắc phục sự cố

| Triệu chứng | Thử cách gì |
| --- | --- |
| "Không tìm thấy" nhưng bạn đã đăng ký | Kiểm tra chính tả tên (dấu không bắt buộc, nhưng lỗi đánh máy có vấn đề). Xác nhận định dạng ngày sinh. Thử chế độ tra cứu khác nếu có. |
| "Quá nhiều lần thử" | Đợi đến hết cooldown hiển thị (thường 60 giây). Giới hạn tốc độ theo IP + session; reload trang không reset. |
| CAPTCHA cứ báo sai | Làm mới CAPTCHA. Mỗi CAPTCHA chỉ dùng một lần; submit hai lần mà không refresh sẽ fail lần thứ hai. |
| Tải bắt đầu nhưng file 0 byte | Server render lỗi. Liên hệ ban tổ chức — đây là lỗi template / font ở phía họ, không phải của bạn. |

## Trang quản trị

URL: `https://<cong-cua-ban>/admin`

Truy cập yêu cầu tài khoản admin. Có ba chế độ login; cấu hình `admin.auth_mode` của deploy quyết định bạn thấy chế độ nào:

- **password** — email + mật khẩu được cấp. Mật khẩu super-admin mặc định được set qua `ADMIN_DEFAULT_PASSWORD` khi boot lần đầu; đổi ngay lập tức.
- **otp** — nhập email, nhận mã 6 số, paste lại. Mã hết hạn sau 5 phút.
- **magic_link** — nhập email, nhận link một-click. Link hết hạn sau 15 phút và chỉ dùng một lần.

Session lưu trong `sessionStorage` và hết hạn sau TTL của JWT (mặc định 8 giờ). Đóng tab trình duyệt là đăng xuất.

### Tra cứu học viên (chế độ admin)

Tìm theo **SBD** only — tra cứu admin bỏ qua so khớp tên không phân biệt dấu của student. Kết quả hiển thị mọi field trong record, kể cả field bị loại khỏi cổng học viên qua `features.student_fields`.

### Cập nhật hồ sơ

Nếu role của bạn là `super-admin` hoặc `admin` (không phải `viewer`), card kết quả có nút **Sửa** cho các trường editable trong `admin.editable_fields`. Cập nhật được lưu vào KV store dưới dạng override — dữ liệu ingest gốc giữ nguyên.

Mỗi lần ghi đều được log vào activity log (SQLite local + tùy chọn forward webhook Google Sheets). Bạn không thể xóa entry log từ UI.

### Theo dõi vận chuyển

Nếu `features.shipment.enabled` là true, trang admin hiển thị form shipment:

1. Nhập SBD, status (từ danh sách cấu hình, ví dụ `packed` / `in_transit` / `delivered`), và các field mở rộng (`tracking_number`, `carrier`, `notes`, …).
2. Submit. Record được upsert — cùng SBD + round sẽ update row hiện có.

Người nhận tra cứu trạng thái vận chuyển trên cổng học viên (nếu `features.shipment.public_fields` có expose cột) qua cùng lookup được CAPTCHA bảo vệ.

### Đăng xuất

Bấm **Đăng xuất** trên header. JWT được xóa khỏi `sessionStorage` và một revocation server-side được ghi lại. Ngay cả khi ai đó copy token, request sau đó vẫn fail.

## Trang xác thực

URL: `https://<cong-cua-ban>/certificate-checker`

### Xác thực một QR blob

Ba cách đến trang này:

1. **Quét QR** trên chứng chỉ in → URL mở với `?blob=<...>` pre-fill → trang auto-submit → kết quả hiện ngay.
2. **Bấm link QR** trong PDF số → cùng flow auto-submit.
3. **Paste blob thủ công** — hữu ích khi người nhận chỉ gửi chuỗi blob (ví dụ qua email). Paste vào textarea, bấm **Xác thực**.

### Đọc kết quả

- **Hợp lệ** (badge xanh) — chữ ký xác thực với khóa công khai của cổng, payload đúng cấu trúc, và nếu có TTL cấu hình (`features.qr_verify.max_age_seconds`), chứng chỉ chưa hết hạn. Dưới badge: tên người nhận, round, kết quả, ngày cấp.
- **Bị tamper** (badge đỏ) — chữ ký không xác thực. Hoặc QR bị sửa, blob bị hỏng khi truyền, hoặc chứng chỉ được ký bởi cổng khác. Không chấp nhận chứng chỉ là thật.
- **Hết hạn** (badge vàng) — chữ ký hợp lệ nhưng TTL đã qua. Chứng chỉ từng là thật nhưng ban tổ chức đánh dấu ngắn hạn (ví dụ offer học bổng). Yêu cầu người nhận bản mới.

### Checker KHÔNG làm gì

- Không truy vấn database student của cổng. Xác thực thuần mật mã: khóa công khai nhúng trong trang xác thực chữ ký. Bạn có thể xác thực blob offline một khi trang đã load.
- Không xác nhận trạng thái hiện tại của người nhận (đang học, đã tốt nghiệp, bị thu hồi). QR là snapshot tại thời điểm cấp.
- Không tiết lộ dữ liệu ngoài những gì được ký vào payload — thường chỉ tên + round + kết quả + ngày cấp. Các field riêng tư (DOB, điện thoại, email) không bao giờ nằm trong QR.

## Lưu ý riêng tư cho người nhận

- CAPTCHA, OTP, và magic-link token đều chỉ dùng một lần. Nếu bạn submit form hai lần, lần thứ hai sẽ fail — đây là có chủ đích.
- Truy vấn tra cứu của bạn được rate-limit theo IP. Cổng log nỗ lực tra cứu (không log nội dung) để phát hiện lạm dụng.
- QR trên chứng chỉ chỉ chứa các field mà ban tổ chức chọn ký. Nó được ký, không được mã hóa — bất kỳ ai cũng có thể đọc field bằng cách decode blob. Nếu không muốn field nào công khai từ QR, yêu cầu ban tổ chức loại nó khỏi `features.qr_verify.payload_fields`.

## Báo lỗi

Phát hiện bug trong hành vi cổng? Liên hệ ban tổ chức. Nếu bạn là ban tổ chức và nghi ngờ bug trong toolkit, xem file `SECURITY.md` ở gốc repo để có liên hệ threat-model, hoặc mở issue tại repo.
