"""Tests for :mod:`luonvuitoi_cert.api.download`."""

from __future__ import annotations

import re
from io import BytesIO

import pytest
from pypdf import PdfReader

from luonvuitoi_cert.api.captcha import issue_challenge
from luonvuitoi_cert.api.download import download_certificate
from luonvuitoi_cert.api.search import SearchError


def _solve(question: str) -> int:
    a, op, b = re.match(r"(\d+)\s*([+\-×])\s*(\d+)", question).groups()  # type: ignore[union-attr]
    return {"+": int(a) + int(b), "-": int(a) - int(b), "×": int(a) * int(b)}[op]


def _params(kv, **extra) -> dict:  # type: ignore[no-untyped-def]
    ch = issue_challenge(kv)
    return {
        "sbd": "12345",
        "name": "Nguyễn Văn A",
        "dob": "01-06-2010",
        "captcha_id": ch.id,
        "captcha_answer": _solve(ch.question),
        "round_id": "main",
        "subject_code": "S",
        **extra,
    }


def test_download_returns_pdf_bytes(cert_config, populated_db, project_root, kv_memory) -> None:  # type: ignore[no-untyped-def]
    resp = download_certificate(
        config=cert_config,
        project_root=project_root,
        db_path=populated_db,
        kv=kv_memory,
        params=_params(kv_memory),
        client_id="ip-1",
    )
    assert resp.content_type == "application/pdf"
    assert resp.pdf_bytes.startswith(b"%PDF")
    reader = PdfReader(BytesIO(resp.pdf_bytes))
    assert len(reader.pages) == 1


def test_filename_contains_identifiers(cert_config, populated_db, project_root, kv_memory) -> None:  # type: ignore[no-untyped-def]
    resp = download_certificate(
        config=cert_config,
        project_root=project_root,
        db_path=populated_db,
        kv=kv_memory,
        params=_params(kv_memory),
        client_id="ip-1",
    )
    assert resp.filename.endswith(".pdf")
    assert "12345" in resp.filename
    assert "main" in resp.filename
    assert "S" in resp.filename


def test_missing_round_raises(cert_config, populated_db, project_root, kv_memory) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(SearchError, match="required"):
        download_certificate(
            config=cert_config,
            project_root=project_root,
            db_path=populated_db,
            kv=kv_memory,
            params=_params(kv_memory, round_id=""),
            client_id="ip-1",
        )


def test_unknown_subject_raises(cert_config, populated_db, project_root, kv_memory) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(SearchError, match="no certificate"):
        download_certificate(
            config=cert_config,
            project_root=project_root,
            db_path=populated_db,
            kv=kv_memory,
            params=_params(kv_memory, subject_code="BOGUS"),
            client_id="ip-1",
        )


def test_download_requires_verify_url_builder_when_qr_enabled(
    project_root, tmp_path, kv_memory, config_dict
) -> None:  # type: ignore[no-untyped-def]
    """Regression: Phase 07 review M2 — missing builder would otherwise ship a footgun QR."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from luonvuitoi_cert.config import CertConfig
    from luonvuitoi_cert.ingest import ingest_rows

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (project_root / "private_key.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (project_root / "public_key.pem").write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    cfg = CertConfig.model_validate({**config_dict, "features": {"qr_verify": {"enabled": True}}})
    db = tmp_path / "qr.db"
    ingest_rows(
        cfg,
        db,
        "main",
        [{"sbd": "12345", "full_name": "A", "dob": "01-06-2010", "school": "S", "phone": "0901234567", "s": "GOLD"}],
    )
    ch = issue_challenge(kv_memory)
    with pytest.raises(SearchError, match="verify_url_builder is required"):
        download_certificate(
            config=cfg,
            project_root=project_root,
            db_path=db,
            kv=kv_memory,
            params={
                "sbd": "12345",
                "name": "A",
                "dob": "01-06-2010",
                "captcha_id": ch.id,
                "captcha_answer": _solve(ch.question),
                "round_id": "main",
                "subject_code": "S",
            },
            client_id="ip-1",
            # verify_url_builder deliberately omitted — production path must raise.
        )


def test_download_embeds_signed_qr_when_enabled(
    project_root, tmp_path, kv_memory, config_dict
) -> None:  # type: ignore[no-untyped-def]
    """Regression: Phase 07 — QR pipeline renders + signs + embeds + roundtrips through /api/verify."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from luonvuitoi_cert.api import verify_qr
    from luonvuitoi_cert.config import CertConfig
    from luonvuitoi_cert.ingest import ingest_rows

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (project_root / "private_key.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (project_root / "public_key.pem").write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    qr_enabled = {**config_dict, "features": {"qr_verify": {"enabled": True}}}
    cfg = CertConfig.model_validate(qr_enabled)
    db = tmp_path / "qr.db"
    ingest_rows(
        cfg,
        db,
        "main",
        [{"sbd": "12345", "full_name": "A", "dob": "01-06-2010", "school": "S", "phone": "0901234567", "s": "GOLD"}],
    )
    ch = issue_challenge(kv_memory)

    captured_blobs: list[str] = []
    resp = download_certificate(
        config=cfg,
        project_root=project_root,
        db_path=db,
        kv=kv_memory,
        params={
            "sbd": "12345",
            "name": "A",
            "dob": "01-06-2010",
            "captcha_id": ch.id,
            "captcha_answer": _solve(ch.question),
            "round_id": "main",
            "subject_code": "S",
        },
        client_id="ip-1",
        verify_url_builder=lambda blob: captured_blobs.append(blob) or blob,
    )
    assert resp.pdf_bytes.startswith(b"%PDF")
    assert len(captured_blobs) == 1  # QR generation path ran
    verdict = verify_qr(config=cfg, project_root=project_root, blob=captured_blobs[0])
    assert verdict.valid
    assert verdict.payload.sbd == "12345"  # type: ignore[union-attr]


def test_admin_mode_works_without_captcha(cert_config, populated_db, project_root, kv_memory) -> None:  # type: ignore[no-untyped-def]
    from luonvuitoi_cert.auth import Role, issue_admin_token

    admin_token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN)
    resp = download_certificate(
        config=cert_config,
        project_root=project_root,
        db_path=populated_db,
        kv=kv_memory,
        params={
            "sbd": "12345",
            "round_id": "main",
            "subject_code": "S",
            "token": admin_token,
        },
        client_id="ip-1",
        mode="admin",
    )
    assert resp.pdf_bytes.startswith(b"%PDF")
