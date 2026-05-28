"""Tests for manual and sample AI session capture commands."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.ai_log import (
    AI_LOG_FILENAME,
    HEADER,
    AiSession,
    parse_sessions,
    write_unattributed_session,
)
from halyard.cli import app
from halyard.hub import set_hub

runner = CliRunner()


def _session() -> AiSession:
    return AiSession(
        start=datetime(2026, 5, 7, 10, 0, 0),
        end=datetime(2026, 5, 7, 10, 30, 0),
        tool="codex",
        model="gpt-5.5",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.0,
    )


def _init_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (tmp_path / "time.timeclock").write_text("; time\n", encoding="utf-8")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")
    (tmp_path / "projects.toml").write_text('[[project]]\nslug = "acme:auth"\n', encoding="utf-8")


def test_record_session_appends_manual_session(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)

    result = runner.invoke(
        app,
        [
            "record-session",
            "--project",
            "acme:auth",
            "--tool",
            "codex",
            "--model",
            "claude-sonnet-4-6",
            "--input-tokens",
            "1000",
            "--output-tokens",
            "500",
        ],
    )

    assert result.exit_code == 0, result.output
    session = parse_sessions(tmp_path)[0]
    assert session.tool == "codex"
    assert session.project == "acme:auth"
    assert session.input_tokens == 1000
    assert session.output_tokens == 500
    assert session.source == "manual"


def test_record_session_vscode_tool_gets_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path)

    result = runner.invoke(
        app,
        [
            "record-session",
            "--project",
            "acme:auth",
            "--tool",
            "vscode",
            "--model",
            "github-copilot",
            "--minutes",
            "12",
            "--note",
            "Copilot chat",
        ],
    )

    assert result.exit_code == 0, result.output
    session = parse_sessions(tmp_path)[0]
    assert session.tool == "vscode"
    assert session.model == "github-copilot"
    assert session.project == "acme:auth"
    assert session.tokens_available is False
    assert session.note == "Copilot chat"


def test_record_session_preserves_metadata_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path)

    result = runner.invoke(
        app,
        [
            "record-session",
            "--project",
            "acme:auth",
            "--tool",
            "vscode",
            "--model",
            "github-copilot",
            "--source",
            "vscode-extension",
            "--interaction-count",
            "6",
            "--user-message-count",
            "3",
            "--assistant-message-count",
            "3",
            "--accepted-suggestion-count",
            "2",
            "--rejected-suggestion-count",
            "1",
            "--files-touched-count",
            "4",
            "--test-run-count",
            "1",
            "--test-status",
            "pass",
            "--human-active-seconds",
            "900",
            "--interaction-data-available",
            "--outcome-data-available",
            "--telemetry-source",
            "vscode-extension",
            "--telemetry-trust",
            "observed",
        ],
    )

    assert result.exit_code == 0, result.output
    session = parse_sessions(tmp_path)[0]
    assert session.source == "vscode-extension"
    assert session.interaction_count == 6
    assert session.user_message_count == 3
    assert session.assistant_message_count == 3
    assert session.accepted_suggestion_count == 2
    assert session.rejected_suggestion_count == 1
    assert session.files_touched_count == 4
    assert session.test_run_count == 1
    assert session.test_status == "pass"
    assert session.human_active_seconds == 900
    assert session.interaction_data_available is True
    assert session.outcome_data_available is True
    assert session.telemetry_source == "vscode-extension"
    assert session.telemetry_trust == "observed"


def test_sample_session_appends_realistic_session(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)

    result = runner.invoke(app, ["sample-session", "--project", "acme:auth"])

    assert result.exit_code == 0, result.output
    session = parse_sessions(tmp_path)[0]
    assert session.tool == "claude-code"
    assert session.model == "claude-sonnet-4-6"
    assert session.project == "acme:auth"
    assert session.input_tokens > 0
    assert session.cost_usd > 0


def test_assign_unattributed_command_uses_project_option(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _init_project(tmp_path)
    runner.invoke(app, ["record-session", "--tool", "codex"])

    result = runner.invoke(app, ["assign-unattributed", "--project", "acme:auth"])

    assert result.exit_code == 0, result.output
    assert parse_sessions(tmp_path)[0].project == "acme:auth"


def test_assign_unattributed_global_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    result = runner.invoke(app, ["assign-unattributed"])

    assert result.exit_code == 0, result.output
    assert "No unattributed sessions" in result.output


def test_assign_unattributed_global_assigns_to_current_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _init_project(tmp_path)
    write_unattributed_session(_session())

    result = runner.invoke(app, ["assign-unattributed", "--project", "acme:auth"])

    assert result.exit_code == 0, result.output
    assert parse_sessions(tmp_path)[0].project == "acme:auth"
    assert (tmp_path / ".halyard" / "unattributed.log").read_text(encoding="utf-8") == ""


def test_assign_unattributed_records_manual_attr_method(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: interactive assignment must record ``attr_method=manual``
    so invoice/audit explainability can distinguish manual reassignment
    from auto-inferred attribution (timer / git / repo-map). Without this
    provenance, manually-routed sessions would be indistinguishable from
    high-confidence captures in the trust ledger.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _init_project(tmp_path)
    write_unattributed_session(_session())

    result = runner.invoke(app, ["assign-unattributed", "--project", "acme:auth"])

    assert result.exit_code == 0, result.output
    assigned = parse_sessions(tmp_path)[0]
    assert assigned.project == "acme:auth"
    assert assigned.attr_method == "manual"


def test_assign_unattributed_global_moves_to_hub(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = tmp_path / "work"
    hub = tmp_path / "hub"
    work.mkdir()
    hub.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _init_project(hub)
    set_hub(hub)
    write_unattributed_session(_session())

    result = runner.invoke(app, ["assign-unattributed"], input="h\n")

    assert result.exit_code == 0, result.output
    assert parse_sessions(hub)[0].tool == "codex"
    assert (tmp_path / ".halyard" / "unattributed.log").read_text(encoding="utf-8") == ""


def test_assign_unattributed_global_discards_after_confirm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    write_unattributed_session(_session())

    result = runner.invoke(app, ["assign-unattributed"], input="d\ny\n")

    assert result.exit_code == 0, result.output
    assert (tmp_path / ".halyard" / "unattributed.log").read_text(encoding="utf-8") == ""


def test_assign_unattributed_global_skip_keeps_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    write_unattributed_session(_session())

    result = runner.invoke(app, ["assign-unattributed"], input="s\n")

    assert result.exit_code == 0, result.output
    assert "codex" in (tmp_path / ".halyard" / "unattributed.log").read_text(encoding="utf-8")


def test_check_log_reports_invalid_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _init_project(tmp_path)
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER + "s bad\n", encoding="utf-8")

    result = runner.invoke(app, ["check-log"])

    assert result.exit_code == 1
    assert "Line 3: expected session line" in result.output
    assert "s bad" in result.output


def test_check_log_uses_hub_when_no_project_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """check-log falls back to hub log when run outside a project directory."""
    hub = tmp_path / "hub"
    hub.mkdir()
    (hub / "halyard.toml").write_text("[business]\nhub = true\n", encoding="utf-8")
    (hub / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")

    non_project = tmp_path / "elsewhere"
    non_project.mkdir()
    monkeypatch.chdir(non_project)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    set_hub(hub)

    result = runner.invoke(app, ["check-log"])

    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_assign_unattributed_rejects_unknown_project_slug(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """assign-unattributed --project exits 1 when slug not in projects.toml.

    No sessions in the unattributed log so the non-interactive path is taken,
    where _is_valid_project raises typer.Exit(code=1) on an unknown slug.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _init_project(tmp_path)
    # Do NOT write any unattributed sessions — forces the non-interactive path.

    result = runner.invoke(app, ["assign-unattributed", "--project", "unknown:slug"])

    assert result.exit_code == 1
    assert "unknown:slug" in result.output
