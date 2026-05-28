"""v2.49 — stop/AfterAgent requires a recorded session start.

Cursor no-state skip is also covered by
test_cursor_collector.test_handle_stop_hook_skips_when_no_start_file;
with-state controls by the existing seeded collector tests. This file
pins the gemini no-state skip and a direct cursor no-state check.
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest


def _patch_stdin(payload: dict, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[type-arg]
    monkeypatch.setattr("sys.stdin", StringIO(json.dumps(payload)))


def test_cursor_stop_no_state_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard.collectors.cursor import handle_stop_hook

    missing = tmp_path / "cursor-session"  # never created
    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", missing)
    _patch_stdin(
        {"model": "claude-3.5-sonnet", "usage": {"input_tokens": 2000, "output_tokens": 400}},
        monkeypatch,
    )
    assert handle_stop_hook() == 0
    assert not missing.exists()  # nothing created/written


def test_gemini_afteragent_no_state_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard.collectors.gemini_cli import handle_agent_stop

    missing = tmp_path / "gc-session"  # SessionStart never ran
    monkeypatch.setattr("halyard.collectors.gemini_cli._GC_SESSION_FILE", missing)
    _patch_stdin(
        {"model": "gemini-2.0-pro", "usage": {"promptTokenCount": 100}},
        monkeypatch,
    )
    assert handle_agent_stop() == 0
    assert not missing.exists()


def test_gemini_afteragent_with_state_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Control: a recorded SessionStart + token-bearing turn is written.
    from datetime import datetime, timedelta

    from halyard.ai_log import AI_LOG_FILENAME, HEADER, parse_sessions
    from halyard.collectors.gemini_cli import handle_agent_stop

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (proj / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")
    gc = tmp_path / "gc-session"
    recent = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
    gc.write_text(
        json.dumps(
            {
                "turn_start": recent,
                "cwd": str(proj),
                "model": "gemini-2.0-pro",
                "prompt_tokens": 1200,
                "output_tokens": 300,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("halyard.collectors.gemini_cli._GC_SESSION_FILE", gc)
    monkeypatch.setattr("halyard.collectors.gemini_cli.read_active_project", lambda: None)
    monkeypatch.setattr("halyard.collectors.gemini_cli.find_project_dir", lambda **_: proj)
    monkeypatch.setattr("halyard.collectors.gemini_cli.find_hub", lambda: None)
    _patch_stdin({"cwd": str(proj)}, monkeypatch)

    assert handle_agent_stop() == 0
    assert len(parse_sessions(proj)) == 1
