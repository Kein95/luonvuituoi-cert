"""Unit tests for :mod:`luonvuitoi_cert.config.models`.

These lock down cross-field invariants (results match subjects, fonts are
registered, IDs are unique) so future schema changes fail loud instead of
silently allowing malformed configs to reach the handlers.
"""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.config.models import Branding, Project


def _valid_raw() -> dict:
    return {
        "project": {"name": "DEMO", "slug": "demo", "locale": "en"},
        "rounds": [{"id": "main", "label": "Main", "table": "students", "pdf": "t.pdf"}],
        "subjects": [{"code": "S", "en": "Science", "db_col": "science_result"}],
        "results": {"S": {"GOLD": 1, "SILVER": 2}},
        "layout": {
            "page_size": [842, 595],
            "fields": {
                "name": {"x": 421, "y": 300, "font": "serif", "size": 36, "align": "center"}
            },
        },
        "fonts": {"serif": "fonts/serif.ttf"},
    }


def test_minimal_config_loads_with_defaults() -> None:
    cfg = CertConfig.model_validate(_valid_raw())
    assert cfg.project.locale == "en"
    assert cfg.admin.auth_mode == "password"
    assert cfg.features.kv_backend == "local"
    assert cfg.features.qr_verify.enabled is False
    assert cfg.student_search.mode == "name_dob_captcha"
    assert cfg.data_mapping.sbd_col == "sbd"  # default
    assert cfg.admin.roles == ["super-admin", "admin", "viewer"]


def test_slug_must_be_kebab_case() -> None:
    with pytest.raises(ValidationError):
        Project(name="Demo", slug="Invalid Slug")
    with pytest.raises(ValidationError):
        Project(name="Demo", slug="UPPER")
    # Tightened regex: reject trailing hyphen and double hyphens.
    with pytest.raises(ValidationError):
        Project(name="Demo", slug="trailing-")
    with pytest.raises(ValidationError):
        Project(name="Demo", slug="double--hyphen")
    with pytest.raises(ValidationError):
        Project(name="Demo", slug="-leading")
    Project(name="Demo", slug="valid-slug-123")
    Project(name="Demo", slug="abc")


def test_branding_rejects_non_hex_color() -> None:
    with pytest.raises(ValidationError):
        Branding(primary_color="not-a-color")
    Branding(primary_color="#abc")
    Branding(primary_color="#AABBCC")
    Branding(primary_color="#AABBCCDD")


def test_results_keys_must_match_subject_codes() -> None:
    raw = _valid_raw()
    raw["results"]["UNKNOWN"] = {"GOLD": 3}
    with pytest.raises(ValidationError, match="not declared in subjects"):
        CertConfig.model_validate(raw)


def test_subject_without_results_is_rejected() -> None:
    """Regression: Phase 02 review C1 — a subject declared without results silently passed before."""
    raw = _valid_raw()
    raw["subjects"].append({"code": "EXTRA", "en": "Extra", "db_col": "extra_col"})
    # results only has the first subject
    with pytest.raises(ValidationError, match="subjects declared without a results mapping"):
        CertConfig.model_validate(raw)


def test_round_id_rejects_path_separators() -> None:
    raw = _valid_raw()
    raw["rounds"][0]["id"] = "has/slash"
    with pytest.raises(ValidationError, match="round.id"):
        CertConfig.model_validate(raw)


def test_round_pdf_rejects_absolute_path() -> None:
    raw = _valid_raw()
    raw["rounds"][0]["pdf"] = "/etc/passwd"
    with pytest.raises(ValidationError, match="relative path"):
        CertConfig.model_validate(raw)


def test_round_pdf_rejects_parent_traversal() -> None:
    raw = _valid_raw()
    raw["rounds"][0]["pdf"] = "../../etc/passwd"
    with pytest.raises(ValidationError, match="traverse parents"):
        CertConfig.model_validate(raw)


def test_round_table_must_be_sql_identifier() -> None:
    raw = _valid_raw()
    raw["rounds"][0]["table"] = "students; DROP TABLE"
    with pytest.raises(ValidationError, match="SQL identifier"):
        CertConfig.model_validate(raw)


def test_subject_code_rejects_special_chars() -> None:
    raw = _valid_raw()
    raw["subjects"][0]["code"] = "a/b!"
    raw["results"] = {"a/b!": {"GOLD": 1}}
    with pytest.raises(ValidationError, match="subject.code"):
        CertConfig.model_validate(raw)


def test_subject_db_col_rejects_sql_injection() -> None:
    raw = _valid_raw()
    raw["subjects"][0]["db_col"] = "x; DROP TABLE students;--"
    with pytest.raises(ValidationError, match="SQL identifier"):
        CertConfig.model_validate(raw)


def test_fonts_reject_absolute_path() -> None:
    raw = _valid_raw()
    raw["fonts"]["evil"] = "/etc/passwd"
    raw["layout"]["fields"]["name"]["font"] = "evil"
    with pytest.raises(ValidationError, match="relative path"):
        CertConfig.model_validate(raw)


