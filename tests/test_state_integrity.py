"""Tests for halyard.state_integrity (phase 1 — hash mode)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from halyard import state_integrity
from halyard.state_integrity import (
    IntegrityError,
    current_mode,
    read_global_trusted_state,
    read_trusted_state,
    verify_all,
    write_trusted_state,
)


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-local mode cache so each test starts clean."""
    state_integrity._reset_cache_for_tests()
    monkeypatch.delenv("HALYARD_STATE_INTEGRITY", raising=False)


# ---------------------------------------------------------------------------
# current_mode
# ---------------------------------------------------------------------------


def test_default_mode_is_off() -> None:
    assert current_mode() == "off"


def test_mode_from_toml(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text('state_integrity = "hash"\n', encoding="utf-8")
    assert current_mode(tmp_path) == "hash"


def test_env_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HALYARD_STATE_INTEGRITY", "hash")
    assert current_mode() == "hash"


def test_invalid_mode_in_toml_falls_back(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text('state_integrity = "bogus"\n', encoding="utf-8")
    assert current_mode(tmp_path) == "off"


# ---------------------------------------------------------------------------
# off mode — pass-through
# ---------------------------------------------------------------------------


def test_read_off_mode_returns_content_verbatim(tmp_path: Path) -> None:
    p = tmp_path / "active"
    p.write_text("slug=acme:auth\n", encoding="utf-8")
    assert read_trusted_state(p, mode="off") == "slug=acme:auth\n"


def test_write_off_mode_does_not_create_sidecar(tmp_path: Path) -> None:
    p = tmp_path / "active"
    write_trusted_state(p, "slug=acme\n", mode="off")
    assert p.read_text(encoding="utf-8") == "slug=acme\n"
    assert not (tmp_path / "active.sha256").exists()


def test_read_missing_file_returns_none(tmp_path: Path) -> None:
    assert read_trusted_state(tmp_path / "nonexistent", mode="hash") is None


# ---------------------------------------------------------------------------
# hash mode — sidecar lifecycle
# ---------------------------------------------------------------------------


def test_write_hash_mode_creates_sidecar(tmp_path: Path) -> None:
    p = tmp_path / "active"
    content = "slug=acme:auth\n"
    write_trusted_state(p, content, mode="hash")

    sidecar = tmp_path / "active.sha256"
    assert sidecar.exists()
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert sidecar.read_text(encoding="utf-8").strip() == expected


def test_read_hash_mode_verifies_match(tmp_path: Path) -> None:
    p = tmp_path / "active"
    write_trusted_state(p, "slug=acme\n", mode="hash")
    assert read_trusted_state(p, mode="hash") == "slug=acme\n"


def test_tampered_file_raises(tmp_path: Path) -> None:
    p = tmp_path / "active"
    write_trusted_state(p, "slug=acme\n", mode="hash")
    p.write_text("slug=evil\n", encoding="utf-8")  # tamper

    with pytest.raises(IntegrityError, match="Integrity mismatch"):
        read_trusted_state(p, mode="hash")


def test_missing_sidecar_raises(tmp_path: Path) -> None:
    p = tmp_path / "active"
    p.write_text("slug=acme\n", encoding="utf-8")  # no sidecar

    with pytest.raises(IntegrityError, match="Missing integrity sidecar"):
        read_trusted_state(p, mode="hash")


def test_verify_all_returns_first_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HALYARD_STATE_INTEGRITY", "hash")
    state_integrity._reset_cache_for_tests()

    a = tmp_path / "a"
    b = tmp_path / "b"
    write_trusted_state(a, "good\n", mode="hash")
    write_trusted_state(b, "good\n", mode="hash")
    b.write_text("tampered\n", encoding="utf-8")  # break b

    ok, failure = verify_all([a, b])
    assert not ok
    assert failure == b


# ---------------------------------------------------------------------------
# read_active_project & find_hub fail-closed-but-soft on tamper
# ---------------------------------------------------------------------------


def test_read_active_project_returns_none_on_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HALYARD_STATE_INTEGRITY", "hash")
    state_integrity._reset_cache_for_tests()
    from halyard.ai_log import read_active_project

    active = tmp_path / ".halyard" / "active"
    write_trusted_state(active, "slug=acme\n", mode="hash")
    active.write_text("slug=evil\n", encoding="utf-8")  # tamper

    # Should log + return None, not crash
    assert read_active_project() is None


def test_find_hub_returns_none_on_tamper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HALYARD_STATE_INTEGRITY", "hash")
    state_integrity._reset_cache_for_tests()
    from halyard.hub import find_hub

    pointer = tmp_path / ".halyard" / "hub"
    fake_hub = tmp_path / "fake_hub"
    fake_hub.mkdir()
    write_trusted_state(pointer, str(fake_hub) + "\n", mode="hash")
    pointer.write_text("/some/evil/path\n", encoding="utf-8")  # tamper

    assert find_hub() is None


# ---------------------------------------------------------------------------
# read_global_trusted_state — sidecar auto-detect prevents downgrade-on-default
# ---------------------------------------------------------------------------
# Threat model: a sidecar on disk proves integrity *was* enabled at write
# time. A later process where current_mode() resolves to "off" (env unset,
# no project halyard.toml) must NOT silently trust unverified content
# alongside that sidecar. The shared helper raises ``mode`` from off to
# the sidecar's mode before reading.


def test_global_helper_uses_sidecar_when_default_off(tmp_path: Path) -> None:
    p = tmp_path / "active"
    write_trusted_state(p, "slug=acme\n", mode="hash")
    # current_mode() resolves to "off" (no env override, no project).
    # Sidecar exists from the prior write — helper must honor it.
    assert read_global_trusted_state(p) == "slug=acme\n"


def test_global_helper_raises_on_tamper_when_default_off(tmp_path: Path) -> None:
    p = tmp_path / "active"
    write_trusted_state(p, "slug=acme\n", mode="hash")
    p.write_text("slug=evil\n", encoding="utf-8")  # tamper, sidecar untouched

    with pytest.raises(IntegrityError):
        read_global_trusted_state(p)


def test_global_helper_returns_none_for_missing_file(tmp_path: Path) -> None:
    p = tmp_path / "active"
    # No file, no sidecar — absence is not tampering.
    assert read_global_trusted_state(p) is None


def test_read_active_project_blocks_downgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: in default runtime (mode resolves to off), a tampered
    ``~/.halyard/active`` with a stale sidecar must NOT be silently
    accepted. This is the P1 finding fixed by routing
    read_active_project through read_global_trusted_state.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("HALYARD_STATE_INTEGRITY", raising=False)
    state_integrity._reset_cache_for_tests()
    from halyard.ai_log import read_active_project

    active = tmp_path / ".halyard" / "active"
    # Write under hash mode explicitly so the sidecar exists, then drop
    # the env override and tamper the content. With mode resolving to
    # off, the previous implementation would have returned "evil".
    write_trusted_state(active, "slug=acme\n", mode="hash")
    active.write_text("slug=evil\n", encoding="utf-8")

    assert read_active_project() is None


def test_find_hub_blocks_downgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: same sidecar-downgrade defense for the hub pointer."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("HALYARD_STATE_INTEGRITY", raising=False)
    state_integrity._reset_cache_for_tests()
    from halyard.hub import find_hub

    pointer = tmp_path / ".halyard" / "hub"
    fake_hub = tmp_path / "fake_hub"
    fake_hub.mkdir()
    write_trusted_state(pointer, str(fake_hub) + "\n", mode="hash")
    pointer.write_text("/some/evil/path\n", encoding="utf-8")  # tamper

    assert find_hub() is None
