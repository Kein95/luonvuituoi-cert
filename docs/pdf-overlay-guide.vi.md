# Hướng dẫn PDF overlay

Cách LUONVUITUOI-CERT biến một file PDF template cùng một dòng dữ liệu học viên thành chứng chỉ tải về được.

## Mô hình tư duy

**Template** của bạn là một file PDF nhiều trang. Mỗi trang là một biến thể chứng chỉ để trống, ứng với một tổ hợp (môn, kết quả). Engine sẽ vẽ tên, trường, lớp và các thông tin khác của học viên lên trên, tại đúng tọa độ bạn chỉ định trong `cert.config.json#layout.fields`.

```
templates/main.pdf
├── trang 1: nền giải Vàng (chưa có tên, trường)
├── trang 2: nền giải Bạc
└── trang 3: nền giải Đồng
                                 ↓   + overlay
                               final.pdf  (một trang, có dữ liệu học viên)
```

## Hệ tọa độ

Đơn vị là points (1/72 inch). Gốc tọa độ nằm tại **góc dưới bên trái** của trang, theo quy ước của reportlab. Trang A5 nằm ngang có kích thước `(842, 595)`; "một inch tính từ đáy lên" tương ứng `y = 72`.

`layout.page_size` trong config chỉ là gợi ý cho người thiết kế. Renderer dùng MediaBox thực tế của trang template, nên nếu hai giá trị khác nhau thì template được ưu tiên.

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
| `x`, `y` | Vị trí baseline của dòng chữ. Với `align: center` hoặc `right`, `x` là cạnh giữa hoặc cạnh phải. |
| `font` | Khóa trỏ tới registry `fonts` ở cấp cao nhất. |
| `size` | Cỡ chữ tính theo points. |
| `color` | Chuỗi màu hex; mặc định `#000000`. |
| `align` | Một trong `left`, `center`, `right`. |
| `wrap` | Số nguyên tùy chọn. Kích hoạt cơ chế xuống dòng đơn giản tại số ký tự cho trước. Văn bản nhiều dòng trải **xuống dưới** tính từ `y`, với khoảng cách dòng 1.2 lần. |

## Tên trường

Các trường dựng sẵn được engine điền từ `data_mapping`:

| Trường layout | Nguồn |
|--------------|-------|
| `name` | `data_mapping.name_col` |
| `dob`, `school`, `grade`, `phone` | `data_mapping.*_col` tương ứng, nếu có khai báo |
| Mọi mục trong `data_mapping.extra_cols` | Cột cơ sở dữ liệu cùng tên |

Trường khai báo trong `layout.fields` mà handler không điền sẽ bị bỏ qua trong im lặng; giá trị thừa trong dict của handler không khớp với trường layout nào sẽ bị loại bỏ. Nghĩa là chỉ cần thêm cột mới vào Excel nguồn rồi khai báo trong `data_mapping.extra_cols` là đủ để hiển thị, không cần sửa handler.

## Vị trí QR

`features.qr_verify.{x, y, size_pt}` chỉ định vị trí vẽ mã QR đã ký. Tọa độ là góc dưới bên trái của ô vuông QR; `size_pt` là độ dài cạnh. Vị trí phổ biến là góc dưới bên phải:

```json
"qr_verify": { "enabled": true, "x": 720, "y": 40, "size_pt": 80 }
```

## Quy trình thiết kế

1. Thiết kế template trống bằng công cụ bạn chọn (InDesign, Figma xuất ra PDF, LibreOffice, Canva). Mỗi ô giải thưởng một trang.
2. Mở PDF trong trình xem có hiển thị tọa độ (Preview trên macOS, đa số trình chỉnh sửa PDF, hoặc nạp vào reportlab để vẽ điểm ngắm tại vị trí đã biết).
3. Ước lượng baseline nơi muốn đặt tên. Thử `"y": page_height / 2`, sau đó chỉnh ±10 points cho đến khi trông vừa ý.
4. Chạy `lvt-cert dev`, truy cập `/` với học viên dữ liệu mẫu; tải PDF về và kiểm tra.
5. Lặp lại việc chỉnh tọa độ cho đến khi bố cục đã đúng vị trí.

## An toàn dữ liệu đầu vào

- Giá trị mỗi trường bị giới hạn ở 1000 ký tự (`MAX_FIELD_LENGTH`). Đầu vào quá dài sẽ làm phát sinh `OverlayError`, nhờ đó một dòng dữ liệu độc hại không thể làm phình to PDF khi render.
- Giá trị chỉ gồm khoảng trắng sẽ bị bỏ qua (không overlay phần trống).
- Giá trị không phải chuỗi sẽ được ép kiểu qua `str()` sau khi kiểm tra độ dài; số, boolean và các kiểu khác đều hiển thị dưới dạng chuỗi.

## Fonts

Toolkit đi kèm các font TrueType có giấy phép cho phép phân phối lại (SIL OFL, Apache 2.0 và tương tự). Đặt file `.ttf` tại đường dẫn khai báo trong `fonts.<key>`; registry sẽ đăng ký font với reportlab ở lần dùng đầu tiên và lưu cache theo đường dẫn đã phân giải, nhờ đó hai project trong cùng một process dùng chung một khóa nhưng trỏ tới file khác nhau sẽ không xung đột.

## Những việc engine KHÔNG làm

- Không tạo hình vector hay dàn trang kiểu CSS. Bản thân PDF là phần thiết kế; engine chỉ overlay chữ.
- Không điền vào trường biểu mẫu của PDF. Hãy dùng cách lấy template làm nền.
- Không tự ngắt từ bằng dấu gạch nối. `wrap` chỉ ngắt theo khoảng trắng.
- Không overlay hình ảnh nào ngoài QR. Hãy đặt logo trực tiếp vào template.

Với chứng chỉ nhiều trang hoặc cần đóng watermark, hãy hậu xử lý kết quả đầu ra của engine bằng `pypdf` trong một handler tùy chỉnh.
