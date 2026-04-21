"""Serialize and deserialize the ``payload.signature`` blob, render QR PNGs.

Blob format::

    base64url(canonical_payload_json) . base64url(signature)

``.`` as a separator keeps the whole thing URL-safe so it works unescaped
inside QR codes and as a query parameter on the verifier URL.
"""

from __future__ import annotations

import base64
from io import BytesIO

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from luonvuitoi_cert.qr.payload import QRPayload

BLOB_SEPARATOR = "."


class CodecError(Exception):
    """Raised when a received blob is malformed, truncated, or wrong base64."""


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    try:
        return base64.urlsafe_b64decode(encoded + padding)
    except (ValueError, TypeError) as e:
        raise CodecError(f"invalid base64 segment: {e}") from e


def encode_blob(payload: QRPayload, signature: bytes) -> str:
    """Join the canonical payload and its signature into a URL-safe string."""
    return f"{_b64encode(payload.to_canonical_json())}{BLOB_SEPARATOR}{_b64encode(signature)}"


def decode_blob(blob: str) -> tuple[QRPayload, bytes]:
    """Inverse of :func:`encode_blob`. Raises :class:`CodecError` on any format issue."""
    if not blob or BLOB_SEPARATOR not in blob:
        raise CodecError("blob is empty or missing the payload.signature separator")
    payload_b64, sig_b64 = blob.split(BLOB_SEPARATOR, 1)
    if not payload_b64 or not sig_b64:
        raise CodecError("blob has an empty payload or signature segment")
    try:
        payload = QRPayload.from_json(_b64decode(payload_b64))
    except (KeyError, ValueError, TypeError) as e:
        raise CodecError(f"payload JSON could not be parsed: {e}") from e
    signature = _b64decode(sig_b64)
    return payload, signature


def render_qr_png(text: str, *, box_size: int = 10, border: int = 2) -> bytes:
    """Encode ``text`` as a PNG QR image. ``text`` is typically a URL wrapping the blob."""
    qr = qrcode.QRCode(
        version=None,  # auto-size based on payload
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(text)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
