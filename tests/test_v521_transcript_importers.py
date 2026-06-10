"""v5.21 — transcript importer hardening.

Regression tests for the 2026-06-10 incident: an unsupervised agent session
shipped a Claude Code transcript importer that decoded project paths from
storage folder names (lossy — 1,841 sessions misattributed to the home
directory), bumped the global plausibility guard 12h → 7 days, deduped only
against its own state file (double-counting hook-recorded sessions), and a
Copilot parser change that fabricated phantom user turns.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard.ai_log import AiSession, collapse_gemini_sessions, parse_sessions
from halyard.collectors import _MAX_SESSION_SECONDS, session_is_implausible
from halyard.collectors.claude_code import import_claude_sessions
from halyard.collectors.copilot import parse_chat_session

_SID = "11111111-2222-3333-4444-555555555555"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the importer at tmp paths. (Hub isolation is handled in conftest.)"""
    import halyard.collectors.claude_code as mod

    monkeypatch.setattr(mod, "_CLAUDE_PROJECTS_DIR", tmp_path / "claude-projects")
    monkeypatch.setattr(mod, "_IMPORTED_STATE_FILE", tmp_path / "claude-imported")


def _project(tmp_path: Path, name: str = "project") -> Path:
    p = tmp_path / name
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[project]\nslug = 'test'\n", encoding="utf-8")
    (p / "ai-sessions.log").write_text(
        "; Halyard AI session log\n"
        "; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd> [key=value ...]\n",
        encoding="utf-8",
    )
    return p


def _transcript_events(
    *,
    cwd: str,
    session_id: str = _SID,
    turns: int = 2,
    start: str = "2026-06-01T14:00:00.000Z",
    end: str = "2026-06-01T14:20:00.000Z",
) -> list[dict]:  # type: ignore[type-arg]
    evs: list[dict] = []  # type: ignore[type-arg]
    for i in range(turns):
        ts = start if i < turns - 1 else end
        evs.append(
            {
                "type": "user",
                "timestamp": ts,
                "cwd": cwd,
                "sessionId": session_id,
                "message": {"content": [{"type": "text", "text": "hi"}]},
            }
        )
        evs.append(
            {
                "type": "assistant",
                "timestamp": ts,
                "cwd": cwd,
                "sessionId": session_id,
                "message": {
                    "model": "claude-fable-5",
                    "usage": {"input_tokens": 10, "output_tokens": 200},
                    "content": [],
                },
            }
        )
    return evs


def _write_transcript(
    tmp_path: Path,
    events: list[dict],  # type: ignore[type-arg]
    *,
    folder: str = "-Users-someone-code-project",
    session_id: str = _SID,
) -> Path:
    d = tmp_path / "claude-projects" / folder
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{session_id}.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    return path


def _claude_lines(project: Path) -> list[str]:
    return [
        ln
        for ln in (project / "ai-sessions.log").read_text(encoding="utf-8").splitlines()
        if ln.startswith("s ") and " claude-code " in ln
    ]


# ---------------------------------------------------------------------------
# Attribution comes from the transcript cwd, never the folder name
# ---------------------------------------------------------------------------


def test_attribution_from_cwd_not_folder_name(tmp_path: Path) -> None:
    """A hyphen-ambiguous storage folder must not steer attribution.

    The folder name decodes (wrongly) to a path that is itself a Halyard
    project — the exact shape of the home-directory incident. The row must
    land in the project named by the transcript's cwd instead.
    """
    decoy = _project(tmp_path, "decoy")  # what a name-decoder would pick
    real = _project(tmp_path, "real-project")  # hyphen in the dir name

    # Folder name encodes the real project's path: '-' and '/' collapse.
    folder = str(real).replace("/", "-")
    _write_transcript(tmp_path, _transcript_events(cwd=str(real)), folder=folder)

    imported = import_claude_sessions(all_projects=True)

    assert len(imported) == 1
    assert _claude_lines(real), "row must land in the cwd-named project"
    assert not _claude_lines(decoy)


def test_transcript_without_cwd_is_skipped(tmp_path: Path) -> None:
    decoy = _project(tmp_path, "decoy")
    events = _transcript_events(cwd="ignored")
    for e in events:
        del e["cwd"]
    # Folder name decodes (wrongly, by replacement) to the decoy project.
    _write_transcript(tmp_path, events, folder=str(decoy).replace("/", "-"))

    # No cwd → no resolvable project → skipped. Never decoded from the
    # folder name, and deliberately no hub fallback (tracked projects only:
    # the real corpus is dominated by headless/observer transcripts that
    # would swamp the hub ledger with unattributed rows).
    imported = import_claude_sessions(all_projects=True)
    assert imported == []
    assert not _claude_lines(decoy)


