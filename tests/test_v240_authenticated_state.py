"""Regression tests for v2.40 authenticated (HMAC) state integrity."""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path

import pytest

from halyard import state_integrity
from halyard.state_integrity import (
    IntegrityError,
    read_trusted_state,
    write_trusted_state,
)


@pytest.fixture(autouse=True)
def _key_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(state_integrity, "_KEY_PATH", tmp_path / "integrity.key")
    state_integrity._reset_cache_for_tests()
    monkeypatch.delenv("HALYARD_STATE_INTEGRITY", raising=False)


def test_hmac_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "active"
    write_trusted_state(p, "slug=acme\n", mode="hmac")
    assert (tmp_path / "active.hmac").exists()
    assert not (tmp_path / "active.sha256").exists()
    assert read_trusted_state(p, mode="hmac") == "slug=acme\n"


def test_hmac_detects_data_tamper(tmp_path: Path) -> None:
    p = tmp_path / "active"
    write_trusted_state(p, "slug=acme\n", mode="hmac")
    p.write_text("slug=evil\n", encoding="utf-8")
    with pytest.raises(IntegrityError, match="Integrity mismatch"):
        read_trusted_state(p, mode="hmac")


def test_hmac_beats_the_attack_that_defeats_hash(tmp_path: Path) -> None:
    """Attacker rewrites the file AND a plain SHA-256 sidecar — the exact
    move that defeats `hash` mode. HMAC must still reject it."""
    p = tmp_path / "active"
    write_trusted_state(p, "slug=acme\n", mode="hmac")
    p.write_text("slug=evil\n", encoding="utf-8")
    # Forge an *unkeyed* digest the way a hash-mode attacker would.
    (tmp_path / "active.hmac").write_text(
        hashlib.sha256(b"slug=evil\n").hexdigest() + "\n", encoding="utf-8"
    )
    with pytest.raises(IntegrityError, match="Integrity mismatch"):
        read_trusted_state(p, mode="hmac")


def test_hmac_key_holder_can_forge_documented_limitation(tmp_path: Path) -> None:
    """Honest boundary: an attacker who can read the 0600 key CAN forge.
    This test documents the limitation rather than asserting false safety."""
    import hmac as _hmac

    p = tmp_path / "active"
    write_trusted_state(p, "slug=acme\n", mode="hmac")
    key = bytes.fromhex((tmp_path / "integrity.key").read_text().strip())
    p.write_text("slug=evil\n", encoding="utf-8")
    (tmp_path / "active.hmac").write_text(
        _hmac.new(key, b"slug=evil\n", hashlib.sha256).hexdigest() + "\n",
        encoding="utf-8",
    )
    assert read_trusted_state(p, mode="hmac") == "slug=evil\n"


def test_hmac_fails_closed_without_key(tmp_path: Path) -> None:
    p = tmp_path / "active"
    write_trusted_state(p, "slug=acme\n", mode="hmac")
    (tmp_path / "integrity.key").unlink()
    with pytest.raises(IntegrityError, match="Missing integrity key"):
        read_trusted_state(p, mode="hmac")


def test_key_file_is_0600(tmp_path: Path) -> None:
    write_trusted_state(tmp_path / "active", "x\n", mode="hmac")
    mode = stat.S_IMODE((tmp_path / "integrity.key").stat().st_mode)
    assert mode == 0o600


def test_hash_mode_still_works(tmp_path: Path) -> None:
    p = tmp_path / "active"
    write_trusted_state(p, "slug=acme\n", mode="hash")
    assert (tmp_path / "active.sha256").exists()
    assert read_trusted_state(p, mode="hash") == "slug=acme\n"


def test_hmac_mode_resolves_from_toml_and_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "halyard.toml").write_text('state_integrity = "hmac"\n')
    state_integrity._reset_cache_for_tests()
    assert state_integrity.current_mode(tmp_path) == "hmac"
    monkeypatch.setenv("HALYARD_STATE_INTEGRITY", "hmac")
    assert state_integrity.current_mode() == "hmac"
