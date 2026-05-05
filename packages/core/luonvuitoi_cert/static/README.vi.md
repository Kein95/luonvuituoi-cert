# Static assets

Các file trong thư mục này được dispatcher phục vụ tại `/static/<name>` với
`Content-Type: application/javascript` (hoặc MIME tương ứng).

## Vendor file `jsqr.min.js`

`jsqr.min.js` **không** được commit để giữ repo gọn. Để bật tính năng
upload ảnh QR trên trang Certificate-Checker, drop file vào đây:

```
packages/core/luonvuitoi_cert/static/jsqr.min.js
```

Nguồn: [jsQR v1.4.0](https://github.com/cozmo/jsQR) — Apache-2.0.
Link tải trực tiếp: <https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.min.js>
(~45 KB).

Khi vắng file, nút upload tự ẩn ở client; luồng dán tay vẫn hoạt động bình thường.
