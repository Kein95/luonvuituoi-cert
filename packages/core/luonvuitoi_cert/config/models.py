"""Pydantic models for ``cert.config.json``.

Design rules:
- Every field that has an obvious default carries one, so minimal configs are tiny.
- Cross-field invariants live in ``@model_validator`` hooks on :class:`CertConfig`
  (e.g., ``results`` keys must match declared ``subjects``).
- Enums are declared as ``Literal`` unions so the exported JSON Schema lists
  valid values explicitly for editor autocomplete.

Changes here propagate to the exported JSON Schema and all sample configs, so
run the test suite before committing.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LocaleCode = Literal["en", "vi"]
AlignMode = Literal["left", "center", "right"]
SearchMode = Literal["name_dob_captcha", "name_sbd_captcha", "sbd_phone"]
AdminSearchMode = Literal["sbd_auth", "sbd_phone"]
AuthMode = Literal["password", "otp_email", "magic_link"]
KVBackend = Literal["local", "upstash", "vercel-kv"]
EmailProvider = Literal["resend"]

_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
# Slug: lowercase kebab-case segments joined by single hyphens, no leading/trailing hyphen.
_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# Identifier used as a dict/URL key — letters/digits/_/- only, no path separators.
_IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
# SQL identifier safe to interpolate into column/table fragments (no quoting needed).
_SQL_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_relative_path(v: str, field: str) -> str:
    """Reject absolute paths and parent-directory traversal for asset references."""
    if not v:
        raise ValueError(f"{field} must not be empty")
    if v.startswith(("/", "\\")):
        raise ValueError(f"{field} must be a relative path (got absolute {v!r})")
    if len(v) >= 2 and v[1] == ":":  # Windows drive letter, e.g. C:\
        raise ValueError(f"{field} must be a relative path (got drive-letter {v!r})")
    parts = re.split(r"[\\/]", v)
    if ".." in parts:
        raise ValueError(f"{field} must not traverse parents ('..' segment in {v!r})")
    return v


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


_SAFE_LOGO_SCHEMES = ("/", "http://", "https://", "data:image/")


class Branding(_Strict):
    logo_url: str | None = None
    primary_color: str = "#667eea"
    accent_color: str = "#764ba2"

    @field_validator("primary_color", "accent_color")
    @classmethod
    def _hex(cls, v: str) -> str:
        if not _HEX_COLOR.match(v):
            raise ValueError(f"expected hex color (e.g. #667eea), got {v!r}")
        return v

    @field_validator("logo_url")
    @classmethod
    def _safe_scheme(cls, v: str | None) -> str | None:
        """Reject ``javascript:``, ``vbscript:``, and other XSS-adjacent URIs.

        Only relative paths, HTTP(S), and inline image data URIs are allowed —
        which covers the real-world cases (uploaded logo, CDN-hosted image,
        embedded base64) without opening an execution sink.
        """
        if v is None or v == "":
            return v
        if not any(v.startswith(prefix) for prefix in _SAFE_LOGO_SCHEMES):
            raise ValueError(f"branding.logo_url must start with {list(_SAFE_LOGO_SCHEMES)}; got {v!r}")
        return v


class Project(_Strict):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=60)
    locale: LocaleCode = "en"
    branding: Branding = Field(default_factory=Branding)

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not _SLUG.match(v):
            raise ValueError(f"slug must be lowercase kebab-case, got {v!r}")
        return v


class Round(_Strict):
    id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=120)
    table: str = Field(min_length=1, max_length=60)
    pdf: str = Field(min_length=1, description="Relative path to the certificate template PDF.")

    @field_validator("id")
    @classmethod
    def _ident(cls, v: str) -> str:
        if not _IDENT.match(v):
            raise ValueError(f"round.id must match {_IDENT.pattern}, got {v!r}")
        return v

    @field_validator("table")
    @classmethod
    def _sql_ident(cls, v: str) -> str:
        if not _SQL_IDENT.match(v):
            raise ValueError(f"round.table must be a SQL identifier, got {v!r}")
        return v

    @field_validator("pdf")
    @classmethod
    def _pdf_path(cls, v: str) -> str:
        return _validate_relative_path(v, "round.pdf")


class Subject(_Strict):
    code: str = Field(min_length=1, max_length=10, description="Short code used as a key in results/layout.")
    en: str = Field(min_length=1, max_length=60)
    vi: str | None = Field(default=None, max_length=60)
    db_col: str = Field(min_length=1, max_length=60)

    @field_validator("code")
    @classmethod
    def _ident(cls, v: str) -> str:
        if not _IDENT.match(v):
            raise ValueError(f"subject.code must match {_IDENT.pattern}, got {v!r}")
        return v

    @field_validator("db_col")
    @classmethod
    def _sql_ident(cls, v: str) -> str:
        if not _SQL_IDENT.match(v):
            raise ValueError(f"subject.db_col must be a SQL identifier, got {v!r}")
        return v


class LayoutField(_Strict):
    x: float
    y: float
    font: str = Field(min_length=1, description="Key into the top-level ``fonts`` registry.")
    size: float = Field(gt=0, le=500)
    color: str = "#000000"
    align: AlignMode = "center"
    wrap: int | None = Field(default=None, ge=1, le=500)

    @field_validator("color")
    @classmethod
    def _hex(cls, v: str) -> str:
        if not _HEX_COLOR.match(v):
            raise ValueError(f"expected hex color, got {v!r}")
        return v


class LayoutSpec(_Strict):
    page_size: tuple[float, float] = Field(description="(width, height) in points.")
    fields: dict[str, LayoutField] = Field(min_length=1)

    @field_validator("page_size")
    @classmethod
    def _positive_page(cls, v: tuple[float, float]) -> tuple[float, float]:
        if v[0] <= 0 or v[1] <= 0:
            raise ValueError("page_size must be positive")
        return v


class DataMapping(_Strict):
    sbd_col: str = "sbd"
    name_col: str = "name"
    dob_col: str | None = None
    school_col: str | None = None
    grade_col: str | None = None
    phone_col: str | None = None
    extra_cols: list[str] = Field(default_factory=list)

    @field_validator("sbd_col", "name_col", "dob_col", "school_col", "grade_col", "phone_col")
    @classmethod
    def _sql_ident_optional(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _SQL_IDENT.match(v):
            raise ValueError(f"data_mapping column must be a SQL identifier, got {v!r}")
        return v

    @field_validator("extra_cols")
    @classmethod
    def _extra_cols_sql_idents(cls, v: list[str]) -> list[str]:
        for col in v:
            if not _SQL_IDENT.match(col):
                raise ValueError(f"data_mapping.extra_cols entries must be SQL identifiers, got {col!r}")
        return v


class StudentSearch(_Strict):
    mode: SearchMode = "name_dob_captcha"
    admin_mode: AdminSearchMode = "sbd_auth"


class AdminConfig(_Strict):
    auth_mode: AuthMode = "password"
    multi_user: bool = True
    roles: list[str] = Field(default_factory=lambda: ["super-admin", "admin", "viewer"])

    @field_validator("roles")
    @classmethod
    def _non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("admin.roles must contain at least one role")
        return v


class QRVerify(_Strict):
    enabled: bool = False
    public_key_path: str = "public_key.pem"
    private_key_path: str = "private_key.pem"
    """Signing key — only the issuer needs this. Never commit it.

    The public key is safe to ship; the verifier endpoint uses only it.
    """
    x: float = 40.0
    y: float = 40.0
    size_pt: float = Field(default=80.0, gt=0)
    """Side length of the QR square drawn on the PDF overlay (in points)."""
    max_age_seconds: int = Field(default=0, ge=0)
    """Reject QR payloads older than this when verifying. ``0`` disables the check.

    Use a non-zero value (e.g., 365 * 86400) when you want issued certificates
    to expire — useful as a poor-man's revocation when there's no admin-side
    revocation list.
    """

    @field_validator("public_key_path", "private_key_path")
    @classmethod
    def _key_paths_relative(cls, v: str) -> str:
        return _validate_relative_path(v, "features.qr_verify.*_key_path")


class Shipment(_Strict):
    enabled: bool = False
    statuses: list[str] = Field(default_factory=lambda: ["pending", "shipped", "delivered"])
    fields: list[str] = Field(default_factory=lambda: ["tracking_code", "carrier", "shipped_at"])
    public_fields: list[str] = Field(default_factory=list)
    """Subset of ``fields`` the public lookup endpoint may return.

    Default empty — public responses carry only ``status`` + ``updated_at``.
    Enumerate non-sensitive fields here (e.g. carrier name) when you want
    students to see them. Tracking codes + recipient addresses should stay
    out unless your threat model tolerates SBD-only enumeration leaks.
    """

    @field_validator("statuses")
    @classmethod
    def _statuses_non_empty_unique(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("shipment.statuses must contain at least one status")
        if len(v) != len({s.strip().lower() for s in v}):
            raise ValueError(f"shipment.statuses must be unique (case-insensitive): {v}")
        for s in v:
            if not s.strip():
                raise ValueError("shipment.statuses entries must not be empty")
        return v

    @field_validator("fields")
    @classmethod
    def _fields_sql_idents(cls, v: list[str]) -> list[str]:
        """Dropped straight into CREATE TABLE; must survive ``_SQL_IDENT``."""
        reserved = {"id", "round_id", "sbd", "status", "created_at", "updated_at"}
        seen: set[str] = set()
        for col in v:
            if not _SQL_IDENT.match(col):
                raise ValueError(f"shipment.fields entries must be SQL identifiers, got {col!r}")
            if col in reserved:
                raise ValueError(f"shipment.fields entry {col!r} clashes with a reserved column")
            if col in seen:
                raise ValueError(f"shipment.fields entries must be unique, got duplicate {col!r}")
            seen.add(col)
        return v

    @model_validator(mode="after")
    def _public_fields_subset_of_fields(self) -> Shipment:
        declared = set(self.fields)
        extras = set(self.public_fields) - declared
        if extras:
            raise ValueError(f"shipment.public_fields has entries not in shipment.fields: {sorted(extras)}")
        return self


class OtpEmail(_Strict):
    enabled: bool = False
    provider: EmailProvider = "resend"


class GSheetLog(_Strict):
    enabled: bool = False


class Features(_Strict):
    qr_verify: QRVerify = Field(default_factory=QRVerify)
    shipment: Shipment = Field(default_factory=Shipment)
    otp_email: OtpEmail = Field(default_factory=OtpEmail)
    gsheet_log: GSheetLog = Field(default_factory=GSheetLog)
    kv_backend: KVBackend = "local"


class CertConfig(_Strict):
    """Root document for ``cert.config.json``. All handlers read from this."""

    project: Project
    rounds: list[Round] = Field(min_length=1)
    subjects: list[Subject] = Field(min_length=1)
    results: dict[str, dict[str, int]] = Field(
        description="subject_code → { result_name: page_number_in_pdf }."
    )
    data_mapping: DataMapping = Field(default_factory=DataMapping)
    layout: LayoutSpec
    fonts: dict[str, str] = Field(min_length=1, description="font_key → ttf path (relative).")

    @field_validator("fonts")
    @classmethod
    def _font_paths_relative(cls, v: dict[str, str]) -> dict[str, str]:
        for key, path in v.items():
            if not _IDENT.match(key):
                raise ValueError(f"fonts key {key!r} must match {_IDENT.pattern}")
            _validate_relative_path(path, f"fonts[{key!r}]")
        return v

    student_search: StudentSearch = Field(default_factory=StudentSearch)
    admin: AdminConfig = Field(default_factory=AdminConfig)
    features: Features = Field(default_factory=Features)

    @model_validator(mode="after")
    def _check_round_ids_unique(self) -> CertConfig:
        ids = [r.id for r in self.rounds]
        if len(ids) != len(set(ids)):
            raise ValueError("rounds[].id must be unique")
        return self

    @model_validator(mode="after")
    def _check_subject_codes_unique(self) -> CertConfig:
        codes = [s.code for s in self.subjects]
        if len(codes) != len(set(codes)):
            raise ValueError("subjects[].code must be unique")
        return self

    @model_validator(mode="after")
    def _check_results_match_subjects(self) -> CertConfig:
        declared = {s.code for s in self.subjects}
        declared_results = set(self.results.keys())
        extras = declared_results - declared
        if extras:
            raise ValueError(f"results has keys not declared in subjects: {sorted(extras)}")
        missing = declared - declared_results
        if missing:
            raise ValueError(
                f"subjects declared without a results mapping: {sorted(missing)} "
                "(every subject.code must have a corresponding results[code] entry)"
            )
        # Each result map must have at least 1 entry and unique page numbers.
        for code, mapping in self.results.items():
            if not mapping:
                raise ValueError(f"results[{code!r}] must have at least one result → page entry")
            pages = list(mapping.values())
            if any(p < 1 for p in pages):
                raise ValueError(f"results[{code!r}] page numbers must be >= 1")
            if len(pages) != len(set(pages)):
                raise ValueError(f"results[{code!r}] page numbers must be unique")
        return self

    @model_validator(mode="after")
    def _check_layout_fonts_registered(self) -> CertConfig:
        registered = set(self.fonts.keys())
        missing: list[str] = []
        for name, spec in self.layout.fields.items():
            if spec.font not in registered:
                missing.append(f"{name}→{spec.font}")
        if missing:
            raise ValueError(f"layout.fields reference unregistered fonts (add to ``fonts``): {missing}")
        return self
