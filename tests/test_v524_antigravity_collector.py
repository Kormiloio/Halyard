"""v5.24 — Antigravity collector.

Antigravity reports no tokens, model, or cost anywhere, so its rows carry
time only and are quarantined from spend. These tests pin that quarantine,
the UTC→local conversion its transcripts require, the growth re-import
behaviour (the v5.2 / v5.21 / v5.22 defect class), the privacy boundary,
and the path-ownership split with the Gemini collectors that share
``~/.gemini/``.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard.ai_log import AiSession, collapse_gemini_sessions, parse_sessions
from halyard.collectors.antigravity import (
    discover_transcripts,
    handle_stop_hook,
    import_antigravity_sessions,
    parse_transcript,
)
from halyard.usage import sum_spend

_CID = "5d3deaf3-ce30-489e-abde-19fb795770a6"
_SECRET = "SUPER-SECRET-PROMPT-TEXT-DO-NOT-CAPTURE"


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import halyard.collectors.antigravity as mod

    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    # The importer resolves its target ledger from Path.cwd() when no
    # workspace is known, walking *up* the tree. Without this chdir the
    # cwd stays inside the repo, find_project_dir climbs to a real Halyard
    # project on the developer's machine, and the tests append synthetic
    # rows to a real ai-sessions.log. Patching Path.home() alone does not
    # prevent it.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(mod, "_ANTIGRAVITY_DIR", home / ".gemini" / "antigravity")
    monkeypatch.setattr(mod, "_BRAIN_DIR", home / ".gemini" / "antigravity" / "brain")
    monkeypatch.setattr(mod, "_IMPORTED_STATE_FILE", home / ".halyard" / "antigravity-imported")
    monkeypatch.setattr(mod, "_WORKSPACE_STATE_DIR", home / ".halyard" / "ag-sessions")


def _project(tmp_path: Path) -> Path:
    p = tmp_path / "project"
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[project]\nslug = 'test'\n", encoding="utf-8")
    (p / "ai-sessions.log").write_text("; Halyard AI session log\n", encoding="utf-8")
    return p


def _write_transcript(
    tmp_path: Path,
    *,
    conversation_id: str = _CID,
    turns: int = 3,
    start: str = "2026-08-09T18:58:04Z",
) -> Path:
    """A transcript in the observed Antigravity shape (UTC ``Z`` stamps)."""
    base = datetime.fromisoformat(start.replace("Z", "+00:00"))
    records: list[dict[str, object]] = []
    for i in range(turns):
        stamp = (base + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        records.append(
            {
                "step_index": len(records),
                "type": "USER_INPUT",
                "source": "USER_EXPLICIT",
                "status": "DONE",
                "created_at": stamp,
                "content": _SECRET,
            }
        )
        records.append(
            {
                "step_index": len(records),
                "type": "PLANNER_RESPONSE",
                "source": "MODEL",
                "status": "DONE",
                "created_at": stamp,
                "content": _SECRET,
                "thinking": _SECRET,
            }
        )
        records.append(
            {
                "step_index": len(records),
                "type": "RUN_COMMAND",
                "source": "MODEL",
                "status": "DONE",
                "created_at": stamp,
                "exit_code": 0,
            }
        )

    home = tmp_path / "home"
    conv = home / ".gemini" / "antigravity" / "brain" / conversation_id
    logs = conv / ".system_generated" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


# --- parsing ---------------------------------------------------------------


def test_parse_transcript_reports_time_but_no_spend(tmp_path: Path) -> None:
    session = parse_transcript(_write_transcript(tmp_path, turns=3))
    assert session is not None

    # The headline contract: time yes, spend no.
    assert session.tool == "antigravity"
    assert session.input_tokens == 0
    assert session.output_tokens == 0
    assert session.cost_usd == 0.0
    assert session.tokens_available is False
    assert session.billing == "credits"
    assert session.telemetry_trust == "inferred"
    assert session.telemetry_source == "antigravity-transcript"

    assert session.user_message_count == 3
    assert session.assistant_message_count == 6  # source=MODEL rows
    assert session.tool_calls == 3
    assert session.interaction_count == 9
    assert session.wall_seconds == 120


def test_created_at_is_converted_from_utc(tmp_path: Path) -> None:
    """Transcript stamps are UTC ``Z``; the ledger writes local time.

    Without conversion every Antigravity session is offset by the local UTC
    offset — the bug this pins. Platform-independent: the expectation is
    derived from whatever zone the runner is in, so it holds on a UTC CI
    box and on a developer machine alike.
    """
    session = parse_transcript(_write_transcript(tmp_path, turns=1, start="2026-08-09T18:58:04Z"))
    assert session is not None

    expected = datetime.fromisoformat("2026-08-09T18:58:04+00:00").astimezone().replace(tzinfo=None)
    assert session.start == expected
    assert session.start.tzinfo is None, "the ledger stores naive local datetimes"


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="time.tzset is POSIX-only")
def test_created_at_conversion_against_a_fixed_zone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same conversion pinned to a concrete offset, where the OS allows it.

    Complements the platform-independent test above, which cannot catch a
    no-op conversion when the runner is already on UTC.
    """
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    try:
        session = parse_transcript(
            _write_transcript(tmp_path, turns=1, start="2026-08-09T18:58:04Z")
        )
        assert session is not None
        # 18:58:04Z is 14:58:04 in New York (EDT, UTC-4).
        assert session.start == datetime(2026, 8, 9, 14, 58, 4)
    finally:
        # monkeypatch restores TZ, but the C-level zone must be reloaded too
        # or every later test in this process inherits New York.
        monkeypatch.undo()
        time.tzset()


