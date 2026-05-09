"""Tests for `halyard invoice` and `halyard log`."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from typer.testing import CliRunner

import halyard.log_config as log_config
from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.cli import app
from halyard.invoicing import ClientRecord, _effective_rate
from halyard.log_agent import run_log_query

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


def test_run_log_query_uses_hub_fallback(tmp_path: Path, monkeypatch: object) -> None:
    hub_dir = tmp_path / "hub"
    hub_dir.mkdir()
    (hub_dir / AI_LOG_FILENAME).write_text(HEADER)
    monkeypatch.setattr("halyard.hub.find_hub", lambda: hub_dir)  # type: ignore[attr-defined]

    response = run_log_query("what did I spend?", project_dir=None, agent="local")

    assert response.data_source == f"hub:{hub_dir}"


def test_log_agent_claude_requires_api_key(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)

    result = runner.invoke(app, ["log", "what did I spend?", "--agent", "claude"])

    assert result.exit_code == 1
    assert "Missing ANTHROPIC_API_KEY" in result.output


def test_log_rejects_unknown_agent(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)

    result = runner.invoke(app, ["log", "what did I spend?", "--agent", "unknown-agent"])

    assert result.exit_code == 1
    assert "--agent must be one of" in result.output


def test_log_cli_agent_overrides_config(tmp_path: Path, monkeypatch: object) -> None:
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
    config_file = tmp_path / "config.toml"
    config_file.write_text('[log]\ndefault_agent = "claude"\n')
    monkeypatch.setattr(log_config, "_LOG_CONFIG_FILE", config_file)  # type: ignore[attr-defined]

    result = runner.invoke(app, ["log", "what did I spend?", "--agent", "local", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["agent"] == "local"


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
            "cost for acme/auth using model sonnet on branch main",
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


# ---------------------------------------------------------------------------
# AI evidence appendix tests (v2 task 5.x)
# ---------------------------------------------------------------------------


def _ai_session(
    project: str = "acme:auth",
    tool: str = "claude-code",
    model: str = "claude-sonnet-4-6",
    cost: float = 2.50,
    input_tokens: int = 1000,
    output_tokens: int = 500,
) -> AiSession:
    from datetime import timedelta

    start = datetime(2026, 5, 6, 10, 0)
    return AiSession(
        start=start,
        end=start + timedelta(minutes=30),
        tool=tool,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        project=project,
    )


def test_ai_evidence_appendix_not_included_by_default(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)

    result = runner.invoke(app, ["invoice", "acme", "--period", "2026-05"])

    assert result.exit_code == 0, result.output
    rendered = (tmp_path / "invoices" / "2026-05-001-acme.md").read_text()
    assert "AI Usage Evidence" not in rendered


def test_ai_evidence_appendix_no_sessions(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)

    result = runner.invoke(app, ["invoice", "acme", "--period", "2026-05", "--include-ai-evidence"])

    assert result.exit_code == 0, result.output
    rendered = (tmp_path / "invoices" / "2026-05-001-acme.md").read_text()
    assert "## AI Usage Evidence" in rendered
    assert "No AI sessions recorded for this period" in rendered


def test_ai_evidence_appendix_with_direct_api_sessions(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)
    append_session(tmp_path, _ai_session(cost=3.75))

    result = runner.invoke(app, ["invoice", "acme", "--period", "2026-05", "--include-ai-evidence"])

    assert result.exit_code == 0, result.output
    rendered = (tmp_path / "invoices" / "2026-05-001-acme.md").read_text()
    assert "## AI Usage Evidence" in rendered
    assert "Direct API" in rendered
    assert "captured from API responses" in rendered
    assert "claude-code" in rendered
    assert "claude-sonnet-4-6" in rendered
    assert "Sessions | 1" in rendered


def test_ai_evidence_appendix_with_seat_plan(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)
    (tmp_path / "ai-plans.toml").write_text(
        """
