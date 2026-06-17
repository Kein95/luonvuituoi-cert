# Hướng dẫn người dùng cuối

Cách sử dụng ba giao diện mà một cổng đã triển khai hiển thị. Tài liệu không kèm ảnh chụp màn hình; các trang đều là HTML đơn giản, dễ tiếp cận, không có yếu tố thương hiệu nào ngoài các biến CSS bạn cấu hình.

## Ai nên đọc trang này

- **Người nhận** (học viên, thí sinh, người được khen thưởng): xem phần [Cổng học viên](#cong-hoc-vien).
- **Người vận hành** (ban tổ chức, admin khóa học): xem phần [Trang quản trị](#trang-quan-tri).
- **Bên thứ ba** (nhà tuyển dụng, trường học, bất kỳ ai cần xác thực chứng chỉ): xem phần [Trang xác thực](#trang-xac-thuc).

Nếu bạn là lập trình viên đang triển khai cổng, hãy bắt đầu tại [quickstart.md](quickstart.md).

## Cổng học viên

URL: `https://<cong-cua-ban>/`

### Tra cứu chứng chỉ

1. Chọn chế độ tra cứu từ danh sách thả xuống. Các chế độ khả dụng phụ thuộc vào cấu hình `features.student_search_modes` của bản triển khai; những lựa chọn phổ biến:
   - **Tên và ngày sinh**: mặc định cho hầu hết bản triển khai.
   - **Tên và số báo danh (SBD)**: dùng khi ban tổ chức chỉ cấp SBD mà không cấp ngày sinh.
   - **SBD và số điện thoại**: dùng khi quy tắc riêng tư yêu cầu người tra cứu tự chứng minh thông tin liên hệ.
2. Điền vào form. Việc so khớp tên không phân biệt dấu (`Nguyễn` khớp với `nguyen`). Ngày sinh chấp nhận định dạng `DD/MM/YYYY` hoặc `YYYY-MM-DD`.
3. Giải CAPTCHA dạng toán bên dưới form. Bấm **Làm mới** nếu các con số bị mờ.
4. Bấm **Tìm kiếm**. Nếu tìm thấy kết quả khớp, trang sẽ hiển thị nút **Tải chứng chỉ**.

### Tải về

Bấm **Tải chứng chỉ**. Trình duyệt lưu file PDF với tên `<ten-ban>-<round>.pdf`. Nếu cổng này bật xác thực QR, file PDF sẽ nhúng mã QR đã ký liên kết tới trang Xác thực; bất kỳ ai quét mã đều được chuyển thẳng đến kết quả xác thực.

### Khắc phục sự cố

| Triệu chứng | Nên thử cách gì |
| --- | --- |
| "Không tìm thấy" dù bạn đã đăng ký | Kiểm tra lại chính tả của tên (không bắt buộc dấu, nhưng lỗi đánh máy thì có ảnh hưởng). Xác nhận đúng định dạng ngày sinh. Thử chế độ tra cứu khác nếu có. |
| "Quá nhiều lần thử" | Đợi hết khoảng thời gian chờ hiển thị trên màn hình (thường 60 giây). Giới hạn tần suất tính theo IP và session; việc tải lại trang không đặt lại bộ đếm. |
| CAPTCHA cứ báo sai | Làm mới CAPTCHA. Mỗi CAPTCHA chỉ dùng được một lần; gửi hai lần mà không làm mới thì lần thứ hai sẽ thất bại. |
| Bắt đầu tải nhưng file 0 byte | Server gặp lỗi khi render. Hãy liên hệ ban tổ chức; đây là lỗi template hoặc font ở phía họ, không phải lỗi của bạn. |

## Trang quản trị

URL: `https://<cong-cua-ban>/admin`

Truy cập yêu cầu tài khoản admin. Có ba chế độ đăng nhập; cấu hình `admin.auth_mode` của bản triển khai quyết định bạn thấy chế độ nào:

- **password**: đăng nhập bằng email và mật khẩu được cấp. Mật khẩu super-admin mặc định được đặt qua `ADMIN_DEFAULT_PASSWORD` ở lần khởi động đầu tiên; hãy đổi ngay lập tức.
- **otp**: nhập email, nhận mã 6 số rồi dán lại. Mã hết hạn sau 5 phút.
- **magic_link**: nhập email, nhận một liên kết bấm một lần là vào. Liên kết hết hạn sau 15 phút và chỉ dùng được một lần.

Session lưu trong `sessionStorage` và hết hạn theo TTL của JWT (mặc định 8 giờ). Đóng tab trình duyệt đồng nghĩa với đăng xuất.

### Tra cứu học viên (chế độ admin)

Chỉ tìm theo **SBD**; tra cứu admin bỏ qua cơ chế so khớp tên không phân biệt dấu của học viên. Kết quả hiển thị mọi trường trong bản ghi, kể cả những trường đã bị ẩn khỏi cổng học viên qua `features.student_fields`.

### Cập nhật hồ sơ

Nếu vai trò của bạn là `super-admin` hoặc `admin` (không phải `viewer`), thẻ kết quả sẽ có nút **Sửa** cho các trường có thể chỉnh sửa khai báo trong `admin.editable_fields`. Bản cập nhật được lưu vào KV store dưới dạng ghi đè, còn dữ liệu nhập gốc vẫn giữ nguyên.

Mỗi lần ghi đều được lưu vào activity log (SQLite cục bộ và tùy chọn chuyển tiếp qua webhook Google Sheets). Bạn không thể xóa bản ghi log từ giao diện.

### Theo dõi vận chuyển

Nếu `features.shipment.enabled` là true, trang admin hiển thị form shipment:

1. Nhập SBD, trạng thái (chọn từ danh sách cấu hình, ví dụ `packed`, `in_transit`, `delivered`) và các trường mở rộng (`tracking_number`, `carrier`, `notes`, và tương tự).
2. Gửi đi. Bản ghi được upsert: cùng SBD và round sẽ cập nhật vào dòng hiện có.

Người nhận tra cứu trạng thái vận chuyển trên cổng học viên (nếu `features.shipment.public_fields` có để lộ cột) qua cùng cơ chế tra cứu được CAPTCHA bảo vệ.

### Đăng xuất

Bấm **Đăng xuất** trên thanh tiêu đề. JWT bị xóa khỏi `sessionStorage` và một bản ghi thu hồi phía server được lưu lại. Ngay cả khi ai đó sao chép được token, các request sau đó vẫn thất bại.

## Trang xác thực

URL: `https://<cong-cua-ban>/certificate-checker`

### Xác thực một QR blob

Ba cách đến trang này:

1. **Quét QR** trên chứng chỉ in: URL mở ra với `?blob=<...>` được điền sẵn, trang tự gửi và kết quả hiện ngay.
2. **Bấm liên kết QR** trong PDF số: theo cùng luồng tự gửi như trên.
3. **Dán blob thủ công**: hữu ích khi người nhận chỉ gửi chuỗi blob (ví dụ qua email). Dán vào ô văn bản rồi bấm **Xác thực**.

### Đọc kết quả

- **Hợp lệ** (badge xanh): chữ ký khớp với khóa công khai của cổng, payload đúng cấu trúc, và nếu có cấu hình TTL (`features.qr_verify.max_age_seconds`) thì chứng chỉ chưa hết hạn. Bên dưới badge là tên người nhận, round, kết quả và ngày cấp.
- **Bị can thiệp** (badge đỏ): chữ ký không hợp lệ. Có thể QR đã bị sửa, blob bị hỏng khi truyền, hoặc chứng chỉ được ký bởi một cổng khác. Không nên công nhận chứng chỉ này là thật.
- **Hết hạn** (badge vàng): chữ ký hợp lệ nhưng TTL đã qua. Chứng chỉ từng là thật nhưng ban tổ chức đặt thời hạn ngắn (ví dụ thư mời học bổng). Hãy yêu cầu người nhận một bản mới.

### Trang xác thực KHÔNG làm gì

- Không truy vấn cơ sở dữ liệu học viên của cổng. Việc xác thực hoàn toàn dựa trên mật mã: khóa công khai được nhúng sẵn trong trang để kiểm tra chữ ký. Bạn có thể xác thực blob ngoại tuyến một khi trang đã tải xong.
- Không xác nhận trạng thái hiện tại của người nhận (đang học, đã tốt nghiệp, bị thu hồi). QR chỉ là một bản chụp tại thời điểm cấp.
- Không tiết lộ dữ liệu nào ngoài những gì đã ký vào payload, thường chỉ gồm tên, round, kết quả và ngày cấp. Các trường riêng tư (ngày sinh, điện thoại, email) không bao giờ nằm trong QR.

## Lưu ý riêng tư cho người nhận

- CAPTCHA, OTP và magic link token đều chỉ dùng một lần. Nếu bạn gửi form hai lần, lần thứ hai sẽ thất bại; đây là điều cố ý.
- Mỗi truy vấn tra cứu của bạn bị giới hạn tần suất theo IP. Cổng có ghi lại các lần tra cứu (không ghi nội dung) để phát hiện lạm dụng.
- QR trên chứng chỉ chỉ chứa những trường mà ban tổ chức chọn để ký. Mã này được ký chứ không được mã hóa, nên bất kỳ ai cũng có thể đọc các trường bằng cách giải mã blob. Nếu không muốn trường nào bị công khai qua QR, hãy yêu cầu ban tổ chức loại nó khỏi `features.qr_verify.payload_fields`.

## Báo lỗi

Phát hiện lỗi trong hành vi của cổng? Hãy liên hệ ban tổ chức. Nếu bạn là ban tổ chức và nghi ngờ có lỗi trong toolkit, xem file `SECURITY.md` ở gốc repo để biết đầu mối liên hệ về threat model, hoặc mở issue tại repo.
