# Static assets

Các file trong thư mục này được dispatcher phục vụ tại `/static/<name>` với
`Content-Type: application/javascript` (hoặc MIME tương ứng).

## File vendor `jsqr.min.js`

`jsqr.min.js` được vendor sẵn tại `packages/core/luonvuitoi_cert/static/jsqr.min.js`
để chức năng upload ảnh QR trên trang Certificate-Checker chạy offline,
không phụ thuộc CDN allowlist.

Nguồn: [jsQR v1.4.0](https://github.com/cozmo/jsQR), giấy phép Apache-2.0
(minified bởi jsDelivr, ~127 KB).

Muốn đổi sang phiên bản mới: thay file bằng bản build từ
`https://cdn.jsdelivr.net/npm/jsqr@{version}/dist/jsQR.min.js` và cập nhật
comment header trong file.

Nếu xoá file, nút upload tự ẩn ở client; luồng dán tay vẫn hoạt động bình thường.
