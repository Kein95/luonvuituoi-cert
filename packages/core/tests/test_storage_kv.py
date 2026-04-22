"""Tests for KV backends: MemoryKV + LocalFileKV + open_kv factory.

RestKV is exercised separately (needs httpx mocking).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.storage.kv import KVError, LocalFileKV, MemoryKV, open_kv


@pytest.fixture(params=["memory", "local"])
def kv(request, tmp_path: Path):  # type: ignore[no-untyped-def]
    if request.param == "memory":
        yield MemoryKV()
    else:
        yield LocalFileKV(tmp_path / "kv.json")


# ── Common surface ──────────────────────────────────────────────────


def test_set_get_roundtrip(kv) -> None:  # type: ignore[no-untyped-def]
    kv.set("foo", "bar")
    assert kv.get("foo") == "bar"


def test_get_returns_none_for_missing(kv) -> None:  # type: ignore[no-untyped-def]
    assert kv.get("nope") is None


def test_delete_removes_key(kv) -> None:  # type: ignore[no-untyped-def]
    kv.set("foo", "bar")
    kv.delete("foo")
    assert kv.get("foo") is None


def test_delete_missing_key_is_noop(kv) -> None:  # type: ignore[no-untyped-def]
    kv.delete("nope")  # must not raise


def test_exists(kv) -> None:  # type: ignore[no-untyped-def]
    assert not kv.exists("foo")
    kv.set("foo", "bar")
    assert kv.exists("foo")


def test_ttl_expires(kv) -> None:  # type: ignore[no-untyped-def]
    kv.set("foo", "bar", ttl_seconds=1)
    assert kv.get("foo") == "bar"
    time.sleep(1.1)
    assert kv.get("foo") is None


def test_scan_prefix(kv) -> None:  # type: ignore[no-untyped-def]
    kv.set("a:1", "1")
    kv.set("a:2", "2")
    kv.set("b:1", "3")
    keys = sorted(kv.scan_prefix("a:"))
    assert keys == ["a:1", "a:2"]


def test_scan_prefix_limit(kv) -> None:  # type: ignore[no-untyped-def]
    for i in range(10):
        kv.set(f"x:{i}", str(i))
    keys = kv.scan_prefix("x:", limit=3)
    assert len(keys) == 3


def test_consume_returns_and_deletes(kv) -> None:  # type: ignore[no-untyped-def]
    kv.set("k", "v")
    assert kv.consume("k") == "v"
    assert kv.get("k") is None


def test_consume_missing_returns_none(kv) -> None:  # type: ignore[no-untyped-def]
    assert kv.consume("absent") is None


def test_consume_expired_treated_as_missing(kv) -> None:  # type: ignore[no-untyped-def]
    kv.set("k", "v", ttl_seconds=1)
    time.sleep(1.1)
    assert kv.consume("k") is None


def test_consume_is_single_use_under_concurrency(kv) -> None:  # type: ignore[no-untyped-def]
    """Regression: Phase 05 review C1 — get+delete TOCTOU between threads."""
    import threading

    kv.set("race", "v")
    results: list[str | None] = []
    lock = threading.Lock()

    def worker() -> None:
        res = kv.consume("race")
        with lock:
            results.append(res)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Exactly one thread wins; everyone else sees None.
    assert results.count("v") == 1
    assert results.count(None) == len(threads) - 1


# ── LocalFileKV-specific ────────────────────────────────────────────


def test_local_kv_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "kv.json"
    LocalFileKV(path).set("k", "v")
    assert LocalFileKV(path).get("k") == "v"


def test_local_kv_corrupt_file_surfaces_error(tmp_path: Path) -> None:
    path = tmp_path / "kv.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(KVError, match="corrupt"):
        LocalFileKV(path).get("anything")


def test_local_kv_atomic_write_leaves_no_temp(tmp_path: Path) -> None:
    kv = LocalFileKV(tmp_path / "kv.json")
    kv.set("k", "v")
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".kv-")]
    assert not leftovers, f"temp files not cleaned: {leftovers}"


# ── open_kv factory ──────────────────────────────────────────────────


def _cfg_with_kv(backend: str) -> CertConfig:
    return CertConfig.model_validate(
        {
            "project": {"name": "T", "slug": "t"},
            "rounds": [{"id": "m", "label": "M", "table": "students", "pdf": "t.pdf"}],
            "subjects": [{"code": "S", "en": "S", "db_col": "s"}],
            "results": {"S": {"GOLD": 1}},
            "layout": {
                "page_size": [100, 100],
                "fields": {"n": {"x": 0, "y": 0, "font": "f", "size": 10, "align": "left"}},
            },
            "fonts": {"f": "f.ttf"},
            "features": {"kv_backend": backend},
        }
    )


def test_open_kv_local_default_path(tmp_path: Path) -> None:
    cfg = _cfg_with_kv("local")
    kv = open_kv(cfg, tmp_path, env={})
    assert isinstance(kv, LocalFileKV)
    kv.set("a", "b")
    assert (tmp_path / ".kv" / "store.json").exists()


def test_open_kv_local_env_override(tmp_path: Path) -> None:
    cfg = _cfg_with_kv("local")
    override = tmp_path / "custom.json"
    kv = open_kv(cfg, tmp_path, env={"KV_LOCAL_PATH": str(override)})
    kv.set("a", "b")
    assert override.exists()


def test_open_kv_upstash_requires_env_vars(tmp_path: Path) -> None:
    cfg = _cfg_with_kv("upstash")
    with pytest.raises(KVError, match="UPSTASH_REDIS_REST_URL"):
        open_kv(cfg, tmp_path, env={})


def test_open_kv_vercel_requires_env_vars(tmp_path: Path) -> None:
    cfg = _cfg_with_kv("vercel-kv")
    with pytest.raises(KVError, match="KV_REST_API_URL"):
        open_kv(cfg, tmp_path, env={})
