"""Search handler — look up a student record across all configured rounds.

Two modes share this entry point:

- ``student`` (default) — public lookup via name + DOB / SBD, protected by a
  one-shot CAPTCHA and a fixed-window rate limit. CAPTCHA runs first, rate
  limit only ticks after a successful CAPTCHA so a single typo can't lock the
  caller out. Both gates run before any DB access.
- ``admin`` — privileged lookup by SBD. The caller is already authenticated
  upstream (Phase 06 wires JWT); here we only re-check the token is non-empty.
  Admin skips CAPTCHA + rate limit.

Transport-layer contract: the HTTP/Flask/Vercel wrapper **must** call
:func:`validate_request_size` on the raw body before JSON-parsing it. This
module trusts the ``params`` dict is already size-bounded.

Result: every round where the student exists, and for each subject that has
a non-empty result cell, the (round_id, subject_code, result_name,
page_number) tuple needed to download the matching certificate.
"""

from __future__ import annotations

import sqlite3
import unicodedata
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from luonvuitoi_cert.api.captcha import verify_challenge
from luonvuitoi_cert.api.feature_gates import require_public_lookup
from luonvuitoi_cert.api.rate_limiter import check_rate_limit
from luonvuitoi_cert.api.security import SecurityError, validate_sbd
from luonvuitoi_cert.auth.tokens import TokenError, verify_admin_token
from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.storage.kv.base import KVBackend

STUDENT_RATE_LIMIT = 20
STUDENT_RATE_WINDOW_SECONDS = 60


class SearchError(Exception):
    """Raised when the query can't be fulfilled (bad params, no match, etc.)."""


@dataclass(slots=True)
class AvailableCertificate:
    round_id: str
    round_label: str
    subject_code: str
    subject_label: str
    result_name: str
    page_number: int


@dataclass(slots=True)
class SearchResult:
    sbd: str
    name: str
    fields: dict[str, str]
    """All declared data_mapping columns for display (keyed by source column name)."""
    certificates: list[AvailableCertificate] = field(default_factory=list)


# ── Normalization helpers ───────────────────────────────────────────


def _strip_accents_upper(text: str) -> str:
    nfd = unicodedata.normalize("NFD", str(text))
    stripped = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return stripped.replace("đ", "d").replace("Đ", "D").upper().strip()


def _normalize_dob(raw: str) -> str:
    """Canonicalize common date formats to ``DD-MM-YYYY`` zero-padded.

    Accepted inputs:
    - ``D/M/YYYY`` or ``DD/MM/YYYY`` — slash separator
    - ``DD-MM-YYYY`` — hyphen separator
    - ``01.06.2010`` — dotted (European style)
    - ``YYYY-MM-DD`` — ISO 8601 (auto-detected by 4-digit leading year)
    Leading/trailing whitespace is stripped before parsing.
    """
    text = str(raw).strip().replace("/", "-").replace(".", "-")
    parts = text.split("-")
    if len(parts) != 3:
        return text
    # ISO: first part is the 4-digit year → flip to DD-MM-YYYY.
    if len(parts[0]) == 4 and parts[0].isdigit():
        y, m, d = parts
    else:
        d, m, y = parts
    return f"{d.zfill(2)}-{m.zfill(2)}-{y.zfill(4) if y.isdigit() and len(y) < 4 else y}"


def _matches_name(candidate: str, query: str) -> bool:
    return _strip_accents_upper(candidate) == _strip_accents_upper(query)


# ── DB query ────────────────────────────────────────────────────────


def _fetch_row(conn: sqlite3.Connection, table: str, sbd_col: str, sbd: str) -> dict[str, str] | None:
    cursor = conn.execute(f'SELECT * FROM "{table}" WHERE "{sbd_col}" = ? LIMIT 1', (sbd,))
    row = cursor.fetchone()
    return dict(row) if row else None