def test_sweep_requires_positive_attribution(tmp_path: Path) -> None:
    """A catch-all project root (the initialised-home-directory shape) must
    not absorb slug-less transcripts during a sweep."""
    catchall = tmp_path / "catchall"
    catchall.mkdir()
    (catchall / "halyard.toml").write_text("", encoding="utf-8")  # no slug
    (catchall / "ai-sessions.log").write_text("; log\n", encoding="utf-8")

    sub = catchall / "random" / "dir"
    sub.mkdir(parents=True)
    _write_transcript(tmp_path, _transcript_events(cwd=str(sub)))

    assert import_claude_sessions(all_projects=True) == []
    assert not _claude_lines(catchall)

    # An explicit, user-directed run is exempt from the slug requirement.
    explicit = import_claude_sessions(project_dir=catchall)
    assert len(explicit) == 1


# ---------------------------------------------------------------------------
# Hook-covered sessions are the hook's
# ---------------------------------------------------------------------------


def test_hook_recorded_session_is_skipped(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_transcript(tmp_path, _transcript_events(cwd=str(project)))

    # The Stop hook already recorded a per-turn row for this session.
    hook_row = (
        f"s 2026-06-01T10:00:00 2026-06-01T10:05:00 claude-code claude-fable-5 "
        f"10 200 0.0100 source=hook session_id={_SID}\n"
    )
    with (project / "ai-sessions.log").open("a", encoding="utf-8") as f:
        f.write(hook_row)

    imported = import_claude_sessions(project_dir=project)

    assert imported == [], "whole-transcript import on top of hook rows double-counts"
    assert len(_claude_lines(project)) == 1  # only the hook row


def test_legacy_hook_row_without_session_id_blocks_reimport(tmp_path: Path) -> None:
    """Pre-token-era hook rows carry neither session_id nor source. A
    transcript overlapping their time window must still be skipped —
    double-counting a hooked session is worse than missing a parallel one."""
    project = _project(tmp_path)
    _write_transcript(tmp_path, _transcript_events(cwd=str(project)))

    # A legacy row overlapping the transcript's local-time window (the
    # transcript's 14:00Z-14:20Z events convert to local naive on read).
    from halyard.collectors.claude_code import _read_from_transcript

    stats = _read_from_transcript(
        str(tmp_path / "claude-projects" / "-Users-someone-code-project" / f"{_SID}.jsonl")
    )
    assert stats.start_dt is not None and stats.end_dt is not None
    mid = stats.start_dt + (stats.end_dt - stats.start_dt) / 2
    legacy_row = (
        f"s {stats.start_dt:%Y-%m-%dT%H:%M:%S} {mid:%Y-%m-%dT%H:%M:%S} "
        "claude-code claude-sonnet-4-6 10 200 0.0100\n"
    )
    with (project / "ai-sessions.log").open("a", encoding="utf-8") as f:
        f.write(legacy_row)

    assert import_claude_sessions(project_dir=project) == []
    assert len(_claude_lines(project)) == 1  # only the legacy row


def test_unhooked_session_is_imported_once(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_transcript(tmp_path, _transcript_events(cwd=str(project)))

    first = import_claude_sessions(project_dir=project)
    assert len(first) == 1
    assert first[0].source == "import"
    assert first[0].job_id == f"claude:{_SID}"
    assert first[0].session_id == _SID

    # Unchanged transcript: second run is a no-op (id→size state).
    assert import_claude_sessions(project_dir=project) == []
    assert len(_claude_lines(project)) == 1


# ---------------------------------------------------------------------------
# Growth re-import + read-time collapse (codex pattern)
# ---------------------------------------------------------------------------


def test_grown_transcript_reimports_and_collapses(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_transcript(tmp_path, _transcript_events(cwd=str(project), turns=1))
    assert len(import_claude_sessions(project_dir=project)) == 1

    # The live session keeps going; its transcript grows.
    _write_transcript(
        tmp_path,
        _transcript_events(cwd=str(project), turns=5, end="2026-06-01T15:30:00.000Z"),
    )
    second = import_claude_sessions(project_dir=project)
    assert len(second) == 1, "grown transcript must re-import"

    # Two raw rows, one canonical session at read time.
    assert len(_claude_lines(project)) == 2
    collapsed = [s for s in parse_sessions(project) if s.tool == "claude-code"]
    assert len(collapsed) == 1
    assert collapsed[0].output_tokens == 1000  # the fuller re-import wins


def test_collapse_never_touches_hook_rows() -> None:
    """Hook rows are per-turn deltas — collapsing them destroys real turns."""

    def _turn(start_min: int, out: int) -> AiSession:
        return AiSession(
            start=datetime(2026, 6, 1, 10, start_min),
            end=datetime(2026, 6, 1, 10, start_min + 4),
            tool="claude-code",
            model="claude-fable-5",
            input_tokens=10,
            output_tokens=out,
            cost_usd=0.01,
            source="hook",
            session_id=_SID,
        )

    turns = [_turn(0, 100), _turn(5, 250), _turn(10, 80)]
    assert collapse_gemini_sessions(turns) == turns


def test_import_rows_collapse_by_job_id() -> None:
    def _row(out: int) -> AiSession:
        return AiSession(
            start=datetime(2026, 6, 1, 10, 0),
            end=datetime(2026, 6, 1, 10, 30),
            tool="claude-code",
            model="claude-fable-5",
            input_tokens=10,
            output_tokens=out,
            cost_usd=0.01,
            source="import",
            session_id=_SID,
            job_id=f"claude:{_SID}",
        )

    out = collapse_gemini_sessions([_row(100), _row(900)])
    assert len(out) == 1
    assert out[0].output_tokens == 900


# ---------------------------------------------------------------------------
# Plausibility guard restored (the 12h → 7d incident)
# ---------------------------------------------------------------------------


def test_max_session_guard_is_12_hours() -> None:
    """Pin the constant: raising it to pass suspicious data re-opens the
    frozen-session-start hole for every collector at once."""
    assert _MAX_SESSION_SECONDS == 12 * 3600


def test_multi_day_session_is_implausible() -> None:
    session = AiSession(
        start=datetime(2026, 6, 1, 10, 0),
        end=datetime(2026, 6, 5, 10, 0),  # 4 days — the imported "session"
        tool="claude-code",
        model="claude-fable-5",
        input_tokens=10,
        output_tokens=100,
        cost_usd=0.01,
    )
    assert session_is_implausible(session, now=datetime(2026, 6, 6, 0, 0))


def test_multi_day_transcript_is_skipped(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_transcript(
        tmp_path,
        _transcript_events(
            cwd=str(project),
            start="2026-06-01T10:00:00.000Z",
            end="2026-06-05T10:00:00.000Z",
        ),
    )
    assert import_claude_sessions(project_dir=project) == []
    assert _claude_lines(project) == []


# ---------------------------------------------------------------------------
# State hygiene
# ---------------------------------------------------------------------------


def test_state_records_only_imported_ids(tmp_path: Path) -> None:
    """Skipped transcripts must not be marked imported — the incident state
    file recorded ~1,856 never-imported ids, permanently hiding them."""
    project = _project(tmp_path)
    _write_transcript(tmp_path, _transcript_events(cwd=str(project)))
    # A second, implausible transcript that will be skipped.
    _write_transcript(
        tmp_path,
        _transcript_events(
            cwd=str(project),
            session_id="aaaaaaaa-0000-0000-0000-000000000000",
            start="2026-06-01T10:00:00.000Z",
            end="2026-06-05T10:00:00.000Z",
        ),
        session_id="aaaaaaaa-0000-0000-0000-000000000000",
    )

    import_claude_sessions(project_dir=project)

    state = (tmp_path / "claude-imported").read_text(encoding="utf-8")
    assert _SID in state
    assert "aaaaaaaa" not in state, "skipped transcripts must stay re-checkable"


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_transcript(tmp_path, _transcript_events(cwd=str(project)))

    imported = import_claude_sessions(project_dir=project, dry_run=True)

    assert len(imported) == 1
    assert _claude_lines(project) == []
    assert not (tmp_path / "claude-imported").exists()


# ---------------------------------------------------------------------------
# Gemini importer dedup must see hook-covered sessions
# ---------------------------------------------------------------------------


def test_gemini_dedup_sees_hook_covered_session(tmp_path: Path) -> None:
    """Regression for the timer duplicate factory: parse_sessions collapses a
    gemini session to its best row, and when a hook row exists it wins —
    exposing session_id, not the importer's job_id. A dedup reading job_id
    alone re-imported the session on every 30-minute tick, and collapse hid
    the growing pile (~447 rows in the repaired Halyard ledger)."""
    from datetime import timedelta
    from unittest.mock import patch

    from halyard.ai_log import append_session
    from halyard.cli_importers import run_gemini_import

    sid = "feed0002-0000-0000-0000-000000000000"
    target = _project(tmp_path, "gem-project")

    # Only a HOOK row exists — session_id set, no job_id.
    append_session(
        target,
        AiSession(
            start=datetime.now() - timedelta(minutes=10),
            end=datetime.now() - timedelta(minutes=5),
            tool="gemini-cli",
            model="gemini-3-flash-preview",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.0,
            project="gem/project",
            source="hook",
            session_id=sid,
        ),
        direct=True,
    )

    class _Summary:
        session_id = sid
        start = datetime.now() - timedelta(minutes=10)
        end = datetime.now() - timedelta(minutes=5)
        dominant_model = "gemini-3-flash-preview"
        total_input = 100
        total_output = 50
        total_cache = 0
        total_tool_calls = 0
        total_tool_errors = 0
        cost_usd = 0.0

    fake = tmp_path / "gemtmp" / "gem-slug" / "chats" / "session-x.jsonl"
    with (
        patch("halyard.collectors.gemini_history.find_all_session_files", return_value=[fake]),
        patch("halyard.collectors.gemini_history.parse_session_file", return_value=_Summary()),
        patch("halyard.collectors.gemini_history.project_dir_for_slug", return_value=target),
        patch("halyard.hub.find_hub", return_value=None),
    ):
        n = run_gemini_import(dry_run=False, all_projects=True, quiet=True)

    assert n == 0, "hook-covered session must not re-import"
    raw = (target / "ai-sessions.log").read_text(encoding="utf-8")
    assert raw.count("gemini-cli") == 1  # the hook row only — no new append


# ---------------------------------------------------------------------------
# Copilot: patch aggregation without phantom requests
# ---------------------------------------------------------------------------


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def test_copilot_patch_beyond_snapshot_materialises(tmp_path: Path) -> None:
    """A request added entirely via patches (after the kind-0 snapshot) must
    be counted — the pre-v5.21 parser dropped it on the floor."""
    base = datetime.now() - timedelta(hours=1)
    events = [
        {"kind": 0, "v": {"creationDate": _ms(base), "requests": []}},
        {"kind": 2, "k": ["requests", 0, "timestamp"], "v": _ms(base)},
        {"kind": 2, "k": ["requests", 0, "completionTokens"], "v": 42},
        {
            "kind": 2,
            "k": ["requests", 0, "response"],
            "v": [{"kind": "message"}],
        },
    ]
    path = tmp_path / "session.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

    session = parse_chat_session(path)

    assert session is not None
    assert session.user_message_count == 1
    assert session.assistant_message_count == 1
    assert session.output_tokens == 42


def test_copilot_no_phantom_user_turns(tmp_path: Path) -> None:
    """Response patches for a high index must not fabricate user turns for
    every index below it."""
    base = datetime.now() - timedelta(hours=1)
    events = [
        {"kind": 0, "v": {"creationDate": _ms(base), "requests": []}},
        {"kind": 2, "k": ["requests", 3, "timestamp"], "v": _ms(base)},
        {"kind": 2, "k": ["requests", 3, "response"], "v": [{"kind": "message"}]},
    ]
    path = tmp_path / "session.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

    session = parse_chat_session(path)

    assert session is not None
    # Indices 0-2 are empty grow-padding: they carry no evidence and count
    # as requests, but the parser must not have invented turns beyond the
    # four reconstructed entries.
    assert session.user_message_count == 4
    assert session.assistant_message_count == 1


def test_copilot_aggregates_overwritten_response_parts(tmp_path: Path) -> None:
    """Successive response patches overwrite each other in the reconstructed
    state; evidence must aggregate across all of them."""
    base = datetime.now() - timedelta(hours=1)
    events = [
        {
            "kind": 0,
            "v": {
                "creationDate": _ms(base),
                "requests": [{"timestamp": _ms(base), "completionTokens": 10}],
            },
        },
        {
            "kind": 2,
            "k": ["requests", 0, "response"],
            "v": [{"kind": "thinking"}],
        },
        {
            "kind": 2,
            "k": ["requests", 0, "response"],
            "v": [{"kind": "toolInvocationSerialized", "toolId": "t1"}],
        },
        {
            "kind": 2,
            "k": ["requests", 0, "response"],
            "v": [{"kind": "message"}],
        },
    ]
    path = tmp_path / "session.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

    session = parse_chat_session(path)

    assert session is not None
    assert session.assistant_message_count == 2  # thinking + message
    assert session.tool_calls == 1  # the overwritten tool part survives
