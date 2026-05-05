/* qr-decode-helper.js — small wrapper around jsQR for the certificate-checker page.
 * Exposes window.LvtQR.decode(imageData) -> blobString | null.
 * If the QR encodes a URL with ?blob=... it returns just the blob value;
 * otherwise it returns the raw decoded text.
 *
 * Depends on jsQR being loaded first (sets window.jsQR).
 */
(function () {
  "use strict";
  var jsqrWarned = false;
  function decode(imageData) {
    if (typeof window.jsQR !== "function") {
      if (!jsqrWarned) {
        // Helps operators notice the vendor file is missing without
        // spamming the console once per click.
        if (window.console && console.warn) {
          console.warn("LvtQR: jsqr.min.js not loaded — QR upload disabled.");
        }
        jsqrWarned = true;
      }
      return null;
    }
    var code = window.jsQR(imageData.data, imageData.width, imageData.height, {
      inversionAttempts: "dontInvert",
    });
    if (!code || !code.data) return null;
    try {
      var url = new URL(code.data);
      var blob = url.searchParams.get("blob");
      return blob || code.data;
    } catch (_) {
      return code.data;
    }
  }
  window.LvtQR = { decode: decode };
})();
