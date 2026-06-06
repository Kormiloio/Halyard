"""Regression tests for P1 findings from the owner's parallel code review
(2026-06-05) that the multi-agent audit missed or only partially covered.

- Hub ingest float path admitted non-finite values (B1 gap — the audit fix
  only covered the ai_log file parser + usage.sum_spend backstop).
- Invoicing keyed projects by bare slug, so two clients sharing a slug
  collided onto one rate/name.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.cli import app
from halyard.hub_server import _parse_ingest_float
from halyard.invoicing import _read_projects

runner = CliRunner()

# --- Hub ingest: non-finite cost rejected (B1, Hub path) -------------------


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_hub_ingest_rejects_non_finite_cost(bad: float) -> None:
    with pytest.raises(ValueError):
        _parse_ingest_float(bad, "cost_usd")


def test_hub_ingest_accepts_finite_cost() -> None:
    assert _parse_ingest_float(1.5, "cost_usd") == 1.5
    assert _parse_ingest_float(0, "cost_usd") == 0.0  # zero is valid
    with pytest.raises(ValueError):
        _parse_ingest_float(-1.0, "cost_usd")  # negative still rejected


# --- Invoicing: projects keyed by (client_slug, slug) ----------------------


def test_read_projects_keyed_by_client_and_slug(tmp_path: Path) -> None:
    # Two different clients each own a project with the slug "web".
    (tmp_path / "projects.toml").write_text(
        '[[project]]\nslug = "web"\nclient_slug = "acme"\n'
        'name = "Acme Web"\nhourly_rate = 150.0\n'
        '[[project]]\nslug = "web"\nclient_slug = "globex"\n'
        'name = "Globex Web"\nhourly_rate = 220.0\n',
        encoding="utf-8",
    )
    projects = _read_projects(tmp_path)

    # Both survive under fully-qualified keys (bare-slug keying would have
    # dropped one and conflated their rates/names).
    assert set(projects) == {"acme:web", "globex:web"}
    assert projects["acme:web"].hourly_rate == 150.0
    assert projects["acme:web"].name == "Acme Web"
    assert projects["globex:web"].hourly_rate == 220.0
    assert projects["globex:web"].name == "Globex Web"


# --- Invoicing: round the money, not the hours -----------------------------


def test_invoice_rounds_money_not_hours(tmp_path: Path) -> None:
    from halyard.invoicing import generate_invoice

    (tmp_path / "halyard.toml").write_text(
        '[business]\nname = "Vendor"\ncurrency = "USD"\n', encoding="utf-8"
    )
    (tmp_path / "clients.toml").write_text(
        '[[client]]\nslug = "acme"\nname = "Acme"\nhourly_rate = 100\n', encoding="utf-8"
    )
    (tmp_path / "projects.toml").write_text(
        '[[project]]\nslug = "auth"\nclient_slug = "acme"\nname = "Auth"\nhourly_rate = 150.0\n',
        encoding="utf-8",
    )
    # Exactly one minute of work.
    (tmp_path / "time.timeclock").write_text(
        "i 2026-05-06 10:00:00 acme:auth\no 2026-05-06 10:01:00\n", encoding="utf-8"
    )
    result = generate_invoice(
        "acme", project_slug=None, period="2026-05", project_dir=tmp_path, dry_run=True
    )
    # 1 min @ $150/h = exact $2.50. The pre-rounding bug billed 0.02h * 150 = $3.00.
    assert result.total == 2.50


# --- cli_report: ledger fields cannot inject Rich markup -------------------


def test_cli_report_escapes_markup_in_model_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (tmp_path / "time.timeclock").write_text("; t\n", encoding="utf-8")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")
    # A crafted model name with malformed Rich markup ("[/]" with no opener)
    # would raise MarkupError out of console.print and crash `report`.
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 6, 10, 0),
            end=datetime(2026, 5, 6, 11, 0),
            tool="claude-code",
            model="[red]evil[/]",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.01,
        ),
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["report", "--all"])
    assert result.exit_code == 0, result.output  # no MarkupError crash
    # The bracket is rendered literally (escaped), not interpreted as a style.
    assert "[red]evil[/]" in result.output
