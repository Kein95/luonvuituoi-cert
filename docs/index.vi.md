---
hide:
  - navigation
  - toc
---

<p class="lvt-credits">🤝 Đồng đội <a href="https://github.com/Liamlenguyen" target="_blank" rel="noopener">@Liamlenguyen</a> — hãy đón chờ những bản colab tiếp theo từ <strong>LUONVUITUOI TEAM</strong> ✨<br>
📧 <a href="mailto:htkien95@gmail.com">htkien95@gmail.com</a> &nbsp;·&nbsp; 📱 <a href="tel:+84348635408">+84 348 635 408</a></p>

<div class="lvt-hero" markdown>

<img src="../assets/logo.svg" alt="Logo LUONVUITUOI-CERT" class="lvt-hero-logo">

# LUONVUITUOI-CERT

<p class="lvt-hero-tagline">
Bộ công cụ cổng chứng chỉ theo cấu hình. Mang theo file PDF mẫu và danh sách học viên của bạn — nhận ngay một cổng tra cứu, tải về, xác thực QR và trang quản trị chỉ trong vài phút.
</p>

<div class="lvt-cta-row">
  <a href="quickstart/" class="lvt-btn lvt-btn-primary">🚀 Bắt đầu nhanh (10 phút)</a>
  <a href="https://github.com/Kein95/luonvuituoi-cert" class="lvt-btn lvt-btn-ghost" target="_blank" rel="noopener">⭐ Xem trên GitHub</a>
</div>

<div class="lvt-badges">
  <img src="https://img.shields.io/github/v/release/Kein95/luonvuituoi-cert?style=flat-square&color=0d6e6e&label=release" alt="release">
  <img src="https://img.shields.io/github/license/Kein95/luonvuituoi-cert?style=flat-square&color=0d6e6e" alt="license">
  <img src="https://img.shields.io/github/actions/workflow/status/Kein95/luonvuituoi-cert/test.yml?style=flat-square&color=0d6e6e&label=tests" alt="tests">
  <img src="https://img.shields.io/github/stars/Kein95/luonvuituoi-cert?style=flat-square&color=fbbf24" alt="stars">
</div>

</div>

## Tại sao cần công cụ này?

Bạn đang tổ chức một cuộc thi, trao chứng chỉ cho học viên, hoặc phát bằng hoàn thành khóa học? Thông thường bạn cần một trang công khai để người nhận tra cứu và tải PDF, một trang quản trị để quản lý dữ liệu, và một trang xác thực để bên thứ ba kiểm tra tính xác thực. **LUONVUITUOI-CERT cung cấp cả ba**, deploy được lên Vercel free tier hoặc bất kỳ Docker host nào, không cần viết code thừa.

<div class="lvt-features" markdown>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🎨</span>
### Dùng template riêng của bạn
Đưa file PDF + tọa độ vào. Engine tự động overlay tên học viên, ngày cấp và mã QR chính xác từng pixel — không cần thiết kế lại.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🔍</span>
### Cổng tra cứu công khai
Người nhận tìm theo tên hoặc số báo danh, xem trước chứng chỉ, tải PDF đã ký. Tối ưu mobile-first, hỗ trợ đa ngôn ngữ.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🔐</span>
### Trang quản trị có sẵn
Quản lý hồ sơ, sửa lỗi, theo dõi vận chuyển, audit log. Bảo vệ bằng JWT + giới hạn tốc độ truy cập.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">📱</span>
### Xác thực QR
Mỗi chứng chỉ gắn mã QR dẫn đến trang xác thực công khai — bên thứ ba xác minh chỉ bằng một lần quét.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">⚡</span>
### Triển khai bất cứ đâu
Deploy Vercel một lệnh (free tier), Dockerfile production-ready, docker-compose — bạn chọn hạ tầng.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">📦</span>
### Cấu hình thay vì code
Một file `cert.config.json` điều khiển mọi thứ: branding, fields, tọa độ overlay, auth, shipment. Không cần fork repo.
</div>

</div>

<div class="lvt-stats" markdown>

<div class="lvt-stat">
<div class="lvt-stat-num">10 phút</div>
<div class="lvt-stat-label">Deploy lần đầu</div>
</div>

<div class="lvt-stat">
<div class="lvt-stat-num">0</div>
<div class="lvt-stat-label">Code thừa</div>
</div>

<div class="lvt-stat">
<div class="lvt-stat-num">$0</div>
<div class="lvt-stat-label">Vercel free tier</div>
</div>

<div class="lvt-stat">
<div class="lvt-stat-num">MIT</div>
<div class="lvt-stat-label">License</div>
</div>

</div>

## Kiến trúc

```mermaid
flowchart LR
    A[cert.config.json] --> B[Python serverless API]
    B --> C[Cổng học viên<br/>/ + /verify]
    B --> D[Trang quản trị<br/>/admin]
    B --> E[(SQLite<br/>students)]
    B --> F[(KV backend<br/>overrides)]
    C -.quét QR.-> G[Trang xác thực]

    style A fill:#fbbf24,stroke:#d97706,color:#0f172a
    style B fill:#0d6e6e,stroke:#0a5757,color:#fff
    style C fill:#14b8a6,stroke:#0d6e6e,color:#fff
    style D fill:#14b8a6,stroke:#0d6e6e,color:#fff
    style G fill:#ccfbf1,stroke:#0d6e6e,color:#0a5757
```

## Bước tiếp theo

<div class="lvt-features" markdown>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🚀</span>
### [Bắt đầu nhanh →](quickstart.md)
Deploy cổng đầu tiên trong 10 phút — CLI scaffold, tour cấu hình, chạy local.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🏛️</span>
### [Kiến trúc →](architecture.md)
Cách các thành phần ghép lại — handlers, transport, KV, ký số, model dữ liệu.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">⚙️</span>
### [Cấu hình →](config-reference.md)
Mọi trường `cert.config.json` + biến môi trường đều được tài liệu hóa.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🔐</span>
### [Bảo mật →](security.md)
Checklist hardening cho deploy production.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🛠️</span>
### [Vận hành →](operations.md)
Health probe, triage log, audit trail, checklist ứng cứu sự cố.
</div>

<div class="lvt-feature" markdown>
<span class="lvt-feature-icon">🧭</span>
### [Khắc phục sự cố →](troubleshooting.md)
Các lỗi thường gặp và nguyên nhân gốc.
</div>

</div>
