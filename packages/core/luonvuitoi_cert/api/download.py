"""Download handler — render the certificate PDF for one (student, round, subject).

The handler composes three subsystems:
- :func:`search_student` confirms the student exists and what certs are
  available (handles CAPTCHA / rate limit / admin gating itself).
- :class:`OverlayRequest` + :func:`render_certificate_bytes` draws the
  student's text onto the correct template page.
- :func:`sanitize_filename` produces the ``Content-Disposition`` name.

Because ``search_student`` is called internally, each download consumes a
fresh CAPTCHA challenge — callers must issue separate challenges for search
and for download; the same ``captcha_id`` cannot be reused.

Transport-layer contract: the HTTP/Flask/Vercel wrapper **must** call
:func:`validate_request_size` on the raw body before JSON-parsing it.

Separating the logic from raw transport keeps handlers identical between
Vercel serverless and the Flask dev server.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from luonvuitoi_cert.api.search import AvailableCertificate, SearchError, search_student
from luonvuitoi_cert.api.security import sanitize_filename
from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.engine import OverlayRequest, render_certificate_bytes
from luonvuitoi_cert.engine.fonts import FontRegistry
from luonvuitoi_cert.qr import (
    QRPayload,
    encode_blob,
    load_private_key,
    render_qr_png,
    sign_payload,
)
from luonvuitoi_cert.storage.kv.base import KVBackend


@dataclass(slots=True)
class DownloadResponse:
    filename: str
    pdf_bytes: bytes
    content_type: str = "application/pdf"


def _build_field_values(config: CertConfig, row: dict[str, str]) -> dict[str, str]:
    """Map declared data_mapping columns to the logical layout field names."""
    m = config.data_mapping
    values: dict[str, str] = {"name": row.get(m.name_col, "")}
    if m.dob_col:
        values["dob"] = row.get(m.dob_col, "")
    if m.school_col:
        values["school"] = row.get(m.school_col, "")
    if m.grade_col:
        values["grade"] = row.get(m.grade_col, "")
    if m.phone_col:
        values["phone"] = row.get(m.phone_col, "")
    for col in m.extra_cols:
        if col not in values:
            values[col] = row.get(col, "")
    return values


def _pick_certificate(
    cert_list: list[AvailableCertificate], round_id: str, subject_code: str
) -> AvailableCertificate:
    for c in cert_list:
        if c.round_id == round_id and c.subject_code == subject_code:
            return c
    raise SearchError(
        f"no certificate for round={round_id!r} subject={subject_code!r}; "
        f"available: {[(c.round_id, c.subject_code) for c in cert_list]}"
    )


def _maybe_sign_qr(
    config: CertConfig,
    project_root: Path,
    sbd: str,
    cert: AvailableCertificate,
    verify_url_builder,  # type: ignore[no-untyped-def]
    allow_raw_qr: bool,
) -> bytes | None:
    """Build + sign + render the QR PNG if ``features.qr_verify.enabled``.

    When ``verify_url_builder`` is None the QR holds the raw blob, which is
    fine for tests but a footgun in production — end users expect scanning to
    open a URL. In production paths :func:`download_certificate` raises
    :class:`SearchError` unless the caller has opted in via
    ``allow_raw_qr=True``.
    """
    qr = config.features.qr_verify
    if not qr.enabled:
        return None
    if verify_url_builder is None and not allow_raw_qr:
        raise SearchError(
            "verify_url_builder is required when features.qr_verify.enabled; "
            "pass allow_raw_qr=True in tests to embed the raw blob"
        )
    key_path = project_root / qr.private_key_path
    private_key = load_private_key(key_path)
    payload = QRPayload.now(
        project_slug=config.project.slug,
        round_id=cert.round_id,
        subject_code=cert.subject_code,
        result=cert.result_name,
        sbd=sbd,
    )
    signature = sign_payload(private_key, payload)
    blob = encode_blob(payload, signature)
    qr_text = verify_url_builder(blob) if verify_url_builder else blob
    return render_qr_png(qr_text)


def download_certificate(
    *,
    config: CertConfig,
    project_root: str | Path,
    db_path: str | Path,
    kv: KVBackend,
    params: dict[str, Any],
    client_id: str,
    mode: Literal["student", "admin"] = "student",
    font_registry: FontRegistry | None = None,
    env: dict[str, str] | None = None,
    verify_url_builder=None,  # type: ignore[no-untyped-def]
    allow_raw_qr: bool = False,
) -> DownloadResponse:
    """Search the student, pick the requested certificate, overlay + return PDF bytes.

    ``verify_url_builder(blob: str) -> str`` is used only when
    ``features.qr_verify.enabled``; it wraps the signed blob into a URL that
    opens the Certificate-Checker page with the blob prefilled.

    When QR is enabled and ``verify_url_builder`` is None, a :class:`SearchError`
    is raised unless ``allow_raw_qr=True`` (tests and CLI). In production the
    builder should always be wired up so scanned QRs actually open a verifier.
    """
    round_id = str(params.get("round_id", "")).strip()
    subject_code = str(params.get("subject_code", "")).strip()
    if not round_id or not subject_code:
        raise SearchError("round_id and subject_code are both required")

    result = search_student(
        config=config,
        db_path=db_path,
        kv=kv,
        params=params,
        client_id=client_id,
        mode=mode,
        env=env,
    )
    cert = _pick_certificate(result.certificates, round_id, subject_code)

    qr_png = _maybe_sign_qr(config, Path(project_root), result.sbd, cert, verify_url_builder, allow_raw_qr)

    pdf_bytes = render_certificate_bytes(
        OverlayRequest(
            config=config,
            project_root=Path(project_root),
            round_id=cert.round_id,
            page_number=cert.page_number,
            values=_build_field_values(config, result.fields),
            qr_png_bytes=qr_png,
        ),
        font_registry=font_registry,
    )
    filename = sanitize_filename(
        f"{config.project.slug}-{cert.round_id}-{cert.subject_code}-{result.sbd}.pdf"
    )
    return DownloadResponse(filename=filename, pdf_bytes=pdf_bytes)
