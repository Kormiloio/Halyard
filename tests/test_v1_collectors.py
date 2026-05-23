"""Tests for the Claude Code hook collector and install-hook command."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from halyard.ai_log import AI_LOG_FILENAME, HEADER, parse_sessions
from halyard.cli import app
from halyard.cli_hooks import _CC_HOOKS, _resolve_claude_hook_entries
from halyard.collectors.claude_code import handle_stop_hook, record_session_start

_RECENT_START = (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")

runner = CliRunner()

CC_SESSION_FILE = Path.home() / ".halyard" / "cc-session"
HALYARD_ACTIVE = Path.home() / ".halyard" / "active"


@pytest.fixture(autouse=True)
def clean_state() -> None:  # type: ignore[misc]
    CC_SESSION_FILE.unlink(missing_ok=True)
    HALYARD_ACTIVE.unlink(missing_ok=True)
    yield  # type: ignore[misc]
    CC_SESSION_FILE.unlink(missing_ok=True)
    HALYARD_ACTIVE.unlink(missing_ok=True)


def _init_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\nname='Test'\n")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER)


# ---------------------------------------------------------------------------
# cc-session (UserPromptSubmit hook)
# ---------------------------------------------------------------------------


def test_cc_session_writes_start_file() -> None:
    import json

    record_session_start()
    assert CC_SESSION_FILE.exists()
    data = json.loads(CC_SESSION_FILE.read_text())
    ts = datetime.fromisoformat(data["start"])
    assert isinstance(ts, datetime)


def test_cc_session_does_not_overwrite_existing() -> None:
    CC_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CC_SESSION_FILE.write_text("2026-05-06T09:00:00")
    record_session_start()
    assert CC_SESSION_FILE.read_text().strip() == "2026-05-06T09:00:00"


# ---------------------------------------------------------------------------
# cc-hook (Stop hook)
# ---------------------------------------------------------------------------


def _run_stop_hook(tmp_path: Path, payload: dict) -> int:  # type: ignore[type-arg]
    with (
        patch("halyard.collectors.claude_code.find_project_dir", return_value=tmp_path),
        patch("sys.stdin", StringIO(json.dumps(payload))),
    ):
        return handle_stop_hook()


def test_stop_hook_writes_session_record(tmp_path: Path) -> None:
    _init_project(tmp_path)
    CC_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CC_SESSION_FILE.write_text(_RECENT_START)

    payload = {
        "model": "claude-sonnet-4-6",
        "usage": {"input_tokens": 5000, "output_tokens": 1200},
    }
    rc = _run_stop_hook(tmp_path, payload)

    assert rc == 0
    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 1
    s = sessions[0]
    assert s.tool == "claude-code"
    assert s.model == "claude-sonnet-4-6"
    assert s.input_tokens == 5000
    assert s.output_tokens == 1200
    assert s.tokens_available is True
    assert s.source == "hook"


def test_stop_hook_clears_session_file(tmp_path: Path) -> None:
    _init_project(tmp_path)
    CC_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CC_SESSION_FILE.write_text(_RECENT_START)

    _run_stop_hook(tmp_path, {"model": "claude-sonnet-4-6", "usage": {}})

    assert not CC_SESSION_FILE.exists()


def test_stop_hook_handles_missing_usage(tmp_path: Path) -> None:
    _init_project(tmp_path)
    rc = _run_stop_hook(tmp_path, {"model": "claude-sonnet-4-6"})

    assert rc == 0
    s = parse_sessions(tmp_path)[0]
    assert s.input_tokens == 0
    assert s.output_tokens == 0
    assert s.tokens_available is False


def test_stop_hook_skips_evidence_free_empty_payload(tmp_path: Path) -> None:
    # v2.47: an empty Stop payload (unknown model, 0 tokens, no
    # transcript/interactions) is not a turn — no stub row is written.
    _init_project(tmp_path)
    rc = _run_stop_hook(tmp_path, {})

    assert rc == 0
    assert parse_sessions(tmp_path) == []


def test_stop_hook_writes_unattributed_when_not_in_halyard_project(tmp_path: Path) -> None:
    # Payload carries evidence (real model + tokens) so the session is
    # real and the not-in-a-project routing to unattributed is exercised.
    payload = '{"model": "claude-sonnet-4-6", "usage": {"input_tokens": 100, "output_tokens": 50}}'
    with (
        patch("halyard.collectors.claude_code.find_project_dir", return_value=None),
        patch("halyard.collectors.claude_code.find_hub", return_value=None),
        patch(
            "halyard.collectors.claude_code.write_unattributed_session",
            return_value=tmp_path / "unattributed.log",
        ) as write_unattributed,
        patch("sys.stdin", StringIO(payload)),
        patch("sys.stderr", StringIO()) as stderr,
    ):
        rc = handle_stop_hook()
    assert rc == 0
    write_unattributed.assert_called_once()
    assert "halyard adopt" in stderr.getvalue()


def test_stop_hook_picks_up_active_project(tmp_path: Path) -> None:
    _init_project(tmp_path)
    HALYARD_ACTIVE.parent.mkdir(parents=True, exist_ok=True)
    HALYARD_ACTIVE.write_text(
        f"timeclock={tmp_path}/time.timeclock\nslug=acme:auth\nstarted=2026-05-06 10:00:00\n"
    )

    _run_stop_hook(
        tmp_path,
        {
            "model": "claude-opus-4-7",
            "usage": {"input_tokens": 1000, "output_tokens": 200},
        },
    )

    s = parse_sessions(tmp_path)[0]
    assert s.project == "acme:auth"


def test_stop_hook_skips_cursor_events(tmp_path: Path) -> None:
    # Cursor fires Claude Code's Stop hook internally — we must not double-record
    _init_project(tmp_path)
    payload = {
        "cursor_version": "0.50.0",
        "model": "claude-opus-4-7",
        "usage": {"input_tokens": 1000, "output_tokens": 200},
    }
    _run_stop_hook(tmp_path, payload)
    assert parse_sessions(tmp_path) == []


def test_stop_hook_captures_cache_tokens(tmp_path: Path) -> None:
    _init_project(tmp_path)
    payload = {
        "model": "claude-opus-4-7",
        "usage": {
            "input_tokens": 10000,
            "output_tokens": 2000,
            "cache_read_input_tokens": 8000,
            "cache_creation_input_tokens": 2000,
        },
    }
    _run_stop_hook(tmp_path, payload)
    s = parse_sessions(tmp_path)[0]
    assert s.cache_read == 8000
    assert s.cache_write == 2000


def test_stop_hook_records_client_surface_if_detected(tmp_path: Path) -> None:
    _init_project(tmp_path)
    with patch("halyard.collectors.claude_code.detect_surface", return_value="cli"):
        _run_stop_hook(
            tmp_path,
            {
                "model": "claude-opus-4-7",
                "usage": {"input_tokens": 1000, "output_tokens": 200},
            },
        )

    s = parse_sessions(tmp_path)[0]
    assert s.client_surface == "cli"


# ---------------------------------------------------------------------------
# install-hook
# ---------------------------------------------------------------------------


def test_install_hook_creates_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    result = runner.invoke(app, ["install-hook"])

    assert result.exit_code == 0
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "Stop" in settings["hooks"]
    assert "UserPromptSubmit" in settings["hooks"]


def test_install_hook_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    runner.invoke(app, ["install-hook"])
    runner.invoke(app, ["install-hook"])

    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert len(settings["hooks"]["Stop"]) == 1


def test_install_hook_preserves_existing_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(json.dumps({"model": "claude-opus-4-7"}))

    runner.invoke(app, ["install-hook"])

    settings = json.loads((settings_dir / "settings.json").read_text())
    assert settings["model"] == "claude-opus-4-7"
    assert "hooks" in settings


def test_resolve_claude_hook_entries_rewrites_halyard_binary() -> None:
    entries = _CC_HOOKS["UserPromptSubmit"]

    resolved = _resolve_claude_hook_entries(entries, "/usr/bin/halyard")

    assert resolved is not entries
    assert resolved[0]["hooks"][0]["command"] == "/usr/bin/halyard cc-session"
    assert entries[0]["hooks"][0]["command"] == "halyard cc-session"


# ---------------------------------------------------------------------------
# D-1: Attribution provenance — claude_code collector
# ---------------------------------------------------------------------------


def test_stop_hook_timer_attribution_sets_attr_method_timer(tmp_path: Path) -> None:
    """When active timer is running, attr_method=timer and no attribution:inferred tag."""
    _init_project(tmp_path)
    HALYARD_ACTIVE.parent.mkdir(parents=True, exist_ok=True)
    HALYARD_ACTIVE.write_text(
        f"timeclock={tmp_path}/time.timeclock\nslug=acme:auth\nstarted=2026-05-06 10:00:00\n"
    )

    _run_stop_hook(
        tmp_path,
        {"model": "claude-sonnet-4-6", "usage": {"input_tokens": 1000, "output_tokens": 200}},
    )

    s = parse_sessions(tmp_path)[0]
    assert s.project == "acme:auth"
    assert s.attr_method == "timer"
    assert "attribution:inferred" not in s.tags


def test_stop_hook_git_inference_sets_attr_method_git(tmp_path: Path) -> None:
    """No active timer → git inference records the specific rung
    (v2.65: git-auto, not the old catch-all "git") + inferred tag."""
    import io

    _init_project(tmp_path)
    inferred_project = "git/my-repo"
    payload = json.dumps(
        {"model": "claude-sonnet-4-6", "usage": {"input_tokens": 500, "output_tokens": 100}}
    )

    with (
        patch("halyard.collectors.claude_code.find_project_dir", return_value=tmp_path),
        patch(
            "halyard.collectors.claude_code.infer_project_with_source",
            return_value=(inferred_project, "git-auto"),
        ),
        patch("sys.stdin", io.StringIO(payload)),
    ):
        handle_stop_hook()

    s = parse_sessions(tmp_path)[0]
    assert s.project == inferred_project
    assert s.attr_method == "git-auto"
    assert "attribution:inferred" in s.tags


def test_stop_hook_no_project_sets_attr_method_none(tmp_path: Path) -> None:
    """When both active timer and git inference return None, attr_method is not set."""
    import io

    _init_project(tmp_path)
    payload = json.dumps({"model": "claude-sonnet-4-6", "usage": {}})

    with (
        patch("halyard.collectors.claude_code.find_project_dir", return_value=tmp_path),
        patch(
            "halyard.collectors.claude_code.infer_project_with_source",
            return_value=(None, None),
        ),
        patch("sys.stdin", io.StringIO(payload)),
    ):
        handle_stop_hook()

    s = parse_sessions(tmp_path)[0]
    assert s.project is None
    assert s.attr_method is None
    assert "attribution:inferred" not in s.tags


# ---------------------------------------------------------------------------
# _read_from_transcript with since= filtering
# ---------------------------------------------------------------------------


def _make_transcript(tmp_path: Path, turns: list[dict]) -> str:  # type: ignore[type-arg]
    """Write a JSONL transcript and return its path string."""
    lines = [json.dumps(t) for t in turns]
    p = tmp_path / "transcript.jsonl"
    p.write_text("\n".join(lines) + "\n")
    return str(p)


def _turn(  # type: ignore[return]
    ts: str, inp: int, out: int, *, model: str = "claude-sonnet-4-6", branch: str | None = None
) -> dict:  # type: ignore[type-arg]
    obj: dict = {  # type: ignore[type-arg]
        "type": "assistant",
        "timestamp": ts,
        "message": {"model": model, "usage": {"input_tokens": inp, "output_tokens": out}},
    }
    if branch:
        obj["gitBranch"] = branch
    return obj


def test_read_from_transcript_no_since(tmp_path: Path) -> None:
    """Without since=, all assistant turns are summed."""
    from halyard.collectors.claude_code import _read_from_transcript

    transcript = _make_transcript(
        tmp_path,
        [
            _turn("2026-05-09T10:00:00.000Z", 100, 50, branch="main"),
            _turn("2026-05-09T11:00:00.000Z", 200, 80),
        ],
    )
    st = _read_from_transcript(transcript)
    assert st.model == "claude-sonnet-4-6"
    assert st.input_tokens == 300
    assert st.output_tokens == 130
    assert st.branch == "main"
    assert st.assistant_count == 2


def test_read_from_transcript_since_filters_earlier_turns(tmp_path: Path) -> None:
    """`since` filters turns timestamped before the cutoff."""
    from halyard.collectors.claude_code import _read_from_transcript

    transcript = _make_transcript(
        tmp_path,
        [
            _turn("2026-05-09T10:00:00.000Z", 100, 50),
            _turn("2026-05-09T11:30:00.000Z", 200, 80),
        ],
    )
    # since is local-naive; use UTC→local conversion to match what the stop hook provides
    since = (
        datetime.fromisoformat("2026-05-09T11:00:00+00:00").astimezone(tz=None).replace(tzinfo=None)
    )
    st = _read_from_transcript(transcript, since=since)
    assert st.input_tokens == 200
    assert st.output_tokens == 80
    assert st.assistant_count == 1


def test_read_from_transcript_since_includes_boundary_turn(tmp_path: Path) -> None:
    """A turn with timestamp exactly equal to since is included (>=)."""
    from halyard.collectors.claude_code import _read_from_transcript

    transcript = _make_transcript(
        tmp_path,
        [_turn("2026-05-09T11:00:00.000Z", 42, 7)],
    )
    since = (
        datetime.fromisoformat("2026-05-09T11:00:00+00:00").astimezone(tz=None).replace(tzinfo=None)
    )
    st = _read_from_transcript(transcript, since=since)
    assert st.input_tokens == 42
    assert st.output_tokens == 7
    assert st.assistant_count == 1


def test_read_from_transcript_since_excludes_all(tmp_path: Path) -> None:
    """When since is after all turns, totals are zero."""
    from halyard.collectors.claude_code import _read_from_transcript

    transcript = _make_transcript(
        tmp_path,
        [_turn("2026-05-09T10:00:00.000Z", 999, 500)],
    )
    since = datetime(2026, 5, 9, 23, 0, 0)
    st = _read_from_transcript(transcript, since=since)
    assert st.input_tokens == 0
    assert st.output_tokens == 0
    assert st.assistant_count == 0


# ---------------------------------------------------------------------------
# _read_session_state UTC / legacy roundtrip
# ---------------------------------------------------------------------------


def test_read_session_state_utc_format() -> None:
    """Z-suffixed start string (legacy) is converted to local-naive datetime."""
    from halyard.collectors.claude_code import _read_session_state

    state = {"start": "2026-05-09T14:30:00Z", "sha_at_start": "abc123"}
    CC_SESSION_FILE.write_text(json.dumps(state))
    result = _read_session_state()
    expected = (
        datetime.fromisoformat("2026-05-09T14:30:00+00:00").astimezone(tz=None).replace(tzinfo=None)
    )
    assert result["start_dt"] == expected
    assert result["sha"] == "abc123"


def test_record_session_start_writes_local_iso(tmp_path: Path) -> None:
    """record_session_start writes a plain local ISO timestamp (no Z suffix)."""
    with (
        patch("halyard.collectors.claude_code.find_project_dir", return_value=None),
        patch("halyard.collectors.claude_code.read_active_project", return_value=None),
        patch("halyard.collectors.claude_code.head_sha", return_value=None),
    ):
        record_session_start()

    raw = json.loads(CC_SESSION_FILE.read_text())
    assert not raw["start"].endswith("Z"), f"Expected no Z suffix, got: {raw['start']}"
    dt = datetime.fromisoformat(raw["start"])
    assert dt.tzinfo is None
