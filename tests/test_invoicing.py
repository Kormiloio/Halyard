"""Tests for `halyard invoice` and `halyard log`."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.cli import app

runner = CliRunner()


def _init_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text(
        """
[business]
name = "Test Consulting"
currency = "USD"
default_due_days = 30

[invoicing]
counter = 0
"""
    )
    (tmp_path / "clients.toml").write_text(
        """
[[client]]
slug = "acme"
name = "Acme Corp"
hourly_rate = 100
"""
    )
    (tmp_path / "projects.toml").write_text(
        """
[[project]]
slug = "auth"
client_slug = "acme"
name = "Auth"
hourly_rate = 150
"""
    )
    (tmp_path / "time.timeclock").write_text(
        """
i 2026-05-06 10:00:00 acme:auth
o 2026-05-06 12:00:00
"""
    )
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER)
    (tmp_path / "invoices").mkdir()


def test_invoice_writes_markdown_and_increments_counter(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)

    result = runner.invoke(app, ["invoice", "acme", "--period", "2026-05"])

    assert result.exit_code == 0, result.output
    invoice_path = tmp_path / "invoices" / "2026-05-001-acme.md"
    assert invoice_path.exists()
    rendered = invoice_path.read_text()
    assert "Acme Corp" in rendered
    assert "Auth" in rendered
    assert "USD 300.00" in rendered
    assert "counter = 1" in (tmp_path / "halyard.toml").read_text()


def test_invoice_dry_run_does_not_write_or_increment(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)

    result = runner.invoke(app, ["invoice", "acme", "--period", "2026-05", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "Invoice 2026-05-001" in result.output
    assert not (tmp_path / "invoices" / "2026-05-001-acme.md").exists()
    assert "counter = 0" in (tmp_path / "halyard.toml").read_text()


def test_log_json_returns_local_summary(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime.now(),
            end=datetime.now(),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cost_usd=1.25,
            project="acme:auth",
        ),
    )

    result = runner.invoke(app, ["log", "what did I spend?", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["session_count"] == 1
    assert payload["cost_usd_total"] == 1.25
    assert payload["agent"] == "local"


def test_log_agent_claude_requires_api_key(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)

    result = runner.invoke(app, ["log", "what did I spend?", "--agent", "claude"])

    assert result.exit_code == 1
    assert "Missing ANTHROPIC_API_KEY" in result.output


def test_log_rejects_unknown_agent(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)

    result = runner.invoke(app, ["log", "what did I spend?", "--agent", "openai"])

    assert result.exit_code == 1
    assert "--agent must be one of" in result.output


def test_log_infers_tool_and_period_from_query(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 6, 10),
            end=datetime(2026, 5, 6, 11),
            tool="cursor",
            model="cursor-unknown",
            input_tokens=100,
            output_tokens=50,
            cost_usd=2.00,
            project="acme:auth",
        ),
    )
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 6, 12),
            end=datetime(2026, 5, 6, 13),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cost_usd=9.00,
            project="acme:auth",
        ),
    )

    with monkeypatch.context() as m:
        import halyard.log_agent as log_agent

        m.setattr(log_agent, "datetime", _FixedDatetime)
        result = runner.invoke(app, ["log", "what did Cursor cost this week?", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["period"] == "week"
    assert payload["session_count"] == 1
    assert payload["cost_usd_total"] == 2.0
    assert payload["filters"]["tool"] == "cursor"


def test_log_explicit_flags_override_inferred_filters(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime.now(),
            end=datetime.now(),
            tool="cursor",
            model="cursor-unknown",
            input_tokens=100,
            output_tokens=50,
            cost_usd=2.00,
            project="acme:auth",
        ),
    )
    append_session(
        tmp_path,
        AiSession(
            start=datetime.now(),
            end=datetime.now(),
            tool="gemini-cli",
            model="gemini-2.0-pro",
            input_tokens=100,
            output_tokens=50,
            cost_usd=3.00,
            project="acme:auth",
        ),
    )

    result = runner.invoke(app, ["log", "what did Cursor cost?", "--tool", "gemini-cli", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["session_count"] == 1
    assert payload["cost_usd_total"] == 3.0
    assert payload["filters"]["tool"] == "gemini-cli"


def test_log_filters_project_model_and_branch(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime.now(),
            end=datetime.now(),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cost_usd=4.00,
            project="acme:auth",
            tags=["branch:main"],
        ),
    )
    append_session(
        tmp_path,
        AiSession(
            start=datetime.now(),
            end=datetime.now(),
            tool="claude-code",
            model="claude-opus-4-7",
            input_tokens=100,
            output_tokens=50,
            cost_usd=8.00,
            project="acme:auth",
            tags=["branch:feature"],
        ),
    )

    result = runner.invoke(
        app,
        [
            "log",
            "cost for acme/auth using model sonnet on main",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["session_count"] == 1
    assert payload["cost_usd_total"] == 4.0
    assert payload["filters"]["project"] == "acme:auth"
    assert payload["filters"]["model"] == "sonnet"
    assert payload["filters"]["branch"] == "main"


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[no-untyped-def]
        return cls(2026, 5, 7, 12)
