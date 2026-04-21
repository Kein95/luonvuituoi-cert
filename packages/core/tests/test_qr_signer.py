"""Tests for :mod:`luonvuitoi_cert.qr.signer` and :mod:`luonvuitoi_cert.qr.codec`."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from luonvuitoi_cert.qr import (
    CodecError,
    QRPayload,
    SignatureError,
    decode_blob,
    encode_blob,
    load_private_key,
    load_public_key,
    render_qr_png,
    sign_payload,
    verify_payload,
)


@pytest.fixture
def keypair(tmp_path: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = tmp_path / "private_key.pem"
    pub = tmp_path / "public_key.pem"
    priv.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    pub.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return priv, pub


def _payload() -> QRPayload:
    return QRPayload(
        project_slug="demo",
        round_id="main",
        subject_code="S",
        result="GOLD",
        sbd="12345",
        issued_at=1_700_000_000,
    )


def test_sign_verify_roundtrip(keypair: tuple[Path, Path]) -> None:
    priv, pub = keypair
    sig = sign_payload(load_private_key(priv), _payload())
    verify_payload(load_public_key(pub), _payload(), sig)


def test_tampered_payload_rejected(keypair: tuple[Path, Path]) -> None:
    priv, pub = keypair
    sig = sign_payload(load_private_key(priv), _payload())
    tampered = QRPayload(project_slug="demo", round_id="main", subject_code="S", result="SILVER", sbd="12345", issued_at=1_700_000_000)
    with pytest.raises(SignatureError):
        verify_payload(load_public_key(pub), tampered, sig)


def test_wrong_key_rejects(keypair: tuple[Path, Path], tmp_path: Path) -> None:
    priv, _ = keypair
    sig = sign_payload(load_private_key(priv), _payload())
    # Generate a fresh keypair to provide a mismatched public key.
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pub = tmp_path / "other_pub.pem"
    other_pub.write_bytes(
        other.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    with pytest.raises(SignatureError):
        verify_payload(load_public_key(other_pub), _payload(), sig)


def test_load_missing_key_raises(tmp_path: Path) -> None:
    with pytest.raises(SignatureError, match="not found"):
        load_private_key(tmp_path / "absent.pem")
    with pytest.raises(SignatureError, match="not found"):
        load_public_key(tmp_path / "absent.pem")


def test_load_invalid_pem(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.pem"
    bogus.write_bytes(b"-----BEGIN RSA PRIVATE KEY-----\ngarbage\n-----END RSA PRIVATE KEY-----\n")
    with pytest.raises(SignatureError):
        load_private_key(bogus)


def test_encode_decode_roundtrip(keypair: tuple[Path, Path]) -> None:
    priv, pub = keypair
    sig = sign_payload(load_private_key(priv), _payload())
    blob = encode_blob(_payload(), sig)
    payload_out, sig_out = decode_blob(blob)
    assert payload_out == _payload()
    verify_payload(load_public_key(pub), payload_out, sig_out)


def test_decode_rejects_empty_segments() -> None:
    with pytest.raises(CodecError, match="empty"):
        decode_blob("")
    with pytest.raises(CodecError, match="empty"):
        decode_blob(".abc")


def test_decode_rejects_missing_separator() -> None:
    with pytest.raises(CodecError, match="separator"):
        decode_blob("abcdefnosig")


def test_decode_rejects_bad_base64() -> None:
    with pytest.raises(CodecError):
        decode_blob("!!!.!!!!")


def test_render_qr_png_produces_image() -> None:
    png = render_qr_png("hello world")
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 100


def test_payload_canonical_json_is_byte_stable() -> None:
    p1 = _payload()
    p2 = _payload()
    assert p1.to_canonical_json() == p2.to_canonical_json()
