"""Regression tests for v5.17 invoicing audit blockers B15 and B16.

B15 (HIGH) — zero rate treated as missing -> over-billing.
    The rate selection used an ``or`` chain, so a legitimate 0.0 (a comp/free
    invoice ``rate_override=0.0`` or a project with ``hourly_rate=0.0``) was
    falsy and fell through to a non-zero fallback, billing the client.

B16 (HIGH) — month-boundary mis-allocation.
    Sessions are selected by ``end`` (half-open ``period_start<=end<period_end``)
    but the appendix derived the ledger month from ``min(s.start)``. A session
    that starts on the last day of the prior month but ends in the invoice month
    ran the ledger for the wrong month (wrong period label, wrong
    ``AiPlan.is_active_in``).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from typer.testing import CliRunner

from halyard.ai_log import AiSession
from halyard.ai_plans import AiPlan
from halyard.cli import app
from halyard.invoicing import render_ai_evidence_appendix

runner = CliRunner()


# ---------------------------------------------------------------------------
# Shared project scaffolding for the CLI-level B15 tests.
# ---------------------------------------------------------------------------


def _write_project(tmp_path: Path, *, project_rate_line: str = "") -> None:
    (tmp_path / "halyard.toml").write_text(
        '[business]\nname = "Vendor"\ncurrency = "USD"\n', encoding="utf-8"
    )
    (tmp_path / "clients.toml").write_text(
        '[[client]]\nslug = "acme"\nname = "Acme"\nhourly_rate = 100\n',
        encoding="utf-8",
    )
    (tmp_path / "projects.toml").write_text(
        '[[project]]\nslug = "auth"\nclient_slug = "acme"\nname = "Auth"\n' + project_rate_line,
        encoding="utf-8",
    )
    (tmp_path / "time.timeclock").write_text(
        "i 2026-05-06 10:00:00 acme:auth\no 2026-05-06 12:00:00\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# B15 — zero rate must bill zero, not fall through to a non-zero fallback.
# ---------------------------------------------------------------------------


def test_b15_rate_override_zero_bills_zero(tmp_path: Path) -> None:
    """A comp/free invoice (rate_override=0.0) must total $0, not the client rate."""
    from halyard.invoicing import generate_invoice

    _write_project(tmp_path)  # client hourly_rate = 100 (the buggy fallback)
    result = generate_invoice(
        "acme",
        project_slug=None,
        period="2026-05",
        project_dir=tmp_path,
        rate_override=0.0,
        dry_run=True,
    )
    # 2h logged. Buggy code billed 2 * 100 = 200.00; the comp rate must win.
    assert result.total == 0.0
    assert "USD 0.00" in result.rendered


def test_b15_project_rate_zero_bills_zero(tmp_path: Path) -> None:
    """A project with hourly_rate = 0.0 must bill zero, not the client fallback."""
    from halyard.invoicing import generate_invoice

    _write_project(tmp_path, project_rate_line="hourly_rate = 0.0\n")
    result = generate_invoice(
        "acme",
        project_slug=None,
        period="2026-05",
        project_dir=tmp_path,
        dry_run=True,
    )
    # Buggy code skipped the falsy 0.0 project rate and billed 2 * 100 = 200.00.
    assert result.total == 0.0
    assert "USD 0.00" in result.rendered


def test_b15_benign_nonzero_rate_still_bills(tmp_path: Path, monkeypatch: object) -> None:
    """Guard against over-restriction: a normal non-zero rate still bills."""
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _write_project(tmp_path, project_rate_line="hourly_rate = 150.0\n")
    result = runner.invoke(app, ["invoice", "acme", "--period", "2026-05", "--dry-run"])
    assert result.exit_code == 0, result.output
    # 2h * 150 = 300.00 — project rate takes precedence over the client rate.
    assert "USD 300.00" in result.output


def test_b15_falls_through_to_client_rate_when_no_override(
    tmp_path: Path, monkeypatch: object
) -> None:
    """No override and no project rate -> client rate (the legitimate fallback)."""
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _write_project(tmp_path)  # project has no hourly_rate line
    result = runner.invoke(app, ["invoice", "acme", "--period", "2026-05", "--dry-run"])
    assert result.exit_code == 0, result.output
    # 2h * 100 (client rate) = 200.00
    assert "USD 200.00" in result.output


# ---------------------------------------------------------------------------
# B16 — appendix ledger month must follow the invoice period, not min(start).
# ---------------------------------------------------------------------------


def _straddling_session() -> AiSession:
    # Starts 2026-04-30 23:50, ends 2026-05-01 00:30 -> belongs to the May
    # invoice because selection is by `end`. min(start) is April.
    return AiSession(
        start=datetime(2026, 4, 30, 23, 50),
        end=datetime(2026, 5, 1, 0, 30),
        tool="claude",
        model="opus",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=0.0,
        billing="seat",
    )


def _plan_ending_in_april() -> AiPlan:
    # Active in April, inactive in May (ends_on April 30).
    return AiPlan(
        slug="max",
        tool="claude",
        billing="seat",
        monthly_usd=200.0,
        allocation="active_minutes",
        ends_on=date(2026, 4, 30),
    )


def test_b16_pinned_period_excludes_expired_plan(tmp_path: Path) -> None:
    """For a May invoice, an April-only plan must not allocate cost.

    Without the fix the ledger ran for April (min start), the plan was active,
    and $200 of allocated subscription cost wrongly appeared on the May invoice.
    """
    appendix = render_ai_evidence_appendix(
        [_straddling_session()],
        [_plan_ending_in_april()],
        [],
        "May 2026",
        ledger_year=2026,
        ledger_month=5,
    )
    assert "$0.0000" in appendix
    assert "Allocated plans" not in appendix


def test_b16_unpinned_legacy_caller_still_uses_min_start(tmp_path: Path) -> None:
    """Guard against over-restriction: callers that omit the pin keep the old
    min(start) behaviour (e.g. the evidence-artifact caller passing 'All time')."""
    appendix = render_ai_evidence_appendix(
        [_straddling_session()],
        [_plan_ending_in_april()],
        [],
        "May 2026",
    )
    # min(start) = April -> plan still active -> allocation present.
    assert "Allocated plans" in appendix
    assert "$200.0000" in appendix


def test_b16_pinned_active_plan_still_allocates(tmp_path: Path) -> None:
    """Benign case: a plan active in the pinned month allocates normally."""
    plan_active_in_may = AiPlan(
        slug="max",
        tool="claude",
        billing="seat",
        monthly_usd=200.0,
        allocation="active_minutes",
        ends_on=date(2026, 5, 31),
    )
    appendix = render_ai_evidence_appendix(
        [_straddling_session()],
        [plan_active_in_may],
        [],
        "May 2026",
        ledger_year=2026,
        ledger_month=5,
    )
    assert "Allocated plans" in appendix
    assert "$200.0000" in appendix
