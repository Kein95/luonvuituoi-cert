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
    Project(name="Demo", slug="valid-slug-123")


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