def test_prompt_content_is_never_captured(tmp_path: Path) -> None:
    """Non-negotiable 5: metadata only, never content or thinking."""
    session = parse_transcript(_write_transcript(tmp_path, turns=2))
    assert session is not None

    for value in vars(session).values():
        assert _SECRET not in str(value), f"prompt content leaked into {value!r}"


def test_malformed_lines_are_skipped_not_fatal(tmp_path: Path) -> None:
    path = _write_transcript(tmp_path, turns=2)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
        handle.write("[]\n")  # valid JSON, wrong shape
        handle.write("\n")

    session = parse_transcript(path)
    assert session is not None
    assert session.user_message_count == 2


def test_transcript_without_timestamps_yields_nothing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    logs = home / ".gemini" / "antigravity" / "brain" / _CID / ".system_generated" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / "transcript.jsonl"
    path.write_text(json.dumps({"type": "GENERIC", "source": "SYSTEM"}) + "\n", encoding="utf-8")

    assert parse_transcript(path) is None


# --- spend quarantine ------------------------------------------------------


def _antigravity_row(**over: object) -> AiSession:
    base: dict[str, object] = {
        "start": datetime(2026, 8, 9, 14, 0),
        "end": datetime(2026, 8, 9, 15, 0),
        "tool": "antigravity",
        "model": "antigravity-auto",
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "tokens_available": False,
        "billing": "credits",
        "telemetry_trust": "inferred",
        "job_id": f"antigravity:{_CID}",
    }
    base.update(over)
    return AiSession(**base)  # type: ignore[arg-type]


def _paid_row(**over: object) -> AiSession:
    base: dict[str, object] = {
        "start": datetime(2026, 8, 9, 14, 0),
        "end": datetime(2026, 8, 9, 15, 0),
        "tool": "claude-code",
        "model": "claude-opus-5",
        "input_tokens": 100,
        "output_tokens": 200,
        "cost_usd": 12.34,
    }
    base.update(over)
    return AiSession(**base)  # type: ignore[arg-type]


def test_antigravity_is_excluded_from_spend() -> None:
    paid = _paid_row()
    assert sum_spend([_antigravity_row(), paid]) == sum_spend([paid]) == 12.34


def test_spend_bearing_tool_does_not_inherit_the_quarantine() -> None:
    """The quarantine must key on the row's own billing, not on tool mixing."""
    assert sum_spend([_antigravity_row(), _paid_row(), _paid_row()]) == 24.68


