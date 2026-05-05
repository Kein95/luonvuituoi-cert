# Static assets

Files in this directory are served by the dispatcher under `/static/<name>`
with `Content-Type: application/javascript` (or matching MIME).

## Vendored jsqr.min.js

`jsqr.min.js` is vendored at `packages/core/luonvuitoi_cert/static/jsqr.min.js`
so the QR image upload on the Certificate-Checker page works offline /
without a CDN allowlist.

Source: [jsQR v1.4.0](https://github.com/cozmo/jsQR) — Apache-2.0
(minified by jsDelivr, ~127 KB).

To swap a newer release: replace the file with the build from
`https://cdn.jsdelivr.net/npm/jsqr@{version}/dist/jsQR.min.js` and bump
the comment header in the file.

If the file is removed, the upload button auto-hides client-side and the
manual paste flow keeps working.
