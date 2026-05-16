"""v2.60 — Claude Code collector enrichment."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from halyard.ai_log import AI_LOG_FILENAME, HEADER, parse_sessions
from halyard.collectors.claude_code import _CC_SESSION_FILE, handle_stop_hook

# Anchor on real now so the session (start..now) is a plausible
# duration (the >12h implausibility guard would otherwise drop it).
_NOW = datetime.now()
_START = _NOW - timedelta(minutes=10)
_E0 = _NOW - timedelta(minutes=9)
_E1 = _NOW - timedelta(minutes=1)  # 8 min after _E0


def _init(tmp: Path) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "halyard.toml").write_text("[business]\n")
    (tmp / AI_LOG_FILENAME).write_text(HEADER)
    return tmp


def _utc(local_naive: datetime) -> str:
    """Render a local-naive time as the UTC 'Z' string the collector
    expects (it inverts: fromisoformat → UTC → local → naive)."""
    aware_local = local_naive.astimezone()  # attach system local tz
    return aware_local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _transcript(tmp: Path, lines: list[dict]) -> Path:  # type: ignore[type-arg]
    p = tmp / "transcript.jsonl"
    p.write_text("\n".join(json.dumps(o) for o in lines) + "\n")
    return p


def _run(tmp: Path, payload: dict) -> int:  # type: ignore[type-arg]
    _CC_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CC_SESSION_FILE.write_text(json.dumps({"start": _START.isoformat()}))
    with (
        patch("halyard.collectors.claude_code.find_project_dir", return_value=tmp),
        patch("halyard.collectors.claude_code._transcript_roots", return_value=[tmp]),
        patch("sys.stdin", StringIO(json.dumps(payload))),
    ):
        return handle_stop_hook()


def _full_transcript(tmp: Path) -> Path:
    t0 = _utc(_E0)
    t1 = _utc(_E1)
    return _transcript(
        tmp,
        [
            {
                "type": "user",
                "timestamp": t0,
                "sessionId": "sess-abc",
                "message": {"content": "do the thing"},
            },
            {
                "type": "assistant",
                "timestamp": t0,
                "sessionId": "sess-abc",
                "message": {
                    "model": "claude-opus-4-7",
                    "usage": {"input_tokens": 4000, "output_tokens": 900},
                    "content": [{"type": "tool_use", "name": "Edit"}],
                },
            },
            {
                "type": "user",
                "timestamp": t1,
                "message": {"content": [{"type": "tool_result", "is_error": True}]},
            },
            {
                "type": "assistant",
                "timestamp": t1,
                "message": {
                    "model": "claude-opus-4-7",
                    "usage": {"input_tokens": 1000, "output_tokens": 200},
                    "content": [{"type": "tool_use", "name": "Bash"}],
                },
            },
        ],
    )


def test_full_transcript_enriches(tmp_path: Path) -> None:
    proj = _init(tmp_path / "p")
    tp = _full_transcript(proj)
    _run(proj, {"transcript_path": str(tp)})

    s = parse_sessions(proj)[0]
    assert s.session_id == "sess-abc"
    assert s.tool_calls == 2
    assert s.tool_errors == 1
    assert s.user_message_count == 1  # tool_result envelope not counted
    assert s.wall_seconds == 8 * 60
    assert s.input_tokens == 5000 and s.output_tokens == 1100


def test_payload_only_leaves_fields_none(tmp_path: Path) -> None:
    proj = _init(tmp_path / "p")
    _run(
        proj,
        {"model": "claude-sonnet-4-6", "usage": {"input_tokens": 800, "output_tokens": 100}},
    )
    s = parse_sessions(proj)[0]
    # Unavailable is not zero — no transcript ⇒ None, not 0/"".
    assert s.tool_calls is None
    assert s.tool_errors is None
    assert s.user_message_count is None
    assert s.wall_seconds is None
    assert s.session_id is None
    assert s.input_tokens == 800  # existing behaviour intact


def test_multi_model_sets_breakdown(tmp_path: Path) -> None:
    proj = _init(tmp_path / "p")
    t0 = _utc(_E0)
    tp = _transcript(
        proj,
        [
            {
                "type": "assistant",
                "timestamp": t0,
                "message": {
                    "model": "claude-opus-4-7",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                    "content": [],
                },
            },
            {
                "type": "assistant",
                "timestamp": t0,
                "message": {
                    "model": "claude-haiku-4-5",
                    "usage": {"input_tokens": 4, "output_tokens": 2},
                    "content": [],
                },
            },
        ],
    )
    _run(proj, {"transcript_path": str(tp)})
    s = parse_sessions(proj)[0]
    # v2.61 usage form: model:in/out/cr/cw, sorted by model name
    assert s.model_breakdown == "claude-haiku-4-5:4/2/0/0|claude-opus-4-7:10/5/0/0"


def test_single_model_no_breakdown(tmp_path: Path) -> None:
    proj = _init(tmp_path / "p")
    tp = _full_transcript(proj)
    _run(proj, {"transcript_path": str(tp)})
    s = parse_sessions(proj)[0]
    assert s.model_breakdown is None  # one model → no breakdown


def test_log_round_trips(tmp_path: Path) -> None:
    proj = _init(tmp_path / "p")
    tp = _full_transcript(proj)
    _run(proj, {"transcript_path": str(tp)})
    before = (proj / AI_LOG_FILENAME).read_text()
    again = parse_sessions(proj)
    assert (proj / AI_LOG_FILENAME).read_text() == before
    assert again[0].session_id == "sess-abc"
    assert again[0].tool_calls == 2


def test_drift_canary_unaffected_by_new_fields(tmp_path: Path) -> None:
    # A real model still reads as real; enrichment doesn't perturb the
    # v2.59 drift predicate.
    from halyard.collectors import session_is_synthetic_telemetry

    proj = _init(tmp_path / "p")
    tp = _full_transcript(proj)
    _run(proj, {"transcript_path": str(tp)})
    s = parse_sessions(proj)[0]
    assert s.model == "claude-opus-4-7"
    assert session_is_synthetic_telemetry(s) is False


@pytest.fixture(autouse=True)
def _clean_session_file() -> None:
    yield
    _CC_SESSION_FILE.unlink(missing_ok=True)
