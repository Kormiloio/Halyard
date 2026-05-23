"""v3.10 — doctor capture-coverage canary.

Catches a live-capture tool that silently stopped recording: on-disk session
files keep getting newer while the ledger stalls (the 2026-05 Gemini outage
that "hooks installed OK" and the drift canary both missed).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import halyard.doctor as doc
from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.doctor import _capture_coverage_checks

_NOW = datetime.now()


def _init(tmp: Path) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "halyard.toml").write_text("[business]\n")
    (tmp / AI_LOG_FILENAME).write_text(HEADER)
    return tmp


def _seed(tmp: Path, tool: str, end: datetime) -> None:
    append_session(
        tmp,
        AiSession(
            start=end - timedelta(minutes=5),
            end=end,
            tool=tool,
            model="claude-opus-4-7" if tool == "claude-code" else "gemini-3-flash-preview",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.0,
            session_id="s1",
            source="hook",
        ),
    )


def test_warns_when_disk_newer_than_ledger(tmp_path: Path) -> None:
    tmp = _init(tmp_path / "p")
    _seed(tmp, "claude-code", _NOW - timedelta(days=16))  # last captured 16d ago
    with patch.object(doc, "_newest_disk_activity", lambda tool: _NOW):  # disk is fresh today
        checks = _capture_coverage_checks(tmp, None)
    ids = {c.id: c for c in checks}
    assert "coverage.claude-code" in ids
    assert ids["coverage.claude-code"].status == "warning"
    assert "uncaptured" in ids["coverage.claude-code"].detail


def test_no_warning_when_ledger_fresh(tmp_path: Path) -> None:
    tmp = _init(tmp_path / "p")
    _seed(tmp, "claude-code", _NOW - timedelta(minutes=30))  # captured recently
    with patch.object(doc, "_newest_disk_activity", lambda tool: _NOW):
        checks = _capture_coverage_checks(tmp, None)
    assert not any(c.id.startswith("coverage.") for c in checks)


def test_no_warning_without_baseline(tmp_path: Path) -> None:
    """A tool that never captured a row can't false-positive (e.g. fresh install)."""
    tmp = _init(tmp_path / "p")  # no claude-code rows at all
    with patch.object(doc, "_newest_disk_activity", lambda tool: _NOW):
        checks = _capture_coverage_checks(tmp, None)
    assert not any(c.id.startswith("coverage.") for c in checks)


def test_grace_window_absorbs_small_lag(tmp_path: Path) -> None:
    tmp = _init(tmp_path / "p")
    _seed(tmp, "gemini-cli", _NOW - timedelta(days=1))  # 1d lag < 2d grace
    with patch.object(doc, "_newest_disk_activity", lambda tool: _NOW):
        checks = _capture_coverage_checks(tmp, None)
    assert not any(c.id.startswith("coverage.") for c in checks)
