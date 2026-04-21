"""Tests for :mod:`luonvuitoi_cert.api.verify`."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from luonvuitoi_cert.api.verify import VerifyError, verify_qr
from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.qr import QRPayload, encode_blob, load_private_key, sign_payload


@pytest.fixture
def qr_project(tmp_path: Path) -> tuple[CertConfig, Path, Path]:
    """Return a QR-enabled config + project root with a real keypair on disk."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (tmp_path / "private_key.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (tmp_path / "public_key.pem").write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    config = CertConfig.model_validate(
        {
            "project": {"name": "Demo", "slug": "demo"},
            "rounds": [{"id": "main", "label": "Main", "table": "students", "pdf": "t.pdf"}],
            "subjects": [{"code": "S", "en": "S", "db_col": "s"}],
            "results": {"S": {"GOLD": 1}},
            "layout": {
                "page_size": [100, 100],
                "fields": {"n": {"x": 0, "y": 0, "font": "f", "size": 10, "align": "left"}},
            },
            "fonts": {"f": "f.ttf"},
            "features": {"qr_verify": {"enabled": True}},
        }
    )
    return config, tmp_path, tmp_path / "private_key.pem"


def _make_blob(config: CertConfig, priv_path: Path, **overrides) -> str:  # type: ignore[no-untyped-def]
    defaults = {
        "project_slug": config.project.slug,
        "round_id": "main",
        "subject_code": "S",
        "result": "GOLD",
        "sbd": "12345",
        "issued_at": 1_700_000_000,
    }
    defaults.update(overrides)
    payload = QRPayload(**defaults)
    signature = sign_payload(load_private_key(priv_path), payload)
    return encode_blob(payload, signature)


# ── Happy path ──────────────────────────────────────────────────────


def test_verify_valid_qr(qr_project) -> None:  # type: ignore[no-untyped-def]
    config, project_root, priv = qr_project
    blob = _make_blob(config, priv)
    resp = verify_qr(config=config, project_root=project_root, blob=blob)
    assert resp.valid
    assert resp.payload is not None
    assert resp.payload.sbd == "12345"


def test_response_to_json_safe(qr_project) -> None:  # type: ignore[no-untyped-def]
    config, project_root, priv = qr_project
    resp = verify_qr(config=config, project_root=project_root, blob=_make_blob(config, priv))
    data = resp.to_json_safe()
    assert data["valid"] is True
    assert data["payload"]["sbd"] == "12345"


# ── Failure modes ───────────────────────────────────────────────────


def test_missing_blob_returns_invalid(qr_project) -> None:  # type: ignore[no-untyped-def]
    config, project_root, _ = qr_project
    resp = verify_qr(config=config, project_root=project_root, blob="")
    assert not resp.valid
    assert resp.reason == "missing QR payload"


def test_malformed_blob_reported(qr_project) -> None:  # type: ignore[no-untyped-def]
    config, project_root, _ = qr_project
    resp = verify_qr(config=config, project_root=project_root, blob="no-separator-here")
    assert not resp.valid
    assert resp.reason is not None and "malformed" in resp.reason


def test_project_mismatch_is_tampered(qr_project) -> None:  # type: ignore[no-untyped-def]
    config, project_root, priv = qr_project
    blob = _make_blob(config, priv, project_slug="some-other-portal")
    resp = verify_qr(config=config, project_root=project_root, blob=blob)
    assert not resp.valid
    assert resp.reason is not None and "project mismatch" in resp.reason


def test_bad_signature_rejected(qr_project) -> None:  # type: ignore[no-untyped-def]
    config, project_root, priv = qr_project
    blob = _make_blob(config, priv)
    # Tamper with the last few signature chars but keep base64 valid by replacing in-place.
    head, sep, tail = blob.rpartition(".")
    # Flip a character; still valid base64 chars, different bytes → signature mismatch.
    tampered_tail = tail[:-4] + "AAAA"
    resp = verify_qr(config=config, project_root=project_root, blob=f"{head}{sep}{tampered_tail}")
    assert not resp.valid


def test_qr_disabled_raises(qr_project) -> None:  # type: ignore[no-untyped-def]
    config, project_root, priv = qr_project
    disabled = config.model_copy(
        update={"features": config.features.model_copy(update={"qr_verify": config.features.qr_verify.model_copy(update={"enabled": False})})}
    )
    with pytest.raises(VerifyError, match="disabled"):
        verify_qr(config=disabled, project_root=project_root, blob=_make_blob(config, priv))
