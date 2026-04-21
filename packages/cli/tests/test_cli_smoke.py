"""Smoke tests for the ``lvt-cert`` entry point.

Phase 01 target: every command advertises ``--help`` without raising, so the
dispatcher wiring is verified before subcommand implementations land.
"""

from __future__ import annotations

from typer.testing import CliRunner

from luonvuitoi_cert_cli.main import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "lvt-cert" in result.stdout


def test_help_lists_all_subcommands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("init", "gen-keys", "seed", "dev"):
        assert name in result.stdout


def test_gen_keys_writes_pair(tmp_path):  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["gen-keys", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "private_key.pem").exists()
    assert (tmp_path / "public_key.pem").exists()


def test_gen_keys_refuses_overwrite(tmp_path):  # type: ignore[no-untyped-def]
    (tmp_path / "private_key.pem").write_text("existing")
    (tmp_path / "public_key.pem").write_text("existing")
    result = runner.invoke(app, ["gen-keys", "--out", str(tmp_path)])
    assert result.exit_code != 0
