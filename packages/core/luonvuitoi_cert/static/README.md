# Static assets

Files in this directory are served by the dispatcher under `/static/<name>`
with `Content-Type: application/javascript` (or matching MIME).

## Vendoring jsqr.min.js

`jsqr.min.js` is **not committed** to keep the repo clean. To enable QR
image upload on the Certificate-Checker page, drop the file here:

```
packages/core/luonvuitoi_cert/static/jsqr.min.js
```

Source: [jsQR v1.4.0](https://github.com/cozmo/jsQR) — Apache-2.0.
Direct download: <https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.min.js>
(~45 KB).

When the file is absent, the upload button is hidden client-side; the
manual paste flow keeps working.
