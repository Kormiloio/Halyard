"""Tests for v2.15 — transaction history and invoice audit."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.cli import app
from halyard.config_history import (
    RateChange,
    _parse_invoice_rates,
    audit_invoices,
    rate_history_from_toml,
)

runner = CliRunner()

_CLIENTS_TOML_WITH_HISTORY = """\
[[client]]
slug = "acme"
name = "Acme Corp"
hourly_rate = 200

[[client.rate_history]]
effective = "2025-01-01"
rate = 150

[[client.rate_history]]
effective = "2026-01-01"
rate = 200

[[client]]
slug = "beta"
name = "Beta Inc"
hourly_rate = 120
"""

_INVOICE_MD = """\
---
invoice_number: 2025-06-001-acme
client_slug: acme
issue_date: 2025-07-01
due_date: 2025-07-31
currency: USD
total: 1500.00
---

# Invoice 2025-06-001-acme

## Line items

| Description | Hours | Rate | Amount |
|---|---:|---:|---:|
| Engineering | 10.00 | USD 150.00 | USD 1500.00 |

**Total: USD 1500.00**
"""

_INVOICE_MD_WRONG_RATE = """\
---
invoice_number: 2026-03-001-acme
client_slug: acme
issue_date: 2026-04-01
due_date: 2026-04-30
currency: USD
total: 1500.00
---

# Invoice 2026-03-001-acme

## Line items

| Description | Hours | Rate | Amount |
|---|---:|---:|---:|
| Engineering | 10.00 | USD 150.00 | USD 1500.00 |

**Total: USD 1500.00**
"""


def _setup_project(tmp_path: Path, clients_toml: str = _CLIENTS_TOML_WITH_HISTORY) -> Path:
    (tmp_path / "halyard.toml").write_text("[business]\nname = 'Test'\n")
    (tmp_path / "clients.toml").write_text(clients_toml)
    (tmp_path / "invoices").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# rate_history_from_toml
# ---------------------------------------------------------------------------


def test_rate_history_from_toml_reads_entries(tmp_path: Path) -> None:
    _setup_project(tmp_path)
    changes = rate_history_from_toml(tmp_path)
    assert len(changes) == 2
    assert changes[0] == RateChange("acme", date(2025, 1, 1), 150.0, "rate_history")
    assert changes[1] == RateChange("acme", date(2026, 1, 1), 200.0, "rate_history")


def test_rate_history_from_toml_empty_when_no_history(tmp_path: Path) -> None:
    _setup_project(tmp_path, "[[client]]\nslug = 'acme'\nname = 'A'\nhourly_rate = 150\n")
    changes = rate_history_from_toml(tmp_path)
    assert changes == []


def test_rate_history_from_toml_sorted_by_date(tmp_path: Path) -> None:
    _setup_project(tmp_path)
    changes = rate_history_from_toml(tmp_path)
    dates = [c.effective_date for c in changes]
    assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# _parse_invoice_rates
# ---------------------------------------------------------------------------


def test_parse_invoice_rates_extracts_nonzero_rates() -> None:
    rates = _parse_invoice_rates(_INVOICE_MD)
    assert rates == [150.0]


def test_parse_invoice_rates_skips_zero_rates() -> None:
    md = """\
---
invoice_number: 2026-01-001-acme
client_slug: acme
total: 50.00
---
## Line items

| Description | Hours | Rate | Amount |
|---|---:|---:|---:|
| Engineering | 10.00 | USD 175.00 | USD 1750.00 |
| AI costs | 0.00 | USD 0.00 | USD 50.00 |

**Total: USD 1800.00**
"""
    rates = _parse_invoice_rates(md)
    assert rates == [175.0]


# ---------------------------------------------------------------------------
# audit_invoices
# ---------------------------------------------------------------------------


def test_audit_invoices_clean(tmp_path: Path) -> None:
    _setup_project(tmp_path)
    (tmp_path / "invoices" / "2025-06-001-acme.md").write_text(_INVOICE_MD)
    mismatches = audit_invoices(tmp_path)
    assert mismatches == []


def test_audit_invoices_detects_mismatch(tmp_path: Path) -> None:
    _setup_project(tmp_path)
    (tmp_path / "invoices" / "2026-03-001-acme.md").write_text(_INVOICE_MD_WRONG_RATE)
    mismatches = audit_invoices(tmp_path)
    assert len(mismatches) == 1
    m = mismatches[0]
    assert m.client_slug == "acme"
    assert m.period == "2026-03"
    assert m.expected_rate == 200.0
    assert m.actual_rate == 150.0


def test_audit_invoices_client_filter(tmp_path: Path) -> None:
    _setup_project(tmp_path)
    (tmp_path / "invoices" / "2026-03-001-acme.md").write_text(_INVOICE_MD_WRONG_RATE)
    assert audit_invoices(tmp_path, client_filter="beta") == []
    assert len(audit_invoices(tmp_path, client_filter="acme")) == 1


def test_audit_invoices_period_filter(tmp_path: Path) -> None:
    _setup_project(tmp_path)
    (tmp_path / "invoices" / "2026-03-001-acme.md").write_text(_INVOICE_MD_WRONG_RATE)
    assert audit_invoices(tmp_path, period_filter="2026-02") == []
    assert len(audit_invoices(tmp_path, period_filter="2026-03")) == 1


def test_audit_invoices_no_invoices_dir(tmp_path: Path) -> None:
    _setup_project(tmp_path)
    (tmp_path / "invoices").rmdir()
    assert audit_invoices(tmp_path) == []


# ---------------------------------------------------------------------------
# CLI: halyard config history
# ---------------------------------------------------------------------------


def test_config_history_cli_toml_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)
    result = runner.invoke(app, ["config", "history"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "2025-01-01" in result.output
    assert "150.00" in result.output
    assert "2026-01-01" in result.output
    assert "200.00" in result.output


def test_config_history_cli_client_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)
    result = runner.invoke(app, ["config", "history", "--client", "beta"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "No rate history found" in result.output


def test_config_history_cli_no_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path, "[[client]]\nslug = 'acme'\nname = 'A'\nhourly_rate = 150\n")
    result = runner.invoke(app, ["config", "history"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "No rate history found" in result.output


# ---------------------------------------------------------------------------
# CLI: halyard config audit
# ---------------------------------------------------------------------------


def test_config_audit_cli_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)
    (tmp_path / "invoices" / "2025-06-001-acme.md").write_text(_INVOICE_MD)
    result = runner.invoke(app, ["config", "audit"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "Audit clean" in result.output


def test_config_audit_cli_mismatch_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)
    (tmp_path / "invoices" / "2026-03-001-acme.md").write_text(_INVOICE_MD_WRONG_RATE)
    result = runner.invoke(app, ["config", "audit"], catch_exceptions=False)
    assert result.exit_code == 1
    assert "mismatch" in result.output.lower()
    assert "150.00" in result.output
    assert "200.00" in result.output


def test_config_audit_cli_no_invoices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)
    result = runner.invoke(app, ["config", "audit"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "No invoices" in result.output
