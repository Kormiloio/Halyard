"""Tests for Gemini CLI history file parser."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import halyard.collectors.gemini_history as gh_mod
from halyard.collectors.gemini_history import (
    find_session_file,
    parse_session_file,
    project_dir_for_slug,
)


def _make_session(
    session_id: str = "abcd1234-0000-0000-0000-000000000000",
    start: str = "2026-05-07T10:00:00.000Z",
    end: str = "2026-05-07T11:00:00.000Z",
    messages: list[dict] | None = None,
) -> dict:
    if messages is None:
        messages = []
    return {
        "sessionId": session_id,
        "startTime": start,
        "lastUpdated": end,
        "messages": messages,
        "kind": "session",
    }


def _gemini_msg(
    model: str = "gemini-2.5-flash",
    inp: int = 10000,
    out: int = 500,
    cached: int = 0,
    thoughts: int = 0,
    tool_calls: list[dict] | None = None,
) -> dict:
    return {
        "type": "gemini",
        "model": model,
        "tokens": {
            "input": inp,
            "output": out,
            "cached": cached,
            "thoughts": thoughts,
            "total": inp + out,
        },
        "toolCalls": tool_calls or [],
    }


def _tool(name: str = "run_shell_command", status: str = "success") -> dict:
    return {"id": "x", "name": name, "status": status}


# ---------------------------------------------------------------------------
# parse_session_file
# ---------------------------------------------------------------------------


def test_parse_session_file_single_model(tmp_path: Path) -> None:
    f = tmp_path / "session-2026-05-07T10-00-abcd1234.json"
    f.write_text(json.dumps(_make_session(messages=[
        _gemini_msg(model="gemini-2.5-flash", inp=10000, out=500, cached=2000),
    ])))
    s = parse_session_file(f)
    assert s is not None
    assert len(s.model_stats) == 1
    assert s.model_stats[0].model == "gemini-2.5-flash"
    assert s.model_stats[0].input_tokens == 8000  # 10000 - 2000 cached
    assert s.model_stats[0].output_tokens == 500
    assert s.model_stats[0].cache_tokens == 2000
    assert s.dominant_model == "gemini-2.5-flash"
    assert s.total_input == 8000
    assert s.total_output == 500
    assert s.total_cache == 2000


def test_parse_session_file_multi_model(tmp_path: Path) -> None:
    f = tmp_path / "session-2026-05-07T10-00-abcd1234.json"
    f.write_text(json.dumps(_make_session(messages=[
        _gemini_msg(model="gemini-2.5-flash", inp=5000, out=50),
        _gemini_msg(model="gemini-2.5-pro", inp=100000, out=800, cached=50000),
        _gemini_msg(model="gemini-2.5-flash", inp=20000, out=200),
    ])))
    s = parse_session_file(f)
    assert s is not None
    assert len(s.model_stats) == 2  # two distinct models
    # dominant = gemini-2.5-pro (800 output)
    assert s.dominant_model == "gemini-2.5-pro"
    # cost is summed across all models — both are in PRICING so cost > 0
    assert s.cost_usd > 0
    assert s.total_output == 50 + 800 + 200


def test_parse_session_file_thinking_tokens(tmp_path: Path) -> None:
    f = tmp_path / "session-2026-05-07T10-00-abcd1234.json"
    f.write_text(json.dumps(_make_session(messages=[
        _gemini_msg(model="gemini-2.5-flash", inp=10000, out=500, thoughts=200),
    ])))
    s = parse_session_file(f)
    assert s is not None
    # thinking tokens billed as additional input
    assert s.model_stats[0].thinking_tokens == 200
    # cost includes thinking: calculate_cost called with input_tokens + thinking_tokens
    from halyard.pricing import calculate_cost
    expected = calculate_cost("gemini-2.5-flash", 10000 + 200, 500)
    assert abs(s.cost_usd - expected) < 0.0001


def test_parse_session_file_tool_calls(tmp_path: Path) -> None:
    f = tmp_path / "session-2026-05-07T10-00-abcd1234.json"
    f.write_text(json.dumps(_make_session(messages=[
        _gemini_msg(tool_calls=[
            _tool("run_shell_command", "success"),
            _tool("read_file", "success"),
            _tool("glob", "error"),
        ]),
    ])))
    s = parse_session_file(f)
    assert s is not None
    assert s.total_tool_calls == 3
    assert s.total_tool_errors == 1


def test_parse_session_file_no_gemini_messages(tmp_path: Path) -> None:
    f = tmp_path / "session.json"
    f.write_text(json.dumps(_make_session(messages=[
        {"type": "user", "content": "hello"},
        {"type": "info", "content": "info msg"},
    ])))
    s = parse_session_file(f)
    assert s is not None
    assert s.model_stats == []
    assert s.dominant_model == ""
    assert s.cost_usd == 0.0


def test_parse_session_file_malformed_json(tmp_path: Path) -> None:
    f = tmp_path / "session.json"
    f.write_text("not valid json ][[[")
    assert parse_session_file(f) is None


def test_parse_session_file_missing_file(tmp_path: Path) -> None:
    assert parse_session_file(tmp_path / "nonexistent.json") is None


def test_parse_session_file_missing_session_id(tmp_path: Path) -> None:
    f = tmp_path / "session.json"
    data = _make_session()
    del data["sessionId"]
    f.write_text(json.dumps(data))
    assert parse_session_file(f) is None


# ---------------------------------------------------------------------------
# find_session_file
# ---------------------------------------------------------------------------


def test_find_session_file_found(tmp_path: Path) -> None:
    session_id = "abcd1234-0000-0000-0000-000000000000"
    chats = tmp_path / "myproject" / "chats"
    chats.mkdir(parents=True)
    f = chats / "session-2026-05-07T10-00-abcd1234.json"
    f.write_text("{}")

    with patch.object(gh_mod, "_GEMINI_TMP", tmp_path):
        result = find_session_file(session_id)
    assert result == f


def test_find_session_file_not_found(tmp_path: Path) -> None:
    with patch.object(gh_mod, "_GEMINI_TMP", tmp_path):
        result = find_session_file("ffffffff-0000-0000-0000-000000000000")
    assert result is None


def test_find_session_file_multiple_matches_returns_newest(tmp_path: Path) -> None:
    import time

    session_id = "abcd1234-0000-0000-0000-000000000000"
    for slug in ("proj-a", "proj-b"):
        chats = tmp_path / slug / "chats"
        chats.mkdir(parents=True)
        (chats / "session-2026-05-07T10-00-abcd1234.json").write_text("{}")
        time.sleep(0.01)  # ensure different mtime

    with patch.object(gh_mod, "_GEMINI_TMP", tmp_path):
        result = find_session_file(session_id)
    assert result is not None
    # Most recently modified wins
    assert result.parent.parent.name == "proj-b"


# ---------------------------------------------------------------------------
# project_dir_for_slug
# ---------------------------------------------------------------------------


def test_project_dir_for_slug_found(tmp_path: Path) -> None:
    slug_dir = tmp_path / "myproject"
    slug_dir.mkdir()
    (slug_dir / ".project_root").write_text("/home/user/projects/myproject\n")
    with patch.object(gh_mod, "_GEMINI_HISTORY", tmp_path):
        result = project_dir_for_slug("myproject")
    assert result == Path("/home/user/projects/myproject")


def test_project_dir_for_slug_absent(tmp_path: Path) -> None:
    with patch.object(gh_mod, "_GEMINI_HISTORY", tmp_path):
        result = project_dir_for_slug("nonexistent")
    assert result is None