def test_fonts_reject_parent_traversal() -> None:
    raw = _valid_raw()
    raw["fonts"]["serif"] = "../../../etc/passwd"
    with pytest.raises(ValidationError, match="traverse parents"):
        CertConfig.model_validate(raw)


def test_results_reject_duplicate_pages() -> None:
    raw = _valid_raw()
    raw["results"]["S"] = {"GOLD": 1, "SILVER": 1}
    with pytest.raises(ValidationError, match="page numbers must be unique"):
        CertConfig.model_validate(raw)


def test_results_reject_non_positive_pages() -> None:
    raw = _valid_raw()
    raw["results"]["S"] = {"GOLD": 0}
    with pytest.raises(ValidationError, match=">= 1"):
        CertConfig.model_validate(raw)


def test_results_reject_empty_mapping() -> None:
    raw = _valid_raw()
    raw["results"]["S"] = {}
    with pytest.raises(ValidationError, match="at least one result"):
        CertConfig.model_validate(raw)


def test_layout_font_must_be_registered() -> None:
    raw = _valid_raw()
    raw["layout"]["fields"]["name"]["font"] = "unregistered"
    with pytest.raises(ValidationError, match="unregistered fonts"):
        CertConfig.model_validate(raw)


def test_rounds_require_unique_ids() -> None:
    raw = _valid_raw()
    raw["rounds"].append({"id": "main", "label": "Dup", "table": "t", "pdf": "p.pdf"})
    with pytest.raises(ValidationError, match="rounds\\[\\].id must be unique"):
        CertConfig.model_validate(raw)


def test_subjects_require_unique_codes() -> None:
    raw = _valid_raw()
    raw["subjects"].append({"code": "S", "en": "Dup", "db_col": "x"})
    raw["results"]["S"] = {"GOLD": 1}
    with pytest.raises(ValidationError, match="subjects\\[\\].code must be unique"):
        CertConfig.model_validate(raw)


def test_extra_fields_are_rejected() -> None:
    raw = _valid_raw()
    raw["unknown_top_level"] = True
    with pytest.raises(ValidationError):
        CertConfig.model_validate(raw)


def test_admin_roles_cannot_be_empty() -> None:
    raw = _valid_raw()
    raw["admin"] = {"roles": []}
    with pytest.raises(ValidationError, match="at least one role"):
        CertConfig.model_validate(raw)


def test_data_mapping_columns_must_be_sql_idents() -> None:
    """Regression: Phase 05 review C2 — *_col fields fed SQL but weren't regex-validated."""
    raw = _valid_raw()
    raw["data_mapping"] = {"sbd_col": "col;DROP TABLE"}
    with pytest.raises(ValidationError, match="SQL identifier"):
        CertConfig.model_validate(raw)


def test_data_mapping_extra_cols_must_be_sql_idents() -> None:
    raw = _valid_raw()
    raw["data_mapping"] = {"extra_cols": ["valid", "a b c"]}
    with pytest.raises(ValidationError, match="SQL identifiers"):
        CertConfig.model_validate(raw)


def test_data_mapping_optional_cols_skip_validation_when_none() -> None:
    raw = _valid_raw()
    raw["data_mapping"] = {"dob_col": None}  # optional, None is allowed
    CertConfig.model_validate(raw)  # must not raise


def test_layout_field_size_bounds() -> None:
    raw = _valid_raw()
    raw["layout"]["fields"]["name"]["size"] = 0
    with pytest.raises(ValidationError):
        CertConfig.model_validate(raw)


def test_full_feature_config_round_trips() -> None:
    raw = _valid_raw()
    raw["features"] = {
        "qr_verify": {"enabled": True, "public_key_path": "public.pem"},
        "shipment": {"enabled": True, "statuses": ["a", "b"], "fields": ["c"]},
        "otp_email": {"enabled": True, "provider": "resend"},
        "gsheet_log": {"enabled": True},
        "kv_backend": "vercel-kv",
    }
    cfg = CertConfig.model_validate(raw)
    assert cfg.features.qr_verify.enabled
    assert cfg.features.shipment.statuses == ["a", "b"]
    assert cfg.features.kv_backend == "vercel-kv"


def test_config_is_immutable_to_extra_keys_deep() -> None:
    raw = _valid_raw()
    raw["features"] = {"unknown_feature": True}
    with pytest.raises(ValidationError):
        CertConfig.model_validate(raw)


def test_model_copy_preserves_validators() -> None:
    cfg = CertConfig.model_validate(_valid_raw())
    clone_raw = copy.deepcopy(cfg.model_dump())
    clone_raw["results"]["S"]["BROKEN"] = 1  # duplicate page 1 alongside GOLD
    with pytest.raises(ValidationError):
        CertConfig.model_validate(clone_raw)
