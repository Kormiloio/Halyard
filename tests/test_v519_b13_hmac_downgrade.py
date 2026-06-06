"""v5.19/B13 — an existing HMAC sidecar cannot be downgraded to hash/off.

Audit blocker B13: the integrity mode is resolved through an
attacker-controlled pointer/config, but the .hmac sidecar on disk is a trusted
signal (unforgeable without integrity.key). Verification must never use a mode
weaker than the file's sidecar implies.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from halyard import state_integrity as si


@pytest.fixture(autouse=True)
def _isolated_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(si, "_KEY_PATH", tmp_path / "integrity.key")
    monkeypatch.delenv("HALYARD_STATE_INTEGRITY", raising=False)
    si._reset_cache_for_tests()


def test_b13_hmac_cannot_be_downgraded_to_hash_or_off(tmp_path: Path) -> None:
    p = tmp_path / "active"
    si.write_trusted_state(p, "legit-pointer\n", mode="hmac")
    assert si._sidecar(p, "hmac").exists()
    assert si.read_trusted_state(p, mode="hmac") == "legit-pointer\n"

    # Attacker forges the content and writes a matching *unkeyed* sha256 sidecar
    # (no key needed), then steers config to the weaker "hash" (or "off").
    p.write_text("FORGED\n", encoding="utf-8")
    si._sidecar(p, "hash").write_text(hashlib.sha256(b"FORGED\n").hexdigest(), encoding="utf-8")

    # The .hmac sidecar (for the original content) still exists and is stronger,
    # so verification upgrades to hmac and the forgery is rejected.
    with pytest.raises(si.IntegrityError):
        si.read_trusted_state(p, mode="hash")
    with pytest.raises(si.IntegrityError):
        si.read_trusted_state(p, mode="off")
    # The canonical global entry point is protected too.
    with pytest.raises(si.IntegrityError):
        si.read_global_trusted_state(p)


def test_b13_genuine_hash_only_file_still_reads(tmp_path: Path) -> None:
    # Guard against over-restriction: a file with only a hash sidecar and
    # mode=hash still verifies normally (no phantom hmac requirement).
    p = tmp_path / "active"
    si.write_trusted_state(p, "ok\n", mode="hash")
    assert not si._sidecar(p, "hmac").exists()
    assert si.read_trusted_state(p, mode="hash") == "ok\n"
