"""v2.57 — active-timer state is integrity-verified (P1-c)."""

from __future__ import annotations

from pathlib import Path

import pytest

from halyard import state_integrity
from halyard.orchestration import write_active_timer
from halyard.reports import read_active_timer


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    state_integrity._reset_cache_for_tests()
    monkeypatch.delenv("HALYARD_STATE_INTEGRITY", raising=False)


def _project(tmp_path: Path, mode: str | None) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    # Top-level key MUST precede any table header to stay top-level.
    toml = (f'state_integrity = "{mode}"\n' if mode else "") + "[business]\n"
    (proj / "halyard.toml").write_text(toml, encoding="utf-8")
    (proj / "time.timeclock").write_text("; t\n", encoding="utf-8")
    return proj


def _wire_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    active = tmp_path / "active"
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", active)
    import halyard.orchestration as orch

    monkeypatch.setattr(orch._reports_mod, "_HALYARD_ACTIVE", active)
    return active


def test_hash_mode_writes_sidecar_and_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = _project(tmp_path, "hash")
    active = _wire_active(tmp_path, monkeypatch)

    write_active_timer(proj / "time.timeclock", "acme:web", "2026-05-16 09:00:00")

    # Sidecar created (integrity actually active for the global file).
    assert state_integrity.detect_sidecar_mode(active) == "hash"
    timer = read_active_timer()
    assert timer is not None and timer.slug == "acme:web"


def test_tampered_active_file_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proj = _project(tmp_path, "hash")
    active = _wire_active(tmp_path, monkeypatch)
    write_active_timer(proj / "time.timeclock", "acme:web", "2026-05-16 09:00:00")

    # Attacker rewrites the slug without updating the sidecar.
    active.write_text(
        active.read_text(encoding="utf-8").replace("acme:web", "evil:exfil"), encoding="utf-8"
    )

    # Fail closed: verification now applies, so the tampered timer is
    # not trusted (previously this returned the forged slug).
    assert read_active_timer() is None


def test_downgrade_via_tampered_path_is_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = _project(tmp_path, "hash")
    active = _wire_active(tmp_path, monkeypatch)
    write_active_timer(proj / "time.timeclock", "acme:web", "2026-05-16 09:00:00")

    # Repoint timeclock= at a dir with no halyard.toml (mode would
    # resolve to "off") AND change the slug. The sidecar still exists,
    # so verification must NOT downgrade to off.
    noproj = tmp_path / "noproj"
    noproj.mkdir()
    tampered = (
        f"timeclock={noproj / 'time.timeclock'}\nslug=evil:exfil\nstarted=2026-05-16 09:00:00\n"
    )
    active.write_text(tampered, encoding="utf-8")

    assert read_active_timer() is None


def test_off_mode_unchanged_behaviour(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proj = _project(tmp_path, None)  # no state_integrity → off
    active = _wire_active(tmp_path, monkeypatch)
    write_active_timer(proj / "time.timeclock", "acme:web", "2026-05-16 09:00:00")

    assert state_integrity.detect_sidecar_mode(active) is None
    timer = read_active_timer()
    assert timer is not None and timer.slug == "acme:web"
