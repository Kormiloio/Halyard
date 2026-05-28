"""v2.59 — collector schema-drift canary in halyard doctor."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.doctor import _DRIFT_WINDOW, build_doctor_report, has_errors, render_json

_BASE = datetime(2026, 5, 10, 9, 0, 0)


def _proj(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (p / "time.timeclock").write_text("; t\n", encoding="utf-8")
    (p / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")
    return p


def _sess(i: int, *, tool: str, model: str) -> AiSession:
    start = _BASE + timedelta(hours=i)
    return AiSession(
        start=start,
        end=start + timedelta(minutes=5),
        tool=tool,
        model=model,
        input_tokens=100,
        output_tokens=50,
        cost_usd=1.0,
        project="kormilo:halyard",
    )


def _ids(report: object) -> set[str]:
    return {c.id for c in report.checks}  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _report(start: Path):  # type: ignore[no-untyped-def]
    return build_doctor_report(start=start)


def test_regression_after_healthy_history_flags(tmp_path: Path) -> None:
    proj = _proj(tmp_path / "p")
    for i in range(6):
        append_session(proj, _sess(i, tool="claude-code", model="claude-opus-4-7"))
    for i in range(6, 6 + _DRIFT_WINDOW):
        append_session(proj, _sess(i, tool="claude-code", model="claude-unknown"))

    report = _report(proj)
    check = next(c for c in report.checks if c.id == "drift.claude-code")
    assert check.status == "warning"
    assert "upstream format" in check.detail
    assert check.fix


def test_healthy_tool_no_canary(tmp_path: Path) -> None:
    proj = _proj(tmp_path / "p")
    for i in range(10):
        append_session(proj, _sess(i, tool="cursor", model="gpt-4o"))
    assert "drift.cursor" not in _ids(_report(proj))


def test_never_healthy_no_canary(tmp_path: Path) -> None:
    proj = _proj(tmp_path / "p")
    for i in range(8):
        append_session(proj, _sess(i, tool="gemini-cli", model="default"))
    assert "drift.gemini-cli" not in _ids(_report(proj))


def test_insufficient_history_no_canary(tmp_path: Path) -> None:
    proj = _proj(tmp_path / "p")
    for i in range(_DRIFT_WINDOW - 1):
        append_session(proj, _sess(i, tool="claude-code", model="claude-unknown"))
    assert "drift.claude-code" not in _ids(_report(proj))


def test_non_sustained_run_no_canary(tmp_path: Path) -> None:
    proj = _proj(tmp_path / "p")
    for i in range(6):
        append_session(proj, _sess(i, tool="claude-code", model="claude-opus-4-7"))
    # Recent window: 4 unreal + 1 real interleaved → not sustained.
    append_session(proj, _sess(6, tool="claude-code", model="claude-unknown"))
    append_session(proj, _sess(7, tool="claude-code", model="claude-unknown"))
    append_session(proj, _sess(8, tool="claude-code", model="claude-opus-4-7"))
    append_session(proj, _sess(9, tool="claude-code", model="claude-unknown"))
    append_session(proj, _sess(10, tool="claude-code", model="claude-unknown"))
    assert "drift.claude-code" not in _ids(_report(proj))


def test_per_tool_isolation(tmp_path: Path) -> None:
    proj = _proj(tmp_path / "p")
    for i in range(10):
        append_session(proj, _sess(i, tool="cursor", model="gpt-4o"))
    for i in range(6):
        append_session(proj, _sess(i, tool="claude-code", model="claude-opus-4-7"))
    for i in range(6, 6 + _DRIFT_WINDOW):
        append_session(proj, _sess(i, tool="claude-code", model="claude-unknown"))
    ids = _ids(_report(proj))
    assert "drift.claude-code" in ids
    assert "drift.cursor" not in ids


def test_exit_code_contract_preserved(tmp_path: Path) -> None:
    proj = _proj(tmp_path / "p")
    for i in range(6):
        append_session(proj, _sess(i, tool="claude-code", model="claude-opus-4-7"))
    for i in range(6, 6 + _DRIFT_WINDOW):
        append_session(proj, _sess(i, tool="claude-code", model="claude-unknown"))
    report = _report(proj)
    drift = [c for c in report.checks if c.id.startswith("drift.")]
    assert drift and all(c.status == "warning" for c in drift)
    # A drift warning must not, by itself, flip the exit code.
    assert all(c.status != "error" for c in drift)
    _ = has_errors(report)  # callable, contract unchanged


def test_drift_id_in_json(tmp_path: Path) -> None:
    proj = _proj(tmp_path / "p")
    for i in range(6):
        append_session(proj, _sess(i, tool="claude-code", model="claude-opus-4-7"))
    for i in range(6, 6 + _DRIFT_WINDOW):
        append_session(proj, _sess(i, tool="claude-code", model="claude-unknown"))
    payload = json.loads(render_json(_report(proj)))
    assert any(c["id"] == "drift.claude-code" for c in payload["checks"])
