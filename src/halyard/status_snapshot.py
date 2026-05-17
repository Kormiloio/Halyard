"""v2.74 — Ambient Status snapshot.

One read-only object composed *entirely* from existing builders
(doctor / report aggregation / budgets / leakage). Zero new captured
data: this never reads provider credentials, cookies, or keychains —
only Halyard's own plain-text files, via the same aggregator the
dashboard and `report` use (single source of truth).

The budget projection is the on-mission reframe of CodexBar's
"when does my quota reset": at the current run-rate, when do you hit
the budget *you* set. It is always an estimate and labeled as one.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import datetime

from halyard.ai_log import (
    AiSession,
    parse_sessions,
    unattributed_log_count,
    unattributed_log_path,
)
from halyard.budget import budget_status
from halyard.doctor import build_doctor_report, has_errors
from halyard.moat import leakage
from halyard.reports import (
    _dedup_sessions,
    aggregate_session_dirs,
    summarize_ai_sessions,
)
from halyard.usage import sum_spend

_TOP_CLIENTS = 5


@dataclass(frozen=True)
class ClientSpend:
    slug: str
    month_usd: float


@dataclass(frozen=True)
class CaptureStatus:
    healthy: bool
    hooks: dict[str, str]
    minutes_since_last_capture: int | None


@dataclass(frozen=True)
class SpendStatus:
    today_usd: float
    month_usd: float
    by_client: list[ClientSpend]


@dataclass(frozen=True)
class AdriftStatus:
    count: int
    usd: float


@dataclass(frozen=True)
class BudgetBurn:
    slug: str
    month_limit_usd: float | None
    month_spend_usd: float
    pct: int
    projected_month_end_usd: float
    days_until_limit: int | None
    estimate: bool = True  # ALWAYS true — a run-rate is never a measurement


@dataclass(frozen=True)
class StatusSnapshot:
    generated_at: datetime
    capture: CaptureStatus
    spend: SpendStatus
    adrift: AdriftStatus
    budgets: list[BudgetBurn] = field(default_factory=list)


def _all_sessions() -> list[AiSession]:
    """The same aggregation the dashboard/report use — registered
    projects + hub, deduped. No provider files touched."""
    merged: list[AiSession] = []
    for d in aggregate_session_dirs():
        merged.extend(parse_sessions(d))
    return _dedup_sessions(merged)


def _capture(now: datetime, sessions: list[AiSession]) -> CaptureStatus:
    report = build_doctor_report()
    hooks = {
        c.id.split(".", 1)[1]: str(c.status) for c in report.checks if c.id.startswith("hook.")
    }
    last_end = max((s.end for s in sessions), default=None)
    mins = None if last_end is None else max(0, int((now - last_end).total_seconds() // 60))
    return CaptureStatus(
        healthy=not has_errors(report),
        hooks=hooks,
        minutes_since_last_capture=mins,
    )


def _spend(now: datetime, sessions: list[AiSession]) -> SpendStatus:
    month_start = datetime(now.year, now.month, 1)
    day_start = datetime(now.year, now.month, now.day)
    today = sum_spend(sessions, period_start=day_start, period_end=now)
    month = sum_spend(sessions, period_start=month_start, period_end=now)
    in_month = [s for s in sessions if month_start <= s.end < now]
    rep = summarize_ai_sessions(in_month, period_label="month")
    by_client = [
        ClientSpend(slug=b.label, month_usd=round(b.cost_usd, 4))
        for b in sorted(rep.by_project, key=lambda b: -b.cost_usd)[:_TOP_CLIENTS]
    ]
    return SpendStatus(today_usd=today, month_usd=month, by_client=by_client)


def _adrift() -> AdriftStatus:
    rows = leakage(unattributed_log_path())
    return AdriftStatus(
        count=unattributed_log_count(),
        usd=round(sum(r.cost_usd for r in rows), 4),
    )


def _budgets(now: datetime) -> list[BudgetBurn]:
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    day_of_month = max(1, now.day)
    out: list[BudgetBurn] = []
    for b in budget_status(now=now):
        mtd = b.month_spend
        limit = b.month_limit
        run_rate = mtd / day_of_month  # >=0; day_of_month>=1
        projected = round(run_rate * days_in_month, 2)
        pct = int(mtd / limit * 100) if limit else 0
        if limit is not None and run_rate > 0:
            days_until = int((limit - mtd) // run_rate)
            days_until = max(0, days_until)
        else:
            days_until = None
        out.append(
            BudgetBurn(
                slug=b.slug,
                month_limit_usd=limit,
                month_spend_usd=round(mtd, 4),
                pct=pct,
                projected_month_end_usd=projected,
                days_until_limit=days_until,
            )
        )
    return out


def build_status_snapshot(now: datetime | None = None) -> StatusSnapshot:
    """Compose the ambient snapshot from existing builders only.

    Pure reader: no file is written; no provider credential/cookie/
    keychain is ever opened — only Halyard's own aggregated log.
    """
    clock = now or datetime.now()
    sessions = _all_sessions()
    return StatusSnapshot(
        generated_at=clock,
        capture=_capture(clock, sessions),
        spend=_spend(clock, sessions),
        adrift=_adrift(),
        budgets=_budgets(clock),
    )
