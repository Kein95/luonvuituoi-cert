# Hướng dẫn PDF overlay

Cách LUONVUITUOI-CERT biến PDF template + một row học viên thành chứng chỉ tải được.

## Mô hình tư duy

**Template** của bạn là PDF nhiều trang. Mỗi trang là một biến thể chứng chỉ trống — một trang cho mỗi combo (môn, kết quả). Engine vẽ tên / trường / lớp / v.v. của học viên lên trên, tại tọa độ bạn chỉ định trong `cert.config.json#layout.fields`.

```
templates/main.pdf
├── trang 1 — background giải Vàng (chưa có tên, trường)
├── trang 2 — background giải Bạc
└── trang 3 — background giải Đồng
                                 ↓   + overlay
                               final.pdf  (một trang, có dữ liệu học viên)
```

## Hệ tọa độ

Points (1/72 inch). Gốc là **góc dưới-trái** của trang — theo convention reportlab. Trang A5 landscape là `(842, 595)`; "một inch từ dưới lên" là `y = 72`.

`layout.page_size` trong config là hint cho author — renderer dùng MediaBox thực của trang template, nên nếu hai giá trị khác nhau, template thắng.

## Spec field

```jsonc
"fields": {
  "name": {
    "x": 421, "y": 330,
    "font": "script",
    "size": 44,
    "color": "#1E3A8A",
    "align": "center"
  },
  "school": {
    "x": 421, "y": 265,
    "font": "serif",
    "size": 18,
    "align": "center",
    "wrap": 60
  }
}
```

| Key | Ý nghĩa |
|-----|---------|
| `x`, `y` | Vị trí baseline text. Cho `align: center` / `right`, x là cạnh giữa/phải. |
| `font` | Key vào registry `fonts` top-level. |
| `size` | Size font theo points. |
| `color` | Chuỗi hex; default `#000000`. |
| `align` | `left`, `center`, `right`. |
| `wrap` | Int tùy chọn. Trigger word-wrap ngây thơ tại số ký tự cho trước. Text nhiều dòng flow **xuống** từ `y` với leading 1.2×. |

## Tên field

Các field built-in engine populate từ `data_mapping`:

| Field layout | Nguồn |
|--------------|-------|
| `name` | `data_mapping.name_col` |
| `dob`, `school`, `grade`, `phone` | `data_mapping.*_col` tương ứng nếu khai báo |
| Bất cứ gì trong `data_mapping.extra_cols` | Cột DB cùng tên |

Field khai báo trong `layout.fields` mà handler không fill sẽ bị skip im lặng; giá trị extra trong dict handler không khớp field layout nào sẽ bị drop. Có nghĩa thêm cột mới vào Excel nguồn và khai báo trong `data_mapping.extra_cols` là đủ để render — không cần thay đổi handler.

## Vị trí QR

`features.qr_verify.{x, y, size_pt}` chỉ định nơi QR đã ký được vẽ. Tọa độ là góc dưới-trái của QR square; `size_pt` là độ dài cạnh. Vị trí phổ biến là góc dưới-phải:

```json
"qr_verify": { "enabled": true, "x": 720, "y": 40, "size_pt": 80 }
```

## Workflow authoring

1. Thiết kế template trống trong tool bạn chọn (InDesign, Figma → PDF, LibreOffice, Canva). Một trang mỗi ô giải thưởng.
2. Mở PDF trong viewer show tọa độ (Preview trên macOS, hầu hết PDF editor, hoặc drop vào reportlab để vẽ crosshair tại vị trí biết trước).
3. Ước lượng baseline nơi muốn tên ngồi. Thử `"y": page_height / 2`, rồi chỉnh ±10 points cho đến khi trông đúng.
4. Chạy `lvt-cert dev` và hit `/` với học viên seed; tải PDF và kiểm tra.
5. Lặp tọa độ cho đến khi layout landed.

## Input safety

- Giá trị single field cap ở 1000 ký tự (`MAX_FIELD_LENGTH`). Input oversize raise `OverlayError` để row DB độc hại không thể làm phồng PDF render.
- Giá trị chỉ whitespace bị skip (không overlay trống).
- Giá trị non-string bị coerce qua `str()` sau check length — số, boolean, v.v. render như dạng string.

## Fonts

Ship font TrueType có license cho redistribute (SIL OFL, Apache 2.0, v.v.). Đặt `.ttf` tại path khai báo trong `fonts.<key>`; registry đăng ký font với reportlab khi dùng lần đầu và cache theo path đã resolve để hai project trong cùng process dùng chung key nhưng khác file không bị va chạm.

## Những gì engine KHÔNG làm

- Không shape vector / layout kiểu CSS — PDF là design; engine chỉ overlay text.
- Không fill form-field PDF. Dùng cách template-as-background.
- Không hyphen. `wrap` chỉ break theo space.
- Không overlay ảnh ngoài QR — drop logo vào template.

Cho chứng chỉ nhiều trang hoặc watermark, post-process output engine với `pypdf` trong handler custom.
