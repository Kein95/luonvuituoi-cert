"""Integration tests for the Phase 11 CLI commands: init, seed, dev app builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from luonvuitoi_cert_cli.main import app

runner = CliRunner()


# ── init ────────────────────────────────────────────────────────────


def test_init_scaffolds_new_project(tmp_path: Path) -> None:
    target = tmp_path / "my-portal"
    result = runner.invoke(
        app,
        [
            "init",
            str(target),
            "--name",
            "Demo Academy",
            "--slug",
            "demo-academy",
            "--locale",
            "en",
            "--non-interactive",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert (target / "cert.config.json").exists()
    assert (target / "vercel.json").exists()
    assert (target / "requirements.txt").exists()
    assert (target / "README.md").exists()


def test_init_refuses_non_empty_target(tmp_path: Path) -> None:
    (tmp_path / "existing.txt").write_text("hi", encoding="utf-8")
    result = runner.invoke(app, ["init", str(tmp_path), "--non-interactive"])
    assert result.exit_code != 0


def test_init_rejects_invalid_slug(tmp_path: Path) -> None:
    target = tmp_path / "x"
    result = runner.invoke(
        app,
        ["init", str(target), "--slug", "Not_A_Slug!", "--non-interactive"],
    )
    assert result.exit_code != 0


def test_init_rejects_invalid_locale(tmp_path: Path) -> None:
    target = tmp_path / "x"
    result = runner.invoke(
        app,
        ["init", str(target), "--slug", "demo", "--locale", "xx", "--non-interactive"],
    )
    assert result.exit_code != 0


def test_init_rendered_config_validates(tmp_path: Path) -> None:
    target = tmp_path / "v"
    result = runner.invoke(
        app,
        ["init", str(target), "--name", "V", "--slug", "v-demo", "--non-interactive"],
    )
    assert result.exit_code == 0
    data = json.loads((target / "cert.config.json").read_text(encoding="utf-8"))
    assert data["project"]["name"] == "V"
    assert data["project"]["slug"] == "v-demo"


# ── seed ────────────────────────────────────────────────────────────


def test_seed_generates_excel(tmp_path: Path) -> None:
    target = tmp_path / "seed-test"
    runner.invoke(
        app,
        ["init", str(target), "--slug", "seed-test", "--non-interactive"],
    )
    output = target / "data" / "students.xlsx"
    result = runner.invoke(
        app,
        [
            "seed",
            "--count",
            "4",
            "--seed",
            "7",
            "--output",
            str(output),
            "--config",
            str(target / "cert.config.json"),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert output.exists()

    from openpyxl import load_workbook

    wb = load_workbook(output)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    assert len(rows) == 5  # header + 4 students
    wb.close()


def test_seed_deterministic_with_seed_value(tmp_path: Path) -> None:
    target = tmp_path / "d"
    runner.invoke(app, ["init", str(target), "--slug", "d", "--non-interactive"])
    out1 = target / "data" / "a.xlsx"
    out2 = target / "data" / "b.xlsx"
    for out in (out1, out2):
        runner.invoke(
            app,
            [
                "seed",
                "--count",
                "3",
                "--seed",
                "12345",
                "--output",
                str(out),
                "--config",
                str(target / "cert.config.json"),
            ],
        )
    assert out1.read_bytes() != b""
    # Same seed => same students => same XLSX body (modulo openpyxl's timestamps).
    # Compare the rendered rows instead of raw bytes.
    from openpyxl import load_workbook

    rows_a = list(load_workbook(out1).active.iter_rows(values_only=True))
    rows_b = list(load_workbook(out2).active.iter_rows(values_only=True))
    assert rows_a == rows_b


# ── dev app ─────────────────────────────────────────────────────────


@pytest.fixture
def scaffolded_project(tmp_path: Path) -> Path:
    target = tmp_path / "live"
    runner.invoke(
        app,
        ["init", str(target), "--slug", "live-portal", "--non-interactive"],
    )
    # Seed so the DB exists with a student.
    runner.invoke(
        app,
        [
            "seed",
            "--count",
            "2",
            "--seed",
            "1",
            "--output",
            str(target / "data" / "students.xlsx"),
            "--config",
            str(target / "cert.config.json"),
        ],
    )
    return target


def test_build_app_registers_pages_and_api(scaffolded_project: Path) -> None:
    from luonvuitoi_cert_cli.server import build_app

    flask_app = build_app(scaffolded_project / "cert.config.json", scaffolded_project)
    rules = {r.rule for r in flask_app.url_map.iter_rules()}
    assert "/" in rules
    assert "/admin" in rules
    assert "/certificate-checker" in rules
    assert "/api/search" in rules
    assert "/api/download" in rules
    assert "/api/verify" in rules
    assert "/api/captcha" in rules
    assert "/api/admin/login" in rules


def test_dev_server_serves_portal_html(scaffolded_project: Path) -> None:
    from luonvuitoi_cert_cli.server import build_app

    flask_app = build_app(scaffolded_project / "cert.config.json", scaffolded_project)
    client = flask_app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"<!doctype html>" in resp.data.lower()
    assert b"Certificate Portal" in resp.data or b"Cert" in resp.data


def test_dev_server_admin_emits_csp(scaffolded_project: Path) -> None:
    """/admin must carry a Content-Security-Policy header to protect the sessionStorage JWT."""
    from luonvuitoi_cert_cli.server import build_app

    flask_app = build_app(scaffolded_project / "cert.config.json", scaffolded_project)
    client = flask_app.test_client()
    resp = client.get("/admin")
    assert resp.status_code == 200
    assert "Content-Security-Policy" in resp.headers


def test_dev_server_captcha_endpoint(scaffolded_project: Path) -> None:
    from luonvuitoi_cert_cli.server import build_app

    flask_app = build_app(scaffolded_project / "cert.config.json", scaffolded_project)
    client = flask_app.test_client()
    resp = client.post("/api/captcha")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "id" in body and "question" in body