[[plan]]
slug = "claude-max"
tool = "claude-code"
billing = "seat"
monthly_usd = 200
allocation = "active_minutes"
starts_on = "2026-01-01"
"""
    )
    append_session(tmp_path, _ai_session(cost=0.0))

    result = runner.invoke(app, ["invoice", "acme", "--period", "2026-05", "--include-ai-evidence"])

    assert result.exit_code == 0, result.output
    rendered = (tmp_path / "invoices" / "2026-05-001-acme.md").read_text()
    assert "Allocated plans" in rendered
    assert "subscription plan allocation" in rendered
    assert "Allocated costs are estimates" in rendered


def test_ai_evidence_appendix_no_trust_note_for_all_direct(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)
    append_session(tmp_path, _ai_session(cost=1.00))

    result = runner.invoke(app, ["invoice", "acme", "--period", "2026-05", "--include-ai-evidence"])

    assert result.exit_code == 0, result.output
    rendered = (tmp_path / "invoices" / "2026-05-001-acme.md").read_text()
    assert "Allocated costs are estimates" not in rendered


def test_ai_evidence_appendix_dry_run(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)
    append_session(tmp_path, _ai_session(cost=2.00))

    result = runner.invoke(
        app,
        ["invoice", "acme", "--period", "2026-05", "--include-ai-evidence", "--dry-run"],
    )

    assert result.exit_code == 0, result.output
    assert "## AI Usage Evidence" in result.output
    assert "Direct API" in result.output


# ---------------------------------------------------------------------------
# Edge-case tests (task 4.5)
# ---------------------------------------------------------------------------


def test_generate_invoice_unknown_client(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)

    result = runner.invoke(app, ["invoice", "unknown-client", "--period", "2026-05"])

    assert result.exit_code == 1
    assert "not found in clients.toml" in result.output


def test_generate_invoice_no_time_entries(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)
    (tmp_path / "time.timeclock").write_text("; empty\n")

    result = runner.invoke(app, ["invoice", "acme", "--period", "2026-05"])

    assert result.exit_code == 1
    assert "No closed time entries found" in result.output


def test_generate_invoice_open_entries_warning(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)
    # Append an open entry (no matching clock-out) inside the billing period
    with (tmp_path / "time.timeclock").open("a") as f:
        f.write("i 2026-05-07 09:00:00 acme:auth\n")

    result = runner.invoke(app, ["invoice", "acme", "--period", "2026-05"])

    assert result.exit_code == 0, result.output
    assert "open time entries" in result.output


def test_generate_invoice_existing_file_no_force(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)
    runner.invoke(app, ["invoice", "acme", "--period", "2026-05"])

    result = runner.invoke(app, ["invoice", "acme", "--period", "2026-05"])

    assert result.exit_code == 1
    assert "already exists" in result.output


def test_generate_invoice_existing_file_force(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)
    runner.invoke(app, ["invoice", "acme", "--period", "2026-05"])

    result = runner.invoke(app, ["invoice", "acme", "--period", "2026-05", "--force"])

    assert result.exit_code == 0, result.output
    invoice_path = tmp_path / "invoices" / "2026-05-001-acme.md"
    assert invoice_path.exists()


def test_generate_invoice_ai_cost_line_item(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)
    (tmp_path / "halyard.toml").write_text(
        """
[business]
name = "Test Consulting"
currency = "USD"
default_due_days = 30

