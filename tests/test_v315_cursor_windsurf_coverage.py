"""v3.15 — coverage canary extended to Cursor and Windsurf.

These tools keep state in SQLite/leveldb stores (no enumerable per-session
files), so the canary uses coarse storage mtimes with a wider grace
(`_COVERAGE_LAG_DAYS_COARSE`). Tests drive `_capture_coverage_checks` with a
monkeypatched `_newest_disk_activity` so they assert the policy, not the disk.
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
            model="gpt-4o" if tool == "cursor" else "windsurf-model",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.0,
            session_id="s1",
            source="hook",
        ),
    )


def _disk(**by_tool: datetime):
    return lambda tool: by_tool.get(tool)


def test_cursor_disk_older_than_capture_no_warning(tmp_path: Path) -> None:
    """The current real state: Cursor unused since before its last capture —
    storage mtime older than the last row — must NOT warn (not broken)."""
    tmp = _init(tmp_path / "p")
    _seed(tmp, "cursor", _NOW - timedelta(days=2))  # last captured 2d ago
    with patch.object(doc, "_newest_disk_activity", _disk(cursor=_NOW - timedelta(days=5))):
        checks = _capture_coverage_checks(tmp, None)
    assert not any(c.id == "coverage.cursor" for c in checks)


def test_cursor_warns_when_disk_newer_beyond_coarse_grace(tmp_path: Path) -> None:
    tmp = _init(tmp_path / "p")
    _seed(tmp, "cursor", _NOW - timedelta(days=10))  # captured 10d ago
    with patch.object(doc, "_newest_disk_activity", _disk(cursor=_NOW)):  # active today
        checks = _capture_coverage_checks(tmp, None)
    by_id = {c.id: c for c in checks}
    assert "coverage.cursor" in by_id
    chk = by_id["coverage.cursor"]
    assert chk.status == "warning"
    assert "best-effort" in chk.detail
    assert chk.fix and "install-hook-cursor" in chk.fix


def test_coarse_grace_is_wider_than_precise(tmp_path: Path) -> None:
    """A 3-day lag warns a file-precise tool (2d grace) but NOT a coarse tool
    (4d grace) — proving the wider grace absorbs noisier db mtimes."""
    tmp = _init(tmp_path / "p")
    _seed(tmp, "cursor", _NOW - timedelta(days=3))
    with patch.object(doc, "_newest_disk_activity", _disk(cursor=_NOW)):
        checks = _capture_coverage_checks(tmp, None)
    assert not any(c.id == "coverage.cursor" for c in checks)


def test_windsurf_warns_beyond_coarse_grace(tmp_path: Path) -> None:
    tmp = _init(tmp_path / "p")
    _seed(tmp, "windsurf", _NOW - timedelta(days=10))
    with patch.object(doc, "_newest_disk_activity", _disk(windsurf=_NOW)):
        checks = _capture_coverage_checks(tmp, None)
    by_id = {c.id: c for c in checks}
    assert "coverage.windsurf" in by_id
    assert (
        by_id["coverage.windsurf"].fix and "install-hook-windsurf" in by_id["coverage.windsurf"].fix
    )


def test_no_warning_without_baseline(tmp_path: Path) -> None:
    """A never-captured Cursor (fresh install) can't false-positive."""
    tmp = _init(tmp_path / "p")  # no cursor rows
    with patch.object(doc, "_newest_disk_activity", _disk(cursor=_NOW)):
        checks = _capture_coverage_checks(tmp, None)
    assert not any(c.id == "coverage.cursor" for c in checks)


def test_precise_tool_keeps_two_day_grace(tmp_path: Path) -> None:
    """Regression guard: adding the coarse tier must not widen the grace for the
    file-precise tools — a 3-day claude-code lag still warns."""
    tmp = _init(tmp_path / "p")
    append_session(
        tmp,
        AiSession(
            start=_NOW - timedelta(days=3, minutes=5),
            end=_NOW - timedelta(days=3),
            tool="claude-code",
            model="claude-opus-4-7",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.0,
            session_id="s1",
            source="hook",
        ),
    )
    with patch.object(doc, "_newest_disk_activity", _disk(**{"claude-code": _NOW})):
        checks = _capture_coverage_checks(tmp, None)
    assert any(c.id == "coverage.claude-code" for c in checks)
