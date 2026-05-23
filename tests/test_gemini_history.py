"""Tests for Gemini CLI history file parser."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import halyard.collectors.gemini_history as gh_mod
from halyard.collectors.gemini_history import (
    find_all_session_files,
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
    f.write_text(
        json.dumps(
            _make_session(
                messages=[
                    {"type": "user", "content": "hello"},
                    _gemini_msg(model="gemini-2.5-flash", inp=10000, out=500, cached=2000),
                ]
            )
        )
    )
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
    assert s.interaction_count == 2
    assert s.user_message_count == 1
    assert s.assistant_message_count == 1
    assert s.prompt_count == 1


def test_parse_session_file_multi_model(tmp_path: Path) -> None:
    f = tmp_path / "session-2026-05-07T10-00-abcd1234.json"
    f.write_text(
        json.dumps(
            _make_session(
                messages=[
                    _gemini_msg(model="gemini-2.5-flash", inp=5000, out=50),
                    _gemini_msg(model="gemini-2.5-pro", inp=100000, out=800, cached=50000),
                    _gemini_msg(model="gemini-2.5-flash", inp=20000, out=200),
                ]
            )
        )
    )
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
    f.write_text(
        json.dumps(
            _make_session(
                messages=[
                    _gemini_msg(model="gemini-2.5-flash", inp=10000, out=500, thoughts=200),
                ]
            )
        )
    )
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
    f.write_text(
        json.dumps(
            _make_session(
                messages=[
                    _gemini_msg(
                        tool_calls=[
                            _tool("run_shell_command", "success"),
                            _tool("read_file", "success"),
                            _tool("glob", "error"),
                        ]
                    ),
                ]
            )
        )
    )
    s = parse_session_file(f)
    assert s is not None
    assert s.total_tool_calls == 3
    assert s.total_tool_errors == 1


def test_parse_session_file_no_gemini_messages(tmp_path: Path) -> None:
    f = tmp_path / "session.json"
    f.write_text(
        json.dumps(
            _make_session(
                messages=[
                    {"type": "user", "content": "hello"},
                    {"type": "info", "content": "info msg"},
                ]
            )
        )
    )
    s = parse_session_file(f)
    assert s is not None
    assert s.model_stats == []
    assert s.dominant_model == ""
    assert s.cost_usd == 0.0
    assert s.interaction_count == 1
    assert s.user_message_count == 1
    assert s.assistant_message_count == 0


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
    f.write_text(json.dumps(_make_session(session_id=session_id)))

    with patch.object(gh_mod, "_GEMINI_TMP", tmp_path):
        result = find_session_file(session_id)
    assert result == f


def test_find_session_file_not_found(tmp_path: Path) -> None:
    with patch.object(gh_mod, "_GEMINI_TMP", tmp_path):
        result = find_session_file("ffffffff-0000-0000-0000-000000000000")
    assert result is None


def test_find_session_file_multiple_exact_matches_returns_newest(tmp_path: Path) -> None:
    import time

    session_id = "abcd1234-0000-0000-0000-000000000000"
    for slug in ("proj-a", "proj-b"):
        chats = tmp_path / slug / "chats"
        chats.mkdir(parents=True)
        (chats / "session-2026-05-07T10-00-abcd1234.json").write_text(
            json.dumps(_make_session(session_id=session_id))
        )
        time.sleep(0.01)  # ensure different mtime

    with patch.object(gh_mod, "_GEMINI_TMP", tmp_path):
        result = find_session_file(session_id)
    assert result is not None
    # Most recently modified wins
    assert result.parent.parent.name == "proj-b"


def test_find_session_file_rejects_prefix_match_without_exact_session_id(tmp_path: Path) -> None:
    session_id = "abcd1234-0000-0000-0000-000000000000"
    chats = tmp_path / "myproject" / "chats"
    chats.mkdir(parents=True)
    f = chats / "session-2026-05-07T10-00-abcd1234.json"
    f.write_text(json.dumps(_make_session(session_id="abcd1234-9999-0000-0000-000000000000")))

    with patch.object(gh_mod, "_GEMINI_TMP", tmp_path):
        result = find_session_file(session_id)
    assert result is None


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


# ---------------------------------------------------------------------------
# Rich session telemetry enrichment (v2.6)
# ---------------------------------------------------------------------------


def test_parse_session_file_rich_telemetry(tmp_path: Path) -> None:
    data = _make_session(
        session_id="rich-session-abc123",
        messages=[_gemini_msg(tool_calls=[{"status": "success"}, {"status": "error"}])],
    )
    data["codeStats"] = {"added": 45, "removed": 12}
    path = tmp_path / "session.json"
    path.write_text(json.dumps(data))

    summary = parse_session_file(path)

    assert summary is not None
    assert summary.total_tool_calls == 2
    assert summary.total_tool_errors == 1
    assert summary.code_added == 45
    assert summary.code_removed == 12
    assert summary.resume_command == "gemini --resume rich-session-abc123"


def test_parse_session_file_no_code_stats(tmp_path: Path) -> None:
    data = _make_session(messages=[_gemini_msg()])
    path = tmp_path / "session.json"
    path.write_text(json.dumps(data))

    summary = parse_session_file(path)

    assert summary is not None
    assert summary.code_added is None
    assert summary.code_removed is None


def test_parse_session_file_resume_command_from_session_id(tmp_path: Path) -> None:
    data = _make_session(session_id="my-session-xyz", messages=[_gemini_msg()])
    path = tmp_path / "session.json"
    path.write_text(json.dumps(data))

    summary = parse_session_file(path)

    assert summary is not None
    assert summary.resume_command == "gemini --resume my-session-xyz"


# ---------------------------------------------------------------------------
# .jsonl rollout format (v3.8)
# ---------------------------------------------------------------------------


def _rollout(
    session_id: str = "abcd1234-0000-0000-0000-000000000000",
    start: str = "2026-05-23T10:00:00.000Z",
    last_updated: str = "2026-05-23T11:00:00.000Z",
    events: list[dict] | None = None,
) -> str:
    """Build a line-delimited rollout: header line + event lines."""
    lines = [
        {
            "sessionId": session_id,
            "projectHash": "deadbeef",
            "startTime": start,
            "lastUpdated": last_updated,
            "kind": "main",
        }
    ]
    lines.extend(events or [])
    return "\n".join(json.dumps(line) for line in lines) + "\n"


def _rollout_user(text: str = "hello", msg_id: str = "u1") -> dict:
    return {
        "id": msg_id,
        "timestamp": "2026-05-23T10:01:00.000Z",
        "type": "user",
        "content": [{"text": text}],
    }


def _rollout_gemini(
    msg_id: str = "g1",
    model: str = "gemini-3-flash-preview",
    inp: int = 10000,
    out: int = 500,
    cached: int = 0,
    thoughts: int = 0,
    tool_calls: list[dict] | None = None,
    total: int | None = None,
    timestamp: str = "2026-05-23T10:02:00.000Z",
) -> dict:
    return {
        "id": msg_id,
        "timestamp": timestamp,
        "type": "gemini",
        "model": model,
        "tokens": {
            "input": inp,
            "output": out,
            "cached": cached,
            "thoughts": thoughts,
            "tool": 0,
            "total": total if total is not None else inp + out,
        },
        "toolCalls": tool_calls or [],
    }


def test_parse_jsonl_single_model(tmp_path: Path) -> None:
    f = tmp_path / "session-2026-05-23T10-00-abcd1234.jsonl"
    f.write_text(
        _rollout(
            events=[
                _rollout_user(),
                _rollout_gemini(model="gemini-3-flash-preview", inp=10000, out=500, cached=2000),
            ]
        )
    )
    s = parse_session_file(f)
    assert s is not None
    assert len(s.model_stats) == 1
    assert s.model_stats[0].model == "gemini-3-flash-preview"
    assert s.model_stats[0].input_tokens == 8000  # 10000 - 2000 cached
    assert s.model_stats[0].output_tokens == 500
    assert s.model_stats[0].cache_tokens == 2000
    assert s.total_input == 8000
    assert s.user_message_count == 1
    assert s.assistant_message_count == 1
    assert s.resume_command == "gemini --resume abcd1234-0000-0000-0000-000000000000"


def test_parse_jsonl_dedupes_streamed_emissions(tmp_path: Path) -> None:
    """The same gemini id is re-emitted as it streams; only the final
    (largest-total) emission counts — summing every emission inflates ~30x."""
    f = tmp_path / "session-2026-05-23T10-00-abcd1234.jsonl"
    f.write_text(
        _rollout(
            events=[
                # message g1 streamed three times, growing each time
                _rollout_gemini(msg_id="g1", inp=5000, out=10, total=5010),
                _rollout_gemini(msg_id="g1", inp=5000, out=200, total=5200),
                _rollout_gemini(
                    msg_id="g1",
                    inp=5000,
                    out=400,
                    total=5400,
                    tool_calls=[_tool("read_file", "success")],
                ),
            ]
        )
    )
    s = parse_session_file(f)
    assert s is not None
    # one distinct message, not three
    assert s.assistant_message_count == 1
    assert len(s.model_stats) == 1
    assert s.model_stats[0].requests == 1
    # final emission wins: out=400, input counted once
    assert s.model_stats[0].input_tokens == 5000
    assert s.total_output == 400
    assert s.total_tool_calls == 1


def test_parse_jsonl_multi_model(tmp_path: Path) -> None:
    f = tmp_path / "session-2026-05-23T10-00-abcd1234.jsonl"
    f.write_text(
        _rollout(
            events=[
                _rollout_gemini(msg_id="g1", model="gemini-2.5-flash", inp=5000, out=50),
                _rollout_gemini(
                    msg_id="g2", model="gemini-2.5-pro", inp=100000, out=800, cached=50000
                ),
                _rollout_gemini(msg_id="g3", model="gemini-2.5-flash", inp=20000, out=200),
            ]
        )
    )
    s = parse_session_file(f)
    assert s is not None
    assert len(s.model_stats) == 2
    assert s.dominant_model == "gemini-2.5-pro"
    assert s.cost_usd > 0
    assert s.total_output == 50 + 800 + 200


def test_parse_jsonl_tool_calls_and_errors(tmp_path: Path) -> None:
    f = tmp_path / "session-2026-05-23T10-00-abcd1234.jsonl"
    f.write_text(
        _rollout(
            events=[
                _rollout_gemini(
                    msg_id="g1",
                    tool_calls=[
                        _tool("run_shell_command", "success"),
                        _tool("read_file", "success"),
                        _tool("glob", "error"),
                    ],
                )
            ]
        )
    )
    s = parse_session_file(f)
    assert s is not None
    assert s.total_tool_calls == 3
    assert s.total_tool_errors == 1


def test_parse_jsonl_end_advances_from_set_patch(tmp_path: Path) -> None:
    f = tmp_path / "session-2026-05-23T10-00-abcd1234.jsonl"
    body = _rollout(
        last_updated="2026-05-23T10:00:00.000Z",
        events=[
            _rollout_gemini(msg_id="g1"),
            {"$set": {"lastUpdated": "2026-05-23T15:30:00.000Z"}},
        ],
    )
    f.write_text(body)
    s = parse_session_file(f)
    assert s is not None
    # end reflects the later $set lastUpdated, not the header value (compared
    # via the same iso parser so the local-tz conversion matches)
    assert s.end == gh_mod._parse_iso("2026-05-23T15:30:00.000Z")
    assert s.end > s.start


def test_parse_jsonl_header_only(tmp_path: Path) -> None:
    f = tmp_path / "session-2026-05-23T10-00-abcd1234.jsonl"
    f.write_text(_rollout(events=[{"type": "info", "content": "notice"}]))
    s = parse_session_file(f)
    assert s is not None
    assert s.model_stats == []
    assert s.dominant_model == ""
    assert s.cost_usd == 0.0
    assert s.assistant_message_count == 0


def test_parse_jsonl_missing_session_id_returns_none(tmp_path: Path) -> None:
    f = tmp_path / "session-2026-05-23T10-00-abcd1234.jsonl"
    # No header line carrying sessionId — only events.
    f.write_text(json.dumps(_rollout_gemini()) + "\n")
    assert parse_session_file(f) is None


def test_parse_jsonl_skips_blank_and_malformed_lines(tmp_path: Path) -> None:
    f = tmp_path / "session-2026-05-23T10-00-abcd1234.jsonl"
    good = _rollout(events=[_rollout_gemini(inp=3000, out=30)])
    # interleave blank + malformed lines
    f.write_text(good.replace("\n", "\n\nnot json here\n", 1))
    s = parse_session_file(f)
    assert s is not None
    assert s.total_output == 30


def test_parse_jsonl_over_budget_returns_none(tmp_path: Path) -> None:
    f = tmp_path / "session-2026-05-23T10-00-abcd1234.jsonl"
    f.write_text(_rollout(events=[_rollout_gemini()]))
    # a tiny budget forces the streamed parse to bail out
    assert parse_session_file(f, max_bytes=10) is None


def test_parse_jsonl_skips_oversize_line(tmp_path: Path) -> None:
    f = tmp_path / "session-2026-05-23T10-00-abcd1234.jsonl"
    big = _rollout_gemini(msg_id="g_big", inp=999999, out=999)
    big["content"] = "x" * 2000  # inflate one line past the (patched) per-line cap
    small = _rollout_gemini(msg_id="g_ok", inp=1000, out=11)
    f.write_text(_rollout(events=[big, small]))
    with patch.object(gh_mod, "_MAX_ROLLOUT_LINE_BYTES", 500):
        s = parse_session_file(f)
    assert s is not None
    # only the small (in-cap) gemini event is counted
    assert s.assistant_message_count == 1
    assert s.total_output == 11


def test_json_jsonl_parity(tmp_path: Path) -> None:
    """The same events produce identical token/tool totals in both formats."""
    events = [
        _gemini_msg(model="gemini-2.5-flash", inp=10000, out=500, cached=2000, thoughts=100),
        _gemini_msg(model="gemini-2.5-pro", inp=50000, out=800, cached=10000),
    ]
    jf = tmp_path / "session-2026-05-23T10-00-abcd1234.json"
    jf.write_text(json.dumps(_make_session(messages=[{"type": "user", "content": "hi"}, *events])))
    rollout_events = [
        _rollout_user(),
        _rollout_gemini(
            msg_id="g1", model="gemini-2.5-flash", inp=10000, out=500, cached=2000, thoughts=100
        ),
        _rollout_gemini(msg_id="g2", model="gemini-2.5-pro", inp=50000, out=800, cached=10000),
    ]
    lf = tmp_path / "session-2026-05-23T10-00-abcd1234.jsonl"
    lf.write_text(_rollout(events=rollout_events))

    js = parse_session_file(jf)
    ls = parse_session_file(lf)
    assert js is not None and ls is not None
    assert js.total_input == ls.total_input
    assert js.total_output == ls.total_output
    assert js.total_cache == ls.total_cache
    assert js.dominant_model == ls.dominant_model
    assert abs(js.cost_usd - ls.cost_usd) < 1e-9
    assert js.user_message_count == ls.user_message_count
    assert js.assistant_message_count == ls.assistant_message_count


# ---------------------------------------------------------------------------
# discovery includes .jsonl (v3.8)
# ---------------------------------------------------------------------------


def test_find_all_session_files_includes_jsonl(tmp_path: Path) -> None:
    chats = tmp_path / "proj" / "chats"
    chats.mkdir(parents=True)
    (chats / "session-2026-05-07T10-00-aaaa1111.json").write_text(json.dumps(_make_session()))
    (chats / "session-2026-05-23T10-00-bbbb2222.jsonl").write_text(_rollout())
    with patch.object(gh_mod, "_GEMINI_TMP", tmp_path):
        found = {p.name for p in find_all_session_files()}
    assert "session-2026-05-07T10-00-aaaa1111.json" in found
    assert "session-2026-05-23T10-00-bbbb2222.jsonl" in found


def test_find_session_file_finds_jsonl(tmp_path: Path) -> None:
    session_id = "abcd1234-0000-0000-0000-000000000000"
    chats = tmp_path / "proj" / "chats"
    chats.mkdir(parents=True)
    f = chats / "session-2026-05-23T10-00-abcd1234.jsonl"
    f.write_text(_rollout(session_id=session_id))
    with patch.object(gh_mod, "_GEMINI_TMP", tmp_path):
        result = find_session_file(session_id)
    assert result == f


def test_find_session_file_jsonl_rejects_prefix_mismatch(tmp_path: Path) -> None:
    session_id = "abcd1234-0000-0000-0000-000000000000"
    chats = tmp_path / "proj" / "chats"
    chats.mkdir(parents=True)
    # same 8-char prefix in the filename, different full id in the header line
    f = chats / "session-2026-05-23T10-00-abcd1234.jsonl"
    f.write_text(_rollout(session_id="abcd1234-9999-0000-0000-000000000000"))
    with patch.object(gh_mod, "_GEMINI_TMP", tmp_path):
        result = find_session_file(session_id)
    assert result is None
