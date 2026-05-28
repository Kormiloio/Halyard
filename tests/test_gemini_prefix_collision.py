"""Gap 7: Gemini session-id 8-char prefix collision.

find_session_file() uses the first 8 chars of a session_id as a glob prefix.
If two sessions share the same 8-char prefix, the glob can return files from
both sessions, causing cross-contamination in attribution.

This test verifies that two sessions with identical 8-char prefixes but
distinct full IDs are attributed to their respective projects independently,
with no cross-contamination of token counts or project slugs.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from halyard.ai_log import AI_LOG_FILENAME, parse_sessions

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Two session IDs that share the same 8-char prefix ("aabbccdd")
_SESSION_A = "aabbccdd-1111-2222-3333-000000000001"
_SESSION_B = "aabbccdd-9999-8888-7777-000000000002"

# Shared 8-char prefix
_PREFIX = "aabbccdd"


def _halyard_project(path: Path, slug: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "halyard.toml").write_text(f"[project]\nslug = '{slug}'\n", encoding="utf-8")
    (path / AI_LOG_FILENAME).write_text(
        "; Halyard AI session log\n"
        "; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd>\n",
        encoding="utf-8",
    )
    return path


def _make_session_file(
    gemini_tmp: Path, slug: str, session_id: str, *, input_tok: int, output_tok: int
) -> Path:
    """Write a minimal Gemini history JSON under the expected path structure."""
    chats_dir = gemini_tmp / slug / "chats"
    chats_dir.mkdir(parents=True, exist_ok=True)
    prefix = session_id[:8]
    path = chats_dir / f"session-2026-05-08T10-00-00-{prefix}.json"
    data = {
        "sessionId": session_id,
        "startTime": "2026-05-08T10:00:00Z",
        "lastUpdated": "2026-05-08T10:30:00Z",
        "messages": [
            {
                "type": "gemini",
                "model": "gemini-2.0-pro",
                "tokens": {
                    "input": input_tok,
                    "output": output_tok,
                    "cached": 0,
                },
                "toolCalls": [],
            }
        ],
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _hook_state(project_dir: Path, session_id: str) -> str:
    return json.dumps(
        {
            "turn_start": (datetime.now() - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S"),
            "cwd": str(project_dir),
            "model": "gemini-2.0-pro",
            "session_id": session_id,
            "prompt_tokens": 0,
            "output_tokens": 0,
            "cache_tokens": 0,
        }
    )


def _after_agent_payload(cwd: str) -> str:
    return json.dumps(
        {
            "hook_event_name": "AfterAgent",
            "cwd": cwd,
            "prompt": "Hello",
            "stop_hook_active": False,
        }
    )


# ---------------------------------------------------------------------------
# Gap 7: prefix collision — sessions attributed independently
# ---------------------------------------------------------------------------


def test_prefix_collision_sessions_attributed_independently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two Gemini sessions sharing an 8-char prefix are attributed independently.

    Each handle_agent_stop() call must record the token counts for its own
    session_id only — no cross-contamination from the other session's history file.
    """
    gemini_tmp = tmp_path / ".gemini" / "tmp"

    # Project A: session A → 500 input, 100 output
    proj_a = _halyard_project(tmp_path / "proj_a", "acme:proj-a")
    _make_session_file(gemini_tmp, "slug-a", _SESSION_A, input_tok=500, output_tok=100)

    # Project B: session B → 800 input, 200 output
    proj_b = _halyard_project(tmp_path / "proj_b", "acme:proj-b")
    _make_session_file(gemini_tmp, "slug-b", _SESSION_B, input_tok=800, output_tok=200)

    state_file = tmp_path / "gc-session"
    monkeypatch.setattr("halyard.collectors.gemini_cli._GC_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.gemini_cli.read_active_project", lambda: None)

    # Redirect _GEMINI_TMP so find_session_file looks in our tmp tree
    monkeypatch.setattr(
        "halyard.collectors.gemini_history._GEMINI_TMP",
        gemini_tmp,
    )

    from halyard.collectors.gemini_cli import handle_agent_stop

    # --- Session A ---
    state_file.write_text(_hook_state(proj_a, _SESSION_A), encoding="utf-8")
    with patch(
        "halyard.collectors.gemini_cli.sys.stdin.read",
        return_value=_after_agent_payload(str(proj_a)),
    ):
        handle_agent_stop()

    sessions_a = parse_sessions(proj_a)
    assert len(sessions_a) == 1, "Session A must produce exactly one record"
    s_a = sessions_a[0]

    # --- Session B ---
    state_file.write_text(_hook_state(proj_b, _SESSION_B), encoding="utf-8")
    with patch(
        "halyard.collectors.gemini_cli.sys.stdin.read",
        return_value=_after_agent_payload(str(proj_b)),
    ):
        handle_agent_stop()

    sessions_b = parse_sessions(proj_b)
    assert len(sessions_b) == 1, "Session B must produce exactly one record"
    s_b = sessions_b[0]

    # Each session must carry its own token counts — no cross-contamination
    assert s_a.input_tokens == 500, (
        f"Session A input should be 500, got {s_a.input_tokens} — prefix collision?"
    )
    assert s_a.output_tokens == 100, f"Session A output should be 100, got {s_a.output_tokens}"
    assert s_b.input_tokens == 800, (
        f"Session B input should be 800, got {s_b.input_tokens} — prefix collision?"
    )
    assert s_b.output_tokens == 200, f"Session B output should be 200, got {s_b.output_tokens}"

    # Verify session IDs are stored independently
    assert s_a.session_id == _SESSION_A
    assert s_b.session_id == _SESSION_B
