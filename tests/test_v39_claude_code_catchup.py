"""v3.9 — Claude Code Stop-hook catch-up high-water mark.

Regression for the silent under-capture: when the Stop hook is missed for a
stretch (common in the desktop app), the old design read the transcript only
since *this* turn's start and dropped every turn in the gap. The fix anchors
the read to the latest end already recorded for the session, so one Stop after
a gap back-fills everything since the last row.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session, parse_sessions
from halyard.collectors.claude_code import _CC_SESSION_FILE, handle_stop_hook

_NOW = datetime.now()
_PREV_END = _NOW - timedelta(minutes=8)  # last recorded row's end (high-water mark)
_GAP_EVENT = _NOW - timedelta(minutes=5)  # a turn that happened in the gap (Stop missed)
_TURN_START = _NOW - timedelta(minutes=2)  # this turn's cc-session start (misses the gap)
_TURN_EVENT = _NOW - timedelta(minutes=1)
_SID = "sess-catchup-0001"


def _utc(local_naive: datetime) -> str:
    return local_naive.astimezone().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _init(tmp: Path) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "halyard.toml").write_text("[business]\n")
    (tmp / AI_LOG_FILENAME).write_text(HEADER)
    return tmp


def _seed_prior_row(tmp: Path) -> None:
    append_session(
        tmp,
        AiSession(
            start=_NOW - timedelta(minutes=9),
            end=_PREV_END,
            tool="claude-code",
            model="claude-opus-4-7",
            input_tokens=400,
            output_tokens=100,
            cost_usd=0.0,
            session_id=_SID,
            source="hook",
        ),
    )


def _transcript(tmp: Path) -> Path:
    p = tmp / "transcript.jsonl"
    p.write_text(
        "\n".join(
            json.dumps(o)
            for o in [
                {  # turn that happened in the gap — Stop was missed for it
                    "type": "assistant",
                    "timestamp": _utc(_GAP_EVENT),
                    "sessionId": _SID,
                    "message": {
                        "model": "claude-opus-4-7",
                        "usage": {"input_tokens": 2000, "output_tokens": 50},
                        "content": [{"type": "tool_use", "name": "Edit"}],
                    },
                },
                {  # this turn
                    "type": "assistant",
                    "timestamp": _utc(_TURN_EVENT),
                    "sessionId": _SID,
                    "message": {
                        "model": "claude-opus-4-7",
                        "usage": {"input_tokens": 1000, "output_tokens": 70},
                        "content": [{"type": "tool_use", "name": "Bash"}],
                    },
                },
            ]
        )
        + "\n"
    )
    return p


def _run(tmp: Path) -> None:
    _CC_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CC_SESSION_FILE.write_text(json.dumps({"start": _TURN_START.isoformat()}))
    payload = {"session_id": _SID, "transcript_path": str(_transcript(tmp))}
    with (
        patch("halyard.collectors.claude_code.find_project_dir", return_value=tmp),
        patch("halyard.collectors.claude_code._transcript_roots", return_value=[tmp]),
        patch("sys.stdin", StringIO(json.dumps(payload))),
    ):
        handle_stop_hook()


def test_stop_hook_catches_up_missed_turns(tmp_path: Path) -> None:
    tmp = _init(tmp_path / "proj")
    _seed_prior_row(tmp)

    _run(tmp)

    rows = sorted([s for s in parse_sessions(tmp) if s.session_id == _SID], key=lambda s: s.start)
    assert len(rows) == 2  # the seeded row + the new catch-up row
    new = rows[-1]
    # Catch-up captured BOTH the gap turn (50) and this turn (70), not just 70.
    assert new.output_tokens == 120
    assert new.tool_calls == 2
    # The new row's window starts at the high-water mark, not this turn's start.
    assert abs((new.start - _PREV_END).total_seconds()) < 2


def test_first_turn_without_prior_row_uses_session_start(tmp_path: Path) -> None:
    """No prior row → no watermark → behaves as before (since = turn start)."""
    tmp = _init(tmp_path / "proj")
    _run(tmp)
    rows = [s for s in parse_sessions(tmp) if s.session_id == _SID]
    assert len(rows) == 1
    # Only the in-window event (after _TURN_START) is captured: output 70, not 120.
    assert rows[0].output_tokens == 70
