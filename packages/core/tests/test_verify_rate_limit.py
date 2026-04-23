"""Regression test: /api/verify must be rate-limited.

Prior state: endpoint ran full RSA-PSS signature verify with no gate, making
it a cheap DoS amplifier and letting attackers probe for valid payloads
unlimited. Cap at 60/min/IP (see VERIFY_RATE_LIMIT in server/app.py).
"""

from __future__ import annotations

import json
from pathlib import Path


def test_verify_endpoint_is_rate_limited(tmp_path: Path) -> None:
    from werkzeug.test import Client

    _make_minimal_project(tmp_path)
    from luonvuitoi_cert_cli.server import build_app

    app = build_app(tmp_path / "cert.config.json", tmp_path)
    client = Client(app)

    codes: list[int] = []
    for _ in range(80):  # headroom over VERIFY_RATE_LIMIT (60) + slack
        resp = client.post(
            "/api/verify",
            json={"blob": "does-not-matter-rate-limit-fires-first"},
            headers={"X-Forwarded-For": "10.0.0.99"},
        )
        codes.append(resp.status_code)
        if resp.status_code == 429:
            break

    assert 429 in codes, f"expected a 429 within 80 reqs, got codes={codes!r}"


def _make_minimal_project(tmp_path: Path) -> None:
    import reportlab

    (tmp_path / "assets" / "fonts").mkdir(parents=True)
    (tmp_path / "assets" / "fonts" / "serif.ttf").write_bytes(
        (Path(reportlab.__file__).parent / "fonts" / "Vera.ttf").read_bytes()
    )
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "main.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    (tmp_path / "cert.config.json").write_text(
        json.dumps(
            {
                "project": {"name": "T", "slug": "t", "locale": "en"},
                "rounds": [
                    {
                        "id": "main",
                        "label": "M",
                        "table": "students",
                        "pdf": "templates/main.pdf",
                    }
                ],
                "subjects": [{"code": "G", "en": "G", "db_col": "result"}],
                "results": {"G": {"GOLD": 1}},
                "data_mapping": {
                    "sbd_col": "sbd",
                    "name_col": "full_name",
                    "dob_col": "dob",
                    "school_col": "school",
                    "phone_col": "phone",
                },
                "layout": {
                    "page_size": [842, 595],
                    "fields": {
                        "name": {
                            "x": 421,
                            "y": 330,
                            "font": "serif",
                            "size": 24,
                            "align": "center",
                        }
                    },
                },
                "fonts": {"serif": "assets/fonts/serif.ttf"},
                "features": {"kv_backend": "local"},
            }
        ),
        encoding="utf-8",
    )
