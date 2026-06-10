"""v5.19/B5 — timer-start path traversal is constrained to registered projects."""

from __future__ import annotations

from pathlib import Path

import pytest

from halyard import hub_server


def _make_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    return root


def test_b5_registered_dir_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reg = _make_project(tmp_path / "proj")
    monkeypatch.setattr("halyard.registry.read_registry", lambda: [reg])
    assert hub_server._target_project_dir({"project_dir": str(reg)}) == reg.resolve()


def test_b5_unregistered_dir_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reg = _make_project(tmp_path / "proj")
    evil = tmp_path / "evil"
    evil.mkdir()
    monkeypatch.setattr("halyard.registry.read_registry", lambda: [reg])
    # v5.19/B5-followup: a supplied-but-unregistered dir raises so the
    # handler surfaces 400 instead of silently rewriting the hub's ledger.
    with pytest.raises(hub_server._RejectedTargetDirError):
        hub_server._target_project_dir({"project_dir": str(evil)})


def test_b5_no_project_dir_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reg = _make_project(tmp_path / "proj")
    monkeypatch.setattr("halyard.registry.read_registry", lambda: [reg])
    # No client-supplied target → None → caller falls back to hub default.
    assert hub_server._target_project_dir({}) is None


def test_b5_timeclock_parent_also_constrained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reg = _make_project(tmp_path / "proj")
    evil = tmp_path / "evil"
    evil.mkdir()
    monkeypatch.setattr("halyard.registry.read_registry", lambda: [reg])
    # The timeclock-parent fallback is constrained the same way.
    with pytest.raises(hub_server._RejectedTargetDirError):
        hub_server._target_project_dir({"timeclock": str(evil / "time.timeclock")})
    assert (
        hub_server._target_project_dir({"timeclock": str(reg / "time.timeclock")}) == reg.resolve()
    )
