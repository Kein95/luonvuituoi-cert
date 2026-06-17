# Xác thực QR

Ký mỗi chứng chỉ tải về bằng chữ ký RSA-PSS-SHA256, nhúng mã QR quét được lên PDF, và cung cấp trang công khai `/certificate-checker` để kiểm tra chữ ký. Tính năng này giúp bên thứ ba (nhà tuyển dụng, trường học) tin tưởng rằng chứng chỉ in không bị can thiệp.

## Bật

```jsonc
"features": {
  "qr_verify": {
    "enabled": true,
    "x": 720, "y": 40, "size_pt": 80,
    "max_age_seconds": 0,
    "public_key_path": "public_key.pem",
    "private_key_path": "private_key.pem"
  }
}
```

Sau đó tạo cặp khóa:

```bash
lvt-cert gen-keys
```

- `private_key.pem`: khóa dùng để ký. Không bao giờ commit; hãy đối xử với nó như mật khẩu cơ sở dữ liệu.
- `public_key.pem`: an toàn để phân phối; endpoint xác thực chỉ cần file này.

## Payload

Mỗi QR mã hóa một URL có dạng:

```
https://mycerts.example/certificate-checker?blob=<base64url(payload)>.<base64url(signature)>
```

Payload là canonical-JSON object:

```json
{
  "project_slug": "demo-academy",
  "round_id":     "main",
  "subject_code": "G",
  "result":       "GOLD",
  "sbd":          "12345",
  "issued_at":    1700000000
}
```

Chỉ gồm các trường không nhạy cảm, vốn là những thông tin mà học viên cầm chứng chỉ in đã đọc được toàn bộ. Chữ ký nhằm ngăn *giả mạo*, không nhằm ngăn việc lộ thông tin.

## Xác thực

`/api/verify` chấp nhận `{"blob": "..."}` và trả:

```json
{
  "valid": true,
  "payload": {
    "project_slug": "demo-academy",
    "round_id": "main",
    "subject_code": "G",
    "result": "GOLD",
    "sbd": "12345",
    "issued_at": 1700000000
  }
}
```

Khi thất bại: trả về `valid: false` kèm `reason` để hiển thị cho người dùng (`malformed QR payload`, `project mismatch`, `signature does not match payload`, `certificate expired`).

## Hết hạn

Đặt `max_age_seconds` khác 0 nếu muốn chứng chỉ ngừng được xác thực sau một thời gian. Đây là cách thu hồi đơn giản, giúp bạn không phải duy trì một danh sách thu hồi:

```json
"max_age_seconds": 31536000
```

Giá trị này bằng 1 năm. Request cũ hơn ngưỡng sẽ bị từ chối vì hết hạn. Hệ thống cũng từ chối payload có thời điểm vượt quá 60 giây trong tương lai (để phòng lệch đồng hồ).

## Ràng buộc theo project slug

`payload.project_slug` được so sánh với `config.project.slug` **trước** khi xác thực chữ ký. Nếu hai cổng vô tình dùng chung khóa công khai, chứng chỉ phát hành cho cổng A vẫn không xác thực được với cổng B vì project slug không khớp sẽ bị loại từ sớm.

## Không có lớp Fernet hay mã hóa

Payload của QR không được mã hóa. Một cổng nội bộ cũ từng chồng thêm Fernet để "phòng thủ nhiều lớp", nhưng threat model không biện minh được điều đó: payload không chứa dữ liệu bí mật. Chỉ riêng chữ ký đã đủ để phát hiện can thiệp, nên chúng tôi loại bỏ phần phức tạp này. Nếu payload của bạn có chứa trường nhạy cảm, hãy thêm mã hóa riêng ở tầng handler.

## Lưu ý vận hành

- Khóa được nạp lại từ đĩa ở mỗi request xác thực (không lưu cache trong bộ nhớ). Chi phí khởi động lạnh khoảng 10 ms, ở mức chấp nhận được.
- `render_qr_png` giới hạn nội dung QR ở 2000 ký tự. Payload đã ký cùng phần URL bao quanh thường khoảng 500 ký tự.
- Renderer không phụ thuộc vào thành phần mật mã: download handler đảm nhận việc ký và tạo PNG, rồi truyền dữ liệu byte vào engine qua `OverlayRequest.qr_png_bytes`.

## Trải nghiệm trang xác thực: dán hay tải ảnh QR

Trang Certificate-Checker nhận payload của QR theo 2 cách:

1. **Dán**: sao chép URL mà QR đã mã hóa rồi dán vào ô văn bản. Cách này hoạt động trên mọi trình duyệt, không cần JS bổ trợ.
2. **🖼️ Tải ảnh QR lên**: chọn ảnh chụp màn hình hoặc ảnh chụp (PNG, JPG, WebP, tối đa 10 MB). Bộ giải mã `jsQR` chạy hoàn toàn trong trình duyệt; không byte ảnh nào được gửi lên server. Blob giải mã được sẽ tự điền vào ô văn bản rồi gửi đi.

Nút tải lên chỉ hiện khi người vận hành đã đặt sẵn file `jsqr.min.js` vào `packages/core/luonvuitoi_cert/static/jsqr.min.js` (khoảng 45 KB, giấy phép Apache-2.0, xem README trong thư mục đó). Khi thiếu file, nút sẽ bị ẩn và luồng dán tay vẫn hoạt động.

CSP: các script đặt sẵn được phục vụ tại `/static/<name>` với `Content-Type: application/javascript` và cache bất biến trong thời gian dài. Bộ điều phối từ chối path traversal (kết hợp regex tên file, danh sách MIME cho phép và ràng buộc `importlib.resources`). Cả 2 thẻ `<script>` đều mang CSP nonce theo từng request khi có.

## Kiểm thử

```bash
pytest -m e2e packages/core/tests/e2e/test_portal_flow.py::test_download_emits_pdf_with_qr_and_verifies
```

Bài kiểm thử ký payload trực tiếp, nhúng vào PDF tải về, trích xuất blob, gửi vòng lại qua `/api/verify`, rồi khẳng định `valid: true`.
