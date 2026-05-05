"""Tests for the package's static-asset reader.

Covers MIME inference, name validation (no traversal, no separators), and the
"missing asset" path. Doesn't require any vendored binaries — the test creates
a temporary file inside the package's ``static/`` directory and removes it on
teardown.
"""

from __future__ import annotations

from pathlib import Path

import luonvuitoi_cert.ui.static_assets as _sa
import pytest
from luonvuitoi_cert.ui import StaticAssetError, read_static_asset


@pytest.fixture
def static_dir() -> Path:
    """Return the on-disk static directory next to the static_assets module.

    importlib.resources.files() can return a MultiplexedPath that doesn't
    expose write APIs, so we resolve the package directory via the module's
    __file__ instead — sufficient for editable installs and wheels.
    """
    return Path(_sa.__file__).resolve().parent.parent / "static"


@pytest.fixture
def fake_js(static_dir: Path):  # type: ignore[no-untyped-def]
    """Drop a throwaway JS file into the package static dir for the duration of one test."""
    target = static_dir / "pytest-fixture-probe.js"
    # Write bytes to avoid platform line-ending translation.
    target.write_bytes(b"/* probe */\n")
    yield target
    target.unlink(missing_ok=True)


def test_reads_existing_js_with_correct_mime(fake_js: Path) -> None:
    data, content_type = read_static_asset(fake_js.name)
    assert data == b"/* probe */\n"
    assert content_type == "application/javascript"


def test_qr_decode_helper_is_shipped_in_package() -> None:
    """qr-decode-helper.js is committed (jsqr.min.js is operator-vendored)."""
    data, content_type = read_static_asset("qr-decode-helper.js")
    assert content_type == "application/javascript"
    assert b"window.LvtQR" in data


def test_missing_asset_raises() -> None:
    with pytest.raises(StaticAssetError):
        read_static_asset("does-not-exist.js")


def test_unknown_suffix_rejected() -> None:
    """Only an allowlist of suffixes (.js / .css / .map) is permitted."""
    with pytest.raises(StaticAssetError):
        read_static_asset("anything.html")
    with pytest.raises(StaticAssetError):
        read_static_asset("anything.py")


def test_no_extension_rejected() -> None:
    with pytest.raises(StaticAssetError):
        read_static_asset("noext")


@pytest.mark.parametrize(
    "evil",
    [
        "../config/models.py",
        "..\\config\\models.py",
        "/etc/passwd",
        "subdir/file.js",
        ".hidden.js",
        "",
        "name with space.js",
        "weird;name.js",
    ],
)
def test_traversal_and_invalid_names_blocked(evil: str) -> None:
    with pytest.raises(StaticAssetError):
        read_static_asset(evil)