[invoicing]
counter = 0
include_ai_cost_in_invoice = true
"""
    )
    append_session(tmp_path, _ai_session(cost=5.00))

    result = runner.invoke(app, ["invoice", "acme", "--period", "2026-05"])

    assert result.exit_code == 0, result.output
    rendered = (tmp_path / "invoices" / "2026-05-001-acme.md").read_text()
    assert "AI usage cost" in rendered


def test_render_ai_evidence_appendix_golden(tmp_path: Path) -> None:
    """Golden assertions: verify the full appendix structure with known inputs."""
    from halyard.invoicing import render_ai_evidence_appendix

    sessions = [
        AiSession(
            start=datetime(2026, 5, 6, 10, 0),
            end=datetime(2026, 5, 6, 10, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=2000,
            output_tokens=800,
            cost_usd=4.00,
            project="acme:auth",
        ),
        AiSession(
            start=datetime(2026, 5, 7, 14, 0),
            end=datetime(2026, 5, 7, 14, 45),
            tool="cursor",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=300,
            cost_usd=1.50,
            project="acme:auth",
        ),
    ]

    appendix = render_ai_evidence_appendix(sessions, [], [], "May 2026")

    assert "## AI Usage Evidence" in appendix
    assert "**Period:** May 2026" in appendix
    assert "claude-code" in appendix
    assert "cursor" in appendix
    assert "claude-sonnet-4-6" in appendix
    assert "gpt-4o" in appendix
    assert "Sessions | 2" in appendix
    assert "Input tokens | 3,000" in appendix
    assert "Output tokens | 1,100" in appendix
    assert "Direct API" in appendix
    assert "$5.5000" in appendix
    assert "**Total AI cost**" in appendix


# ---------------------------------------------------------------------------
# Rate history tests
# ---------------------------------------------------------------------------


def test_effective_rate_no_history_returns_default() -> None:
    client = ClientRecord(slug="acme", name="Acme", hourly_rate=150.0)
    assert _effective_rate(client, date(2026, 1, 15)) == 150.0


def test_effective_rate_picks_most_recent_before_date() -> None:
    client = ClientRecord(
        slug="acme",
        name="Acme",
        hourly_rate=175.0,
        rate_history=(
            (date(2025, 1, 1), 120.0),
            (date(2026, 1, 1), 150.0),
            (date(2026, 6, 1), 175.0),
        ),
    )
    assert _effective_rate(client, date(2026, 3, 1)) == 150.0


def test_effective_rate_all_future_falls_back_to_default() -> None:
    client = ClientRecord(
        slug="acme",
        name="Acme",
        hourly_rate=100.0,
        rate_history=((date(2027, 1, 1), 200.0),),
    )
    assert _effective_rate(client, date(2026, 1, 1)) == 100.0


def test_effective_rate_exact_effective_date_is_inclusive() -> None:
    client = ClientRecord(
        slug="acme",
        name="Acme",
        hourly_rate=100.0,
        rate_history=((date(2026, 3, 1), 175.0),),
    )
    assert _effective_rate(client, date(2026, 3, 1)) == 175.0


def test_read_clients_parses_rate_history(tmp_path: Path) -> None:
    from halyard.invoicing import _read_clients

    (tmp_path / "clients.toml").write_text(
        '[[client]]\nslug = "acme"\nname = "Acme"\nhourly_rate = 175.0\n\n'
        '[[client.rate_history]]\nrate = 150.0\neffective = "2026-01-01"\n\n'
        '[[client.rate_history]]\nrate = 175.0\neffective = "2026-06-01"\n'
    )
    clients = _read_clients(tmp_path)
    assert len(clients["acme"].rate_history) == 2
    assert clients["acme"].rate_history[0] == (date(2026, 1, 1), 150.0)
    assert clients["acme"].rate_history[1] == (date(2026, 6, 1), 175.0)


# ---------------------------------------------------------------------------
# M-3: Invoice slug validation (path traversal prevention)
# ---------------------------------------------------------------------------


def test_read_clients_rejects_traversal_slug(tmp_path: Path) -> None:
    """A client slug containing path traversal characters must be rejected."""
    from halyard.invoicing import _read_clients

    (tmp_path / "clients.toml").write_text(
        '[[client]]\nslug = "../../evil"\nname = "Evil"\nhourly_rate = 100\n'
    )
    clients = _read_clients(tmp_path)
    assert "../../evil" not in clients
    assert len(clients) == 0


def test_read_clients_rejects_slug_with_spaces(tmp_path: Path) -> None:
    from halyard.invoicing import _read_clients

    (tmp_path / "clients.toml").write_text(
        '[[client]]\nslug = "bad slug"\nname = "Bad"\nhourly_rate = 100\n'
    )
    clients = _read_clients(tmp_path)
    assert len(clients) == 0


def test_read_clients_accepts_valid_slug(tmp_path: Path) -> None:
    from halyard.invoicing import _read_clients

    (tmp_path / "clients.toml").write_text(
        '[[client]]\nslug = "acme-corp"\nname = "Acme Corp"\nhourly_rate = 100\n'
    )
    clients = _read_clients(tmp_path)
    assert "acme-corp" in clients


def test_read_projects_rejects_traversal_slug(tmp_path: Path) -> None:
    """A project slug containing path traversal characters must be rejected."""
    from halyard.invoicing import _read_projects

    (tmp_path / "projects.toml").write_text(
        '[[project]]\nslug = "../evil"\nclient_slug = "acme"\nname = "Evil"\n'
    )
    projects = _read_projects(tmp_path)
    assert "../evil" not in projects
    assert len(projects) == 0


def test_read_projects_rejects_traversal_client_slug(tmp_path: Path) -> None:
    """A client_slug containing path traversal characters must be rejected."""
    from halyard.invoicing import _read_projects

    (tmp_path / "projects.toml").write_text(
        '[[project]]\nslug = "auth"\nclient_slug = "../../etc"\nname = "Auth"\n'
    )
    projects = _read_projects(tmp_path)
    assert len(projects) == 0


# ---------------------------------------------------------------------------
# M-4: Invoice path confinement
# ---------------------------------------------------------------------------


def test_generate_invoice_path_confined_to_invoices_dir(
    tmp_path: Path, monkeypatch: object
) -> None:
    """A valid client slug must produce an invoice path inside invoices/."""
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)

    from halyard.invoicing import generate_invoice

    result = generate_invoice(
        "acme",
        project_slug=None,
        period="2026-05",
        project_dir=tmp_path,
    )
    assert result.path is not None
    invoice_dir = (tmp_path / "invoices").resolve()
    assert result.path.resolve().is_relative_to(invoice_dir)
