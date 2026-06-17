"""Smoke tests for the ``lvt-cert`` entry point.

Phase 01 target: every command advertises ``--help`` without raising, so the
dispatcher wiring is verified before subcommand implementations land.
"""

from __future__ import annotations

import os
import stat

import pytest
from luonvuitoi_cert_cli.main import app
from typer.testing import CliRunner

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


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes only")
def test_gen_keys_private_key_is_owner_only(tmp_path):  # type: ignore[no-untyped-def]
    """The QR signing key must be created 0600. It's the sole forgery secret."""
    result = runner.invoke(app, ["gen-keys", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    mode = stat.S_IMODE((tmp_path / "private_key.pem").stat().st_mode)
    assert mode == 0o600, oct(mode)