def _collect_certificates(
    config: CertConfig, round_id: str, round_label: str, row: dict[str, str]
) -> list[AvailableCertificate]:
    out: list[AvailableCertificate] = []
    for subj in config.subjects:
        raw = row.get(subj.db_col, "").strip()
        if not raw:
            continue
        pages = config.results.get(subj.code, {})
        # Match result name case-insensitively / accent-tolerant.
        normalized = _strip_accents_upper(raw)
        page_number = next(
            (p for name, p in pages.items() if _strip_accents_upper(name) == normalized),
            None,
        )
        if page_number is None:
            continue
        out.append(
            AvailableCertificate(
                round_id=round_id,
                round_label=round_label,
                subject_code=subj.code,
                subject_label=subj.en,
                result_name=raw,
                page_number=page_number,
            )
        )
    return out


# ── Public entry points ─────────────────────────────────────────────


def _verify_student_gate(kv: KVBackend, params: dict[str, Any], client_id: str) -> None:
    """CAPTCHA first, rate-limit after — a wrong guess must not burn the caller's quota.

    Ordering rationale: the CAPTCHA is single-use and consumed on failure, so
    attackers can't get free retries; ticking the rate limit only *after* a
    successful CAPTCHA ensures that if a legitimate human typos their answer
    they don't get locked out of search on the next try. ``issue_challenge``
    itself is rate-limited at the transport layer (Phase 07).
    """
    verify_challenge(kv, str(params.get("captcha_id", "")), params.get("captcha_answer"))
    check_rate_limit(
        kv, "search", client_id, limit=STUDENT_RATE_LIMIT, window_seconds=STUDENT_RATE_WINDOW_SECONDS
    )


def _match_predicate(config: CertConfig, row: dict[str, str], params: dict[str, Any]) -> bool:
    mode = config.student_search.mode
    m = config.data_mapping
    if mode == "name_dob_captcha":
        if not m.dob_col:
            raise SearchError("config.data_mapping.dob_col required for name_dob_captcha mode")
        return _matches_name(row.get(m.name_col, ""), str(params.get("name", ""))) and (
            _normalize_dob(row.get(m.dob_col, "")) == _normalize_dob(str(params.get("dob", "")))
        )
    if mode == "name_sbd_captcha":
        return _matches_name(row.get(m.name_col, ""), str(params.get("name", "")))
    if mode == "sbd_phone":
        if not m.phone_col:
            raise SearchError("config.data_mapping.phone_col required for sbd_phone mode")
        last4 = str(params.get("phone", ""))[-4:]
        return row.get(m.phone_col, "")[-4:] == last4 and bool(last4)
    raise SearchError(f"unknown student_search.mode: {mode!r}")


def search_student(
    *,
    config: CertConfig,
    db_path: str | Path,
    kv: KVBackend,
    params: dict[str, Any],
    client_id: str,
    mode: Literal["student", "admin"] = "student",
    env: dict[str, str] | None = None,
) -> SearchResult:
    """Resolve a student record and enumerate downloadable certificates.

    ``env`` is threaded through to :func:`verify_admin_token` so tests and
    multi-worker deployments share a single JWT secret source. If omitted,
    ``os.environ`` is read at verify time.
    """
    sbd = validate_sbd(params.get("sbd"))
    if mode == "student":
        # Feature gate runs before CAPTCHA/rate-limit so disabled surfaces
        # don't tick quotas or burn a captcha token.
        require_public_lookup(kv)
        _verify_student_gate(kv, params, client_id)
    elif mode == "admin":
        try:
            verify_admin_token(str(params.get("token", "")), env=env, kv=kv)
        except TokenError as e:
            raise SecurityError(str(e)) from e
    else:
        raise SearchError(f"unknown mode: {mode!r}")

    found: SearchResult | None = None
    with closing(sqlite3.connect(str(Path(db_path).expanduser().resolve()))) as conn:
        conn.row_factory = sqlite3.Row
        for r in config.rounds:
            row = _fetch_row(conn, r.table, config.data_mapping.sbd_col, sbd)
            if row is None:
                continue
            if mode == "student" and not _match_predicate(config, row, params):
                continue
            if found is None:
                found = SearchResult(
                    sbd=sbd,
                    name=row.get(config.data_mapping.name_col, ""),
                    fields={k: str(v) for k, v in row.items()},
                )
            found.certificates.extend(_collect_certificates(config, r.id, r.label, row))
    if found is None:
        raise SearchError("no matching student found")
    return found
