"""Org report formatters — Rich tables for the org admin CLI views.

FROZEN — ENTERPRISE EXTRACTION CANDIDATE. This module is scaffolding for
the planned ``halyard-enterprise`` package and is off-limits for new
feature work in OSS Halyard. Bug fixes affecting solo-user paths only.
See CONTRIBUTING.md.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from halyard.org_store import (
    finance_export,
    governance_gaps,
    org_monthly_summary,
    project_monthly_rollup,
    team_monthly_rollup,
    user_monthly_rollup,
)

console = Console()


def _usd(value: float | None) -> str:
    if value is None or value == 0:
        return "$0.00"
    return f"${value:,.2f}"


def _period_label(year: int, month: int) -> str:
    import calendar

    return f"{calendar.month_abbr[month]} {year}"


# ---------------------------------------------------------------------------
# Executive overview
# ---------------------------------------------------------------------------


def print_org_summary(db_path: Path, org_id: str, year: int, month: int) -> None:
    data = org_monthly_summary(db_path, org_id, year, month)
    period = _period_label(year, month)

    total = data.get("total_usd") or 0.0
    direct = data.get("direct_usd") or 0.0
    alloc = data.get("allocated_usd") or 0.0

    cost_str = (
        f"{_usd(total)} (captured {_usd(direct)}, allocated {_usd(alloc)})"
        if direct > 0 and alloc > 0
        else _usd(total)
    )

    console.print(
        Panel(
            f"[bold]Org:[/] {org_id}   [bold]Period:[/] {period}\n"
            f"Sessions: {data.get('sessions', 0):,}   "
            f"Active users: {data.get('active_users', 0)}   "
            f"Active teams: {data.get('active_teams', 0)}\n"
            f"AI spend: {cost_str}\n"
            f"Unattributed sessions: {data.get('unattributed', 0)}",
            title="Org Overview",
            border_style="cyan",
        )
    )

    tool_mix = data.get("tool_mix", [])
    if tool_mix:
        t = Table("Tool", "Sessions", box=None, padding=(0, 2))
        for row in tool_mix:
            t.add_row(row["tool"], str(row["sessions"]))
        console.print(t)

    model_mix = data.get("model_mix", [])
    if model_mix:
        t = Table("Model", "Sessions", "Direct cost", box=None, padding=(0, 2))
        for row in model_mix:
            t.add_row(row["model"], str(row["sessions"]), _usd(row.get("direct_usd")))
        console.print(t)


# ---------------------------------------------------------------------------
# Team rollup
# ---------------------------------------------------------------------------


def print_team_rollup(
    db_path: Path, org_id: str, year: int, month: int, team_id: str | None = None
) -> None:
    rows = team_monthly_rollup(db_path, org_id, year, month, team_id)
    period = _period_label(year, month)

    if not rows:
        console.print(f"[yellow]No sessions found for {period}.[/]")
        return

    t = Table(
        "Team",
        "Sessions",
        "Users",
        "Direct",
        "Allocated",
        "Total",
        "Unattributed",
        title=f"Team Rollup — {period}",
        box=None,
        padding=(0, 2),
    )
    for r in rows:
        unattr = r.get("unattributed", 0) or 0
        flag = f"[yellow]{unattr}[/]" if unattr > 0 else "0"
        t.add_row(
            r["team_id"],
            str(r["sessions"]),
            str(r["active_users"]),
            _usd(r.get("direct_usd")),
            _usd(r.get("allocated_usd")),
            _usd(r.get("total_usd")),
            flag,
        )
    console.print(t)


# ---------------------------------------------------------------------------
# Project rollup
# ---------------------------------------------------------------------------


def print_project_rollup(
    db_path: Path,
    org_id: str,
    year: int,
    month: int,
    project_id: str | None = None,
    team_id: str | None = None,
) -> None:
    rows = project_monthly_rollup(db_path, org_id, year, month, project_id, team_id)
    period = _period_label(year, month)

    if not rows:
        console.print(f"[yellow]No attributed sessions found for {period}.[/]")
        return

    t = Table(
        "Project",
        "Team",
        "Sessions",
        "Contributors",
        "Direct",
        "Allocated",
        "Total",
        "Inferred",
        title=f"Project Rollup — {period}",
        box=None,
        padding=(0, 2),
    )
    for r in rows:
        inf = r.get("inferred_sessions", 0) or 0
        inf_str = f"[dim]{inf}[/]" if inf > 0 else "0"
        t.add_row(
            r["project_id"] or "(unattributed)",
            r["team_id"],
            str(r["sessions"]),
            str(r["contributors"]),
            _usd(r.get("direct_usd")),
            _usd(r.get("allocated_usd")),
            _usd(r.get("total_usd")),
            inf_str,
        )
    console.print(t)


# ---------------------------------------------------------------------------
# People / adoption view
# ---------------------------------------------------------------------------


def print_people_rollup(
    db_path: Path, org_id: str, year: int, month: int, team_id: str | None = None
) -> None:
    rows = user_monthly_rollup(db_path, org_id, year, month, team_id)
    period = _period_label(year, month)

    if not rows:
        console.print(f"[yellow]No user activity found for {period}.[/]")
        return

    t = Table(
        "User",
        "Team",
        "Sessions",
        "Active days",
        "Tools",
        "Total cost",
        title=f"People — {period}",
        box=None,
        padding=(0, 2),
    )
    for r in rows:
        t.add_row(
            r["user_id"],
            r["team_id"],
            str(r["sessions"]),
            str(r["active_days"]),
            r.get("tools") or "",
            _usd(r.get("total_usd")),
        )
    console.print(t)


# ---------------------------------------------------------------------------
# Governance
# ---------------------------------------------------------------------------


def print_governance(
    db_path: Path,
    org_id: str,
    year: int,
    month: int,
    unattributed_threshold: float = 0.10,
) -> None:
    data = governance_gaps(db_path, org_id, year, month, unattributed_threshold)
    period = _period_label(year, month)
    alerts = data.get("alerts", [])

    if not alerts:
        console.print(f"[green]No governance alerts for {period}.[/]")
        return

    console.print(f"[bold red]Governance alerts — {period}[/]")
    for a in alerts:
        if a["type"] == "unattributed_rate":
            pct = f"{a['rate'] * 100:.0f}%"
            console.print(
                f"  [yellow]●[/] {a['team_id']}: {pct} unattributed "
                f"({a['unattributed']}/{a['total']} sessions)"
            )
        elif a["type"] == "missing_cost":
            console.print(f"  [red]●[/] {a['team_id']}: {a['count']} sessions with no cost data")


# ---------------------------------------------------------------------------
# Finance export
# ---------------------------------------------------------------------------


def _enrich_cost_centers(rows: list[dict], hub_dir: Path | None) -> list[dict]:  # type: ignore[type-arg]
    """Attach cost_center to each finance row using hub config files."""
    if hub_dir is None:
        for r in rows:
            r.setdefault("cost_center", "")
        return rows
    from halyard.cost_centers import (
        read_cost_center_config,
        read_project_cost_centers,
        resolve_cost_center,
    )

    org_cc = read_cost_center_config(hub_dir)
    project_overrides = read_project_cost_centers(hub_dir)
    for r in rows:
        r["cost_center"] = resolve_cost_center(
            r.get("project_id", ""),
            r.get("team_id", ""),
            project_overrides=project_overrides,
            org_config=org_cc,
        )
    return rows


def print_finance_table(
    db_path: Path, org_id: str, year: int, month: int, hub_dir: Path | None = None
) -> None:
    rows = _enrich_cost_centers(finance_export(db_path, org_id, year, month), hub_dir)
    period = _period_label(year, month)

    if not rows:
        console.print(f"[yellow]No data for {period}.[/]")
        return

    t = Table(
        "Cost center",
        "Team",
        "Project",
        "Tool",
        "Sessions",
        "Direct",
        "Allocated",
        "Total",
        "Trust",
        title=f"Finance Export — {period}",
        box=None,
        padding=(0, 2),
    )
    for r in rows:
        t.add_row(
            r.get("cost_center") or "",
            r["team_id"],
            r["project_id"] or "(unattributed)",
            r["tool"],
            str(r["sessions"]),
            _usd(r.get("direct_usd")),
            _usd(r.get("allocated_usd")),
            _usd(r.get("total_usd")),
            r.get("trust", ""),
        )
    console.print(t)


def export_finance_csv(
    db_path: Path, org_id: str, year: int, month: int, hub_dir: Path | None = None
) -> str:
    """Return a well-formed CSV string of the finance export rows."""
    rows = _enrich_cost_centers(finance_export(db_path, org_id, year, month), hub_dir)
    if not rows:
        return ""

    fieldnames = [
        "billing_period",
        "org_id",
        "cost_center",
        "team_id",
        "project_id",
        "tool",
        "sessions",
        "direct_usd",
        "allocated_usd",
        "total_usd",
        "trust",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()
