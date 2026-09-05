"""v5.25 P0 — Grok CLI hook borrowing.

Grok merges hook definitions out of ``~/.claude/settings.json`` and
``~/.cursor/hooks.json`` (``[compat.claude] hooks`` / ``[compat.cursor]
hooks``, both ``true`` by default). Those are exactly the files Halyard
installs into, so a Grok session can invoke Halyard's Claude/Cursor hook
commands and have its work recorded under the wrong tool.

Two defences, both pinned here: the collectors refuse a foreign payload,
and ``doctor`` warns on machines that have not disabled compat scanning.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from halyard.collectors import foreign_harness
from halyard.doctor import _grok_compat_check

# Documented Grok common fields (10-hooks.md): camelCase, unlike Claude
# Code's and Cursor's snake_case.
_GROK_PAYLOAD = {
    "hookEventName": "Stop",
    "sessionId": "019febb6-13af-7382-8595-be0246e25bf8",
    "cwd": "/Users/you/project",
    "workspaceRoot": "/Users/you/project",
    "timestamp": "2026-08-10T12:47:48Z",
    "permissionMode": "default",
}

_CLAUDE_PAYLOAD = {
    "hook_event_name": "Stop",
    "session_id": "8e97e221-837f-41ab-9405-4175c44ac3a0",
    "transcript_path": "/tmp/transcript.jsonl",
    "cwd": "/Users/you/project",
    "stop_hook_active": False,
}

_CURSOR_PAYLOAD = {
    "cursor_version": "1.2.3",
    "workspace_roots": ["/Users/you/project"],
    "model": "claude-4-sonnet",
}


# --- discriminator ---------------------------------------------------------


def test_grok_payload_is_identified() -> None:
    assert foreign_harness(_GROK_PAYLOAD) == "grok"


def test_native_payloads_are_not_flagged() -> None:
    """The guard must be a positive Grok signature, not a snake_case heuristic."""
    assert foreign_harness(_CLAUDE_PAYLOAD) is None
    assert foreign_harness(_CURSOR_PAYLOAD) is None
    assert foreign_harness({}) is None


@pytest.mark.parametrize("marker", ["hookEventName", "workspaceRoot", "permissionMode"])
def test_any_single_grok_marker_is_enough(marker: str) -> None:
    assert foreign_harness({marker: "x"}) == "grok"


def test_sessionid_alone_is_not_a_grok_signal() -> None:
    """claude_code reads `session_id or sessionId`, so sessionId alone is ambiguous.

    Flagging on it would break any legitimate camelCase Claude payload; the
    guard deliberately keys on fields Claude Code never sends.
    """
    assert foreign_harness({"sessionId": "abc"}) is None


# --- collector refusal -----------------------------------------------------


def _project(tmp_path: Path) -> Path:
    p = tmp_path / "project"
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[project]\nslug = 'test'\n", encoding="utf-8")
    (p / "ai-sessions.log").write_text("; Halyard AI session log\n", encoding="utf-8")
    return p


def test_claude_hook_writes_no_row_for_a_grok_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard.ai_log import parse_sessions
    from halyard.collectors import claude_code

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(claude_code, "_CC_SESSION_FILE", home / ".halyard" / "cc-session")
    monkeypatch.setattr(claude_code, "_read_payload", lambda: dict(_GROK_PAYLOAD))

    project = _project(tmp_path)
    monkeypatch.chdir(project)

    assert claude_code.handle_stop_hook() == 0
    assert parse_sessions(project) == []


def test_cursor_hook_writes_no_row_for_a_grok_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard.ai_log import parse_sessions
    from halyard.collectors import cursor

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    state = home / ".halyard" / "cursor-session"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"start": "2026-08-10T12:00:00"}), encoding="utf-8")
    monkeypatch.setattr(cursor, "_CURSOR_SESSION_FILE", state)
    monkeypatch.setattr(cursor, "_read_payload", lambda: dict(_GROK_PAYLOAD))

    project = _project(tmp_path)
    monkeypatch.chdir(project)

    assert cursor.handle_stop_hook() == 0
    assert parse_sessions(project) == []
    assert not state.exists(), "a refused fire must not leave stale session state"


# --- doctor ----------------------------------------------------------------


@pytest.fixture
def _grok_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A machine with Grok installed and Halyard hooks in both borrowed files."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".cursor").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", lambda: home)

    (home / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {
                            "matcher": "",
                            "hooks": [{"type": "command", "command": "/x/halyard cc-hook"}],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (home / ".cursor" / "hooks.json").write_text(
        json.dumps({"hooks": {"stop": [{"command": "/x/halyard cursor-hook"}]}}),
        encoding="utf-8",
    )

    grok = tmp_path / "grok"
    grok.mkdir()
    monkeypatch.setenv("GROK_HOME", str(grok))
    return grok


def test_doctor_skips_when_grok_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "nowhere")
    monkeypatch.delenv("GROK_HOME", raising=False)
    assert _grok_compat_check() is None


def test_doctor_warns_when_compat_is_at_its_default(_grok_home: Path) -> None:
    (_grok_home / "config.toml").write_text('[cli]\ninstaller = "internal"\n', encoding="utf-8")

    check = _grok_compat_check()
    assert check is not None
    assert check.status == "warning"
    assert check.id == "grok.compat"
    assert check.fix is not None and "hooks = false" in check.fix


def test_doctor_warns_with_no_config_file_at_all(_grok_home: Path) -> None:
    """Absent config means every compat cell is at its default of true."""
    check = _grok_compat_check()
    assert check is not None
    assert check.status == "warning"


def test_doctor_quiet_once_both_toggles_are_set(_grok_home: Path) -> None:
    (_grok_home / "config.toml").write_text(
        "[compat.claude]\nhooks = false\n\n[compat.cursor]\nhooks = false\n", encoding="utf-8"
    )
    assert _grok_compat_check() is None


def test_doctor_still_warns_when_only_one_toggle_is_set(_grok_home: Path) -> None:
    """Half a remedy is still a live mis-attribution path."""
    (_grok_home / "config.toml").write_text("[compat.claude]\nhooks = false\n", encoding="utf-8")

    check = _grok_compat_check()
    assert check is not None
    assert "cursor" in check.detail
    assert check.fix is not None and "compat.cursor" in check.fix
    assert "compat.claude" not in check.fix, "already-set toggle must not be re-suggested"


def test_doctor_quiet_when_halyard_hooks_are_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing to borrow ⇒ nothing to warn about."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    grok = tmp_path / "grok"
    grok.mkdir()
    monkeypatch.setenv("GROK_HOME", str(grok))

    assert _grok_compat_check() is None


def test_doctor_tolerates_malformed_grok_config(_grok_home: Path) -> None:
    """A broken config must warn (defaults apply), never raise out of doctor."""
    (_grok_home / "config.toml").write_text("this is not = valid toml [[[", encoding="utf-8")

    check = _grok_compat_check()
    assert check is not None
    assert check.status == "warning"


def test_empty_grok_home_env_falls_back_to_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Path("") is PosixPath("."), which is truthy — an `or` fallback resolves
    GROK_HOME to the cwd and reads the wrong config."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("GROK_HOME", "")
    monkeypatch.chdir(tmp_path)

    # No ~/.grok ⇒ None. If the empty env var leaked through as ".", this
    # would inspect the cwd instead and could return a check.
    assert _grok_compat_check() is None


# --- rendering -------------------------------------------------------------


def test_doctor_text_survives_rich_markup(_grok_home: Path) -> None:
    """The fix string contains "[compat.claude]", which Rich reads as markup.

    doctor.render_text returns plain text by contract (render_json emits the
    same strings raw), so the CLI must escape before printing or the TOML
    table names vanish from the user's terminal.
    """
    from rich.console import Console
    from rich.markup import escape

    from halyard.doctor import DoctorReport, render_text

    check = _grok_compat_check()
    assert check is not None

    console = Console(file=None, width=200, record=True)
    console.print(escape(render_text(DoctorReport(status="warning", checks=[check]))))
    out = console.export_text()

    assert "[compat.claude]" in out
    assert "[compat.cursor]" in out