def test_quarantine_is_spend_only_never_time() -> None:
    """Time must still reach invoices; only spend is withheld."""
    row = parse_transcript(_write_transcript(_tmp(), turns=4))
    assert row is not None
    assert row.wall_seconds is not None and row.wall_seconds > 0
    assert (row.end - row.start).total_seconds() > 0


def _tmp() -> Path:
    import tempfile

    return Path(tempfile.mkdtemp())


def test_report_bucket_marks_antigravity_not_spend_tracked() -> None:
    from halyard.reports import _tool_buckets_for_report

    buckets = {b.tool: b for b in _tool_buckets_for_report([_antigravity_row(), _paid_row()])}
    assert buckets["antigravity"].spend_tracked is False
    assert buckets["claude-code"].spend_tracked is True


# --- growth / idempotence --------------------------------------------------


def test_import_is_idempotent(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_transcript(tmp_path, turns=2)

    first = import_antigravity_sessions(project_dir=None, all_projects=True)
    second = import_antigravity_sessions(project_dir=None, all_projects=True)

    assert len(first) == 1
    assert second == []
    del project


def test_grown_conversation_reimports_and_collapses(tmp_path: Path) -> None:
    """A resumed conversation must supersede its earlier row, not duplicate it."""
    _project(tmp_path)
    _write_transcript(tmp_path, turns=2)
    first = import_antigravity_sessions(project_dir=None, all_projects=True)
    assert len(first) == 1

    _write_transcript(tmp_path, turns=5)  # same conversation id, grown
    second = import_antigravity_sessions(project_dir=None, all_projects=True)
    assert len(second) == 1, "a grown transcript must re-import"

    collapsed = collapse_gemini_sessions(first + second)
    assert len(collapsed) == 1, "both rows describe one conversation"
    assert collapsed[0].end == second[0].end, "the widest/most complete row wins"


def test_distinct_conversations_do_not_collapse(tmp_path: Path) -> None:
    _project(tmp_path)
    _write_transcript(tmp_path, conversation_id=_CID, turns=2)
    _write_transcript(tmp_path, conversation_id="11111111-2222-3333-4444-555555555555", turns=2)

    rows = import_antigravity_sessions(project_dir=None, all_projects=True)
    assert len(rows) == 2
    assert len(collapse_gemini_sessions(rows)) == 2


def test_ledger_duplicate_canary_stays_quiet(tmp_path: Path) -> None:
    """v5.23's canary must not fire on a legitimate mixed-tool ledger."""
    from halyard.doctor import _ledger_duplicate_checks

    project = _project(tmp_path)
    _write_transcript(tmp_path, turns=2)
    import_antigravity_sessions(project_dir=project, all_projects=False)

    checks = _ledger_duplicate_checks(project, None)
    assert [c for c in checks if c.status != "ok"] == []


# --- hook path -------------------------------------------------------------


def test_hook_prefers_payload_transcript_path(tmp_path: Path) -> None:
    """The documented transcript path and the real one disagree.

    The collector must trust ``transcriptPath`` from the payload rather than
    a hardcoded layout.
    """
    project = _project(tmp_path)
    odd = tmp_path / "elsewhere" / "transcript.jsonl"
    odd.parent.mkdir(parents=True, exist_ok=True)
    odd.write_bytes(_write_transcript(tmp_path, turns=2).read_bytes())

    rc = handle_stop_hook(
        {
            "conversationId": _CID,
            "workspacePaths": [str(project)],
            "transcriptPath": str(odd),
            "modelName": "auto",
        }
    )
    assert rc == 0

    rows = parse_sessions(project)
    ag = [r for r in rows if r.tool == "antigravity"]
    assert len(ag) == 1
    assert ag[0].model == "antigravity-auto"
    assert ag[0].billing == "credits"
    assert ag[0].tokens_available is False


def test_hook_rejects_traversal_in_conversation_id(tmp_path: Path) -> None:
    """conversation_id is untrusted hook stdin (v5.16/B07)."""
    project = _project(tmp_path)
    _write_transcript(tmp_path, turns=2)

    for bad in ("../../etc/passwd", "..", "a/b", ""):
        assert handle_stop_hook({"conversationId": bad, "workspacePaths": [str(project)]}) == 0

    escaped = tmp_path / "home" / ".halyard" / "ag-sessions"
    assert not escaped.exists() or list(escaped.iterdir()) == []


def test_hook_without_transcript_writes_nothing(tmp_path: Path) -> None:
    project = _project(tmp_path)
    assert handle_stop_hook({"conversationId": _CID, "workspacePaths": [str(project)]}) == 0
    assert [r for r in parse_sessions(project) if r.tool == "antigravity"] == []


# --- path ownership vs the Gemini collectors -------------------------------


def test_antigravity_transcripts_are_invisible_to_gemini(tmp_path: Path) -> None:
    """Both live under ~/.gemini/; neither may claim the other's files."""
    import halyard.collectors.gemini_history as gem

    home = tmp_path / "home"
    _write_transcript(tmp_path, turns=3)

    # Gemini's roots are siblings of antigravity/ and must stay empty.
    assert not (home / ".gemini" / "tmp").exists()
    assert not (home / ".gemini" / "history").exists()
    assert gem._is_foreign(home / ".gemini" / "antigravity" / "brain" / _CID / "x.jsonl")
    assert discover_transcripts()  # antigravity still sees its own


def test_gemini_history_is_invisible_to_antigravity(tmp_path: Path) -> None:
    home = tmp_path / "home"
    chats = home / ".gemini" / "tmp" / "someslug" / "chats"
    chats.mkdir(parents=True, exist_ok=True)
    (chats / "session-1.json").write_text(json.dumps({"messages": []}), encoding="utf-8")

    assert discover_transcripts() == {}
    assert import_antigravity_sessions(project_dir=None, all_projects=True) == []


# --- doctor ----------------------------------------------------------------


def test_doctor_skips_when_antigravity_absent(tmp_path: Path) -> None:
    from halyard.doctor import _antigravity_hook_check

    assert _antigravity_hook_check(required=False) is None


def test_doctor_warns_when_present_but_unhooked(tmp_path: Path) -> None:
    from halyard.doctor import _antigravity_hook_check

    _write_transcript(tmp_path, turns=1)  # creates ~/.gemini/antigravity/

    check = _antigravity_hook_check(required=False)
    assert check is not None
    assert check.status == "warning"
    # The fix must name a command that actually exists.
    assert check.fix == "halyard install-hook-antigravity"


def test_doctor_ok_when_hooked_and_says_spend_is_untracked(tmp_path: Path) -> None:
    from halyard.doctor import _antigravity_hook_check

    _write_transcript(tmp_path, turns=1)
    hooks = tmp_path / "home" / ".gemini" / "config"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "hooks.json").write_text(
        json.dumps(
            {"halyard": {"Stop": [{"type": "command", "command": "/usr/bin/halyard ag-hook"}]}}
        ),
        encoding="utf-8",
    )

    check = _antigravity_hook_check(required=False)
    assert check is not None
    assert check.status == "ok"
    assert "not spend-tracked" in check.detail


def test_doctor_finds_hooks_nested_under_a_matcher(tmp_path: Path) -> None:
    """Antigravity wraps tool-event handlers in a matcher; both shapes count."""
    from halyard.doctor import _antigravity_hook_check

    _write_transcript(tmp_path, turns=1)
    hooks = tmp_path / "home" / ".gemini" / "config"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "hooks.json").write_text(
        json.dumps(
            {
                "someone-else": {"Stop": [{"type": "command", "command": "./other.sh"}]},
                "halyard": {
                    "PostToolUse": [
                        {
                            "matcher": "run_command",
                            "hooks": [{"type": "command", "command": "/usr/bin/halyard ag-hook"}],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    check = _antigravity_hook_check(required=False)
    assert check is not None
    assert check.status == "ok"


# --- performance -----------------------------------------------------------


def test_large_transcript_parses_quickly(tmp_path: Path, perf_ceiling) -> None:  # type: ignore[no-untyped-def]
    """Hooks block Antigravity's agent loop, so parsing must stay cheap."""
    path = _write_transcript(tmp_path, turns=2000)

    started = time.perf_counter()
    session = parse_transcript(path)
    elapsed = time.perf_counter() - started

    assert session is not None
    assert elapsed < perf_ceiling(1.0)
