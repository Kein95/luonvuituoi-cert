# Xác thực QR

Ký mỗi chứng chỉ đã tải về bằng chữ ký RSA-PSS-SHA256, nhúng QR quét được trên PDF, và expose trang công khai `/certificate-checker` validate chữ ký. Giúp bên thứ ba (nhà tuyển dụng, trường học) tin tưởng chứng chỉ in không bị tamper.

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

Rồi tạo cặp khóa:

```bash
lvt-cert gen-keys
```

- `private_key.pem` — signer. Không bao giờ commit; đối xử như mật khẩu DB.
- `public_key.pem` — an toàn để ship; verifier endpoint chỉ cần file này.

## Payload

Mỗi QR encode URL dạng:

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

Chỉ field non-sensitive — học viên giữ chứng chỉ in đã đọc được toàn bộ. Chữ ký ngăn *forgery*, không phải disclosure.

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

Khi fail: `valid: false` cộng `reason` cho user (`malformed QR payload`, `project mismatch`, `signature does not match payload`, `certificate expired`).

## Expiry

Set `max_age_seconds` non-zero nếu muốn cert ngừng verify sau một thời gian — revocation kiểu nghèo giúp bạn không phải chạy revocation list:

```json
"max_age_seconds": 31536000
```

= 1 năm. Request cũ hơn bị từ chối là expired. Cũng từ chối payload có date hơn 60 giây trong tương lai (guard clock skew).

## Bind project-slug

`payload.project_slug` được so sánh với `config.project.slug` **trước** khi xác thực chữ ký. Nếu hai cổng vô tình share public key, cert mint cho portal A không validate được với portal B — mismatch project_slug fail sớm.

## Không lớp Fernet / mã hóa

QR payload không được mã hóa. Portal cũ nội bộ từng stack Fernet lên trên để "defense in depth," nhưng threat model không justify: không có secret data trong payload. Chỉ chữ ký là đủ cho phát hiện tamper, và ta bỏ complexity. Nếu payload của bạn chứa field nhạy cảm, thêm mã hóa riêng ở handler layer.

## Lưu ý vận hành

- Key được reload từ disk mỗi verify request (không cache in-memory). Cost cold-start ~10 ms — chấp nhận được.
- `render_qr_png` cap text QR ở 2000 ký tự. Signed payload + URL wrapper thường ~500 ký tự.
- Renderer giữ crypto-agnostic — download handler làm signing + tạo PNG và truyền bytes vào engine qua `OverlayRequest.qr_png_bytes`.

## Testing

```bash
pytest -m e2e packages/core/tests/e2e/test_portal_flow.py::test_download_emits_pdf_with_qr_and_verifies
```

Ký payload trực tiếp, nhúng vào PDF tải về, extract blob, round-trip qua `/api/verify`, và assert `valid: true`.
