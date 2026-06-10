"""AI Work Ledger — cost allocation and attribution.

Joins ai-sessions.log with ai-plans.toml to produce per-project cost summaries
that distinguish captured API cost from allocated seat/credit cost.

Trust labels:
  captured   — cost_usd written directly from API response at capture time
  calculated — cost derived from captured tokens + pricing table
  allocated  — share of a monthly seat or credit plan cost
  inferred   — project attribution guessed from timeclock overlap (not confirmed)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, cast

from halyard.ai_log import AiSession
from halyard.ai_plans import AiPlan
from halyard.usage import round_money

CostTrust = Literal["captured", "calculated", "allocated", "unallocated", "mixed", "inferred"]


def infer_project_attribution(
    session: AiSession,
    timeclock_entries: list[tuple[datetime, datetime, str]],
) -> str | None:
    """Return the inferred project slug from an unambiguous timeclock overlap, or None."""
    overlapping = [
        account
        for tc_start, tc_end, account in timeclock_entries
        if tc_start <= session.end and tc_end >= session.start
    ]
    return overlapping[0] if len(overlapping) == 1 else None


@dataclass(frozen=True)
class LedgerEntry:
    project: str
    sessions: int
    active_minutes: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    direct_usd: float
    allocated_usd: float
    total_usd: float
    trust: CostTrust
    has_inferred_attribution: bool


@dataclass(frozen=True)
class LedgerSummary:
    entries: list[LedgerEntry]
    period_label: str
    total_direct_usd: float
    total_allocated_usd: float
    total_usd: float
    unattributed_count: int


def build_ledger(
    sessions: list[AiSession],
    plans: list[AiPlan],
    timeclock_entries: list[tuple[datetime, datetime, str]],
    *,
    year: int,
    month: int,
) -> LedgerSummary:
    """Allocate costs and produce per-project ledger entries for the given month."""
    period_label = datetime(year, month, 1).strftime("%B %Y")
    active_plans = [p for p in plans if p.is_active_in(year, month)]

    # Resolve attribution: fill in project via timeclock overlap when missing
    resolved = _resolve_attribution(sessions, timeclock_entries)

    # Separate direct-API sessions from seat/credits sessions by plan
    direct_sessions, plan_session_map = _partition_by_plan(resolved, active_plans)

    # Per-project accumulators: {project: {field: value}}
    buckets: dict[str, dict[str, float | int | bool | Decimal]] = {}

    def _bucket(project: str) -> dict[str, float | int | bool | Decimal]:
        return buckets.setdefault(
            project,
            {
                "sessions": 0,
                "active_minutes": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read": 0,
                "cache_write": 0,
                "direct_usd": Decimal(0),
                "allocated_usd": Decimal(0),
                "seat_claimed": 0,
                "has_inferred": False,
            },
        )

    # Direct API sessions
    for sess, inferred in direct_sessions:
        project = sess.project or "(unattributed)"
        b = _bucket(project)
        b["sessions"] = int(b["sessions"]) + 1
        b["active_minutes"] = int(b["active_minutes"]) + _session_minutes(sess)
        b["input_tokens"] = int(b["input_tokens"]) + sess.input_tokens
        b["output_tokens"] = int(b["output_tokens"]) + sess.output_tokens
        b["cache_read"] = int(b["cache_read"]) + (sess.cache_read or 0)
        b["cache_write"] = int(b["cache_write"]) + (sess.cache_write or 0)
        b["direct_usd"] = cast(Decimal, b["direct_usd"]) + Decimal(str(sess.cost_usd))
        if inferred:
            b["has_inferred"] = True

    # Seat / credits sessions with allocation
    for plan, plan_sessions in plan_session_map.items():
        allocated = _allocate_plan_cost(plan, plan_sessions, year, month)
        for sess, inferred, project_alloc in allocated:
            project = sess.project or "(unattributed)"
            b = _bucket(project)
            b["sessions"] = int(b["sessions"]) + 1
            b["active_minutes"] = int(b["active_minutes"]) + _session_minutes(sess)
            b["input_tokens"] = int(b["input_tokens"]) + sess.input_tokens
            b["output_tokens"] = int(b["output_tokens"]) + sess.output_tokens
            b["cache_read"] = int(b["cache_read"]) + (sess.cache_read or 0)
            b["cache_write"] = int(b["cache_write"]) + (sess.cache_write or 0)
            b["allocated_usd"] = cast(Decimal, b["allocated_usd"]) + Decimal(str(project_alloc))
            b["seat_claimed"] = int(b["seat_claimed"]) + 1
            if inferred:
                b["has_inferred"] = True

    entries = [
        LedgerEntry(
            project=project,
            sessions=int(b["sessions"]),
            active_minutes=int(b["active_minutes"]),
            input_tokens=int(b["input_tokens"]),
            output_tokens=int(b["output_tokens"]),
            cache_read_tokens=int(b["cache_read"]),
            cache_write_tokens=int(b["cache_write"]),
            direct_usd=round_money(float(b["direct_usd"]), 4),
            allocated_usd=round_money(float(b["allocated_usd"]), 4),
            total_usd=round_money(
                float(cast(Decimal, b["direct_usd"]) + cast(Decimal, b["allocated_usd"])), 4
            ),
            trust=_trust_label(
                float(b["direct_usd"]), float(b["allocated_usd"]), int(b["seat_claimed"])
            ),
            has_inferred_attribution=bool(b["has_inferred"]),
        )
        for project, b in sorted(
            buckets.items(),
            key=lambda item: (
                -(
                    float(
                        cast(Decimal, item[1]["direct_usd"])
                        + cast(Decimal, item[1]["allocated_usd"])
                    )
                )
            ),
        )
    ]

    unattributed = sum(1 for e in entries if e.project == "(unattributed)")
    total_direct = round_money(sum(e.direct_usd for e in entries), 4)
    total_allocated = round_money(sum(e.allocated_usd for e in entries), 4)

    return LedgerSummary(
        entries=entries,
        period_label=period_label,
        total_direct_usd=total_direct,
        total_allocated_usd=total_allocated,
        total_usd=round_money(total_direct + total_allocated, 4),
        unattributed_count=unattributed,
    )


def build_aggregated_ledger(
    sessions: list[AiSession],
    plans: list[AiPlan],
    timeclock_entries: list[tuple[datetime, datetime, str]],
    *,
    period_label: str,
) -> LedgerSummary:
    """Build a multi-month ledger by running :func:`build_ledger` per (year,
    month) and folding the per-month summaries into one.

    Subscription / seat plans charge per *month*, so a single-month
    ``build_ledger`` call against an all-time session set undercounts: a
    $100/month plan with sessions in two months reports $100, not $200. The
    aggregated builder calls ``build_ledger`` once per (year, month) covered
    by ``sessions`` and sums the entries, preserving each month's plan
    attribution (an :class:`AiPlan` only active in some months contributes
    nothing to the others).

    Direct-API costs are per-session, so they sum trivially across months.
    Allocated costs are summed across the per-month allocations.
    """
    if not sessions:
        return LedgerSummary(
            entries=[],
            period_label=period_label,
            total_direct_usd=0.0,
            total_allocated_usd=0.0,
            total_usd=0.0,
            unattributed_count=0,
        )

    # v5.19/B-end-month: bucket by session END, not start. Halyard's billing
    # period selection (`build_filtered_ai_report`, the invoice path) is
    # always done on `end`, so a session that starts Jan 31 23:50 and ends
    # Feb 1 00:10 is February work. Bucketing by `start` here gave it
    # January's plan allocation instead of February's.
    months: dict[tuple[int, int], list[AiSession]] = {}
    for sess in sessions:
        months.setdefault((sess.end.year, sess.end.month), []).append(sess)

    # Per-project numeric accumulators across all months. Trust labels live
    # in their own map so the dict value type stays numeric (mypy keeps
    # `CostTrust` out of the float/int/bool union). We carry the SET of
    # labels we observed per project across months and reduce it to a
    # single label below — first-month-wins was a real bug (Jan captured +
    # Feb allocated kept "captured" instead of promoting to "mixed").
    by_project: dict[str, dict[str, float | int | bool]] = {}
    trust_seen: dict[str, set[CostTrust]] = {}

    def _bucket(project: str) -> dict[str, float | int | bool]:
        return by_project.setdefault(
            project,
            {
                "sessions": 0,
                "active_minutes": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read": 0,
                "cache_write": 0,
                "direct_usd": 0.0,
                "allocated_usd": 0.0,
                "has_inferred": False,
            },
        )

    for (year, month), month_sessions in sorted(months.items()):
        monthly = build_ledger(month_sessions, plans, timeclock_entries, year=year, month=month)
        for entry in monthly.entries:
            b = _bucket(entry.project)
            b["sessions"] = int(b["sessions"]) + entry.sessions
            b["active_minutes"] = int(b["active_minutes"]) + entry.active_minutes
            b["input_tokens"] = int(b["input_tokens"]) + entry.input_tokens
            b["output_tokens"] = int(b["output_tokens"]) + entry.output_tokens
            b["cache_read"] = int(b["cache_read"]) + entry.cache_read_tokens
            b["cache_write"] = int(b["cache_write"]) + entry.cache_write_tokens
            b["direct_usd"] = float(b["direct_usd"]) + entry.direct_usd
            b["allocated_usd"] = float(b["allocated_usd"]) + entry.allocated_usd
            if entry.has_inferred_attribution:
                b["has_inferred"] = True
            trust_seen.setdefault(entry.project, set()).add(entry.trust)

    entries = [
        LedgerEntry(
            project=project,
            sessions=int(b["sessions"]),
            active_minutes=int(b["active_minutes"]),
            input_tokens=int(b["input_tokens"]),
            output_tokens=int(b["output_tokens"]),
            cache_read_tokens=int(b["cache_read"]),
            cache_write_tokens=int(b["cache_write"]),
            direct_usd=round_money(float(b["direct_usd"]), 4),
            allocated_usd=round_money(float(b["allocated_usd"]), 4),
            total_usd=round_money(float(b["direct_usd"]) + float(b["allocated_usd"]), 4),
            trust=_merge_trust_labels(
                trust_seen.get(project, {"captured"}),
                float(b["direct_usd"]),
                float(b["allocated_usd"]),
            ),
            has_inferred_attribution=bool(b["has_inferred"]),
        )
        for project, b in sorted(
            by_project.items(),
            key=lambda item: -(float(item[1]["direct_usd"]) + float(item[1]["allocated_usd"])),
        )
    ]
    total_direct = round_money(sum(e.direct_usd for e in entries), 4)
    total_allocated = round_money(sum(e.allocated_usd for e in entries), 4)
    unattributed = sum(1 for e in entries if e.project == "(unattributed)")
    return LedgerSummary(
        entries=entries,
        period_label=period_label,
        total_direct_usd=total_direct,
        total_allocated_usd=total_allocated,
        total_usd=round_money(total_direct + total_allocated, 4),
        unattributed_count=unattributed,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_attribution(
    sessions: list[AiSession],
    timeclock_entries: list[tuple[datetime, datetime, str]],
) -> list[tuple[AiSession, bool]]:
    """Return (session, inferred) pairs. Unattributed sessions get a project
    inferred from an unambiguous overlapping timeclock window."""
    import dataclasses

    result: list[tuple[AiSession, bool]] = []
    for sess in sessions:
        if sess.project:
            result.append((sess, False))
            continue
        inferred = infer_project_attribution(sess, timeclock_entries)
        if inferred is not None:
            result.append((dataclasses.replace(sess, project=inferred), True))
        else:
            result.append((sess, False))
    return result


def _partition_by_plan(
    resolved: list[tuple[AiSession, bool]],
    plans: list[AiPlan],
) -> tuple[
    list[tuple[AiSession, bool]],
    dict[AiPlan, list[tuple[AiSession, bool]]],
]:
    """Split sessions into direct-API and plan-matched groups.

    A session can only be claimed by one plan (first match wins by plan order).
    Sessions not matching any plan fall into direct.
    """
    plan_map: dict[AiPlan, list[tuple[AiSession, bool]]] = {p: [] for p in plans}
    direct: list[tuple[AiSession, bool]] = []

    for sess, inferred in resolved:
        matched = False
        for plan in plans:
            if plan.billing != "api" and plan.tool == sess.tool:
                plan_map[plan].append((sess, inferred))
                matched = True
                break
        if not matched:
            direct.append((sess, inferred))

    # Remove empty plan buckets
    plan_map = {p: slist for p, slist in plan_map.items() if slist}
    return direct, plan_map


def _allocate_plan_cost(
    plan: AiPlan,
    plan_sessions: list[tuple[AiSession, bool]],
    year: int,
    month: int,
) -> list[tuple[AiSession, bool, float]]:
    """Return (session, inferred, allocated_usd) triples for a seat/credits plan."""
    if not plan_sessions:
        return []

    if plan.billing == "credits":
        return _allocate_credits(plan, plan_sessions)

    # seat billing
    monthly_usd = plan.monthly_usd or 0.0
    if monthly_usd == 0.0 or plan.allocation == "manual":
        return [(sess, inf, 0.0) for sess, inf in plan_sessions]

    if plan.allocation in ("active_minutes", "direct"):
        total_minutes = sum(_session_minutes(sess) for sess, _ in plan_sessions) or 1
        return [
            (sess, inf, monthly_usd * _session_minutes(sess) / total_minutes)
            for sess, inf in plan_sessions
        ]

    if plan.allocation == "session_count":
        share = monthly_usd / len(plan_sessions)
        return [(sess, inf, share) for sess, inf in plan_sessions]

    # project_weight and manual: no automatic allocation
    return [(sess, inf, 0.0) for sess, inf in plan_sessions]


def _allocate_credits(
    plan: AiPlan,
    plan_sessions: list[tuple[AiSession, bool]],
) -> list[tuple[AiSession, bool, float]]:
    """Allocate credit cost using session.credits if available, else by minutes."""
    rate = plan.credit_to_usd
    result: list[tuple[AiSession, bool, float]] = []

    for sess, inf in plan_sessions:
        if sess.credits is not None and rate is not None:
            result.append((sess, inf, round_money(sess.credits * rate, 4)))
        elif plan.monthly_usd is not None:
            # Fall back to minute-based allocation if credits field is absent
            result.append((sess, inf, 0.0))
        else:
            result.append((sess, inf, 0.0))

    # If we couldn't use per-session credits, fall back to minute allocation
    if all(cost == 0.0 for _, _, cost in result) and plan.monthly_usd:
        total_minutes = sum(_session_minutes(sess) for sess, _ in plan_sessions) or 1
        result = [
            (sess, inf, plan.monthly_usd * _session_minutes(sess) / total_minutes)
            for sess, inf in plan_sessions
        ]

    return result


def _session_minutes(sess: AiSession) -> int:
    return max(1, int((sess.end - sess.start).total_seconds() // 60))


def _trust_label(direct: float, allocated: float, seat_claimed: int = 0) -> CostTrust:
    if direct > 0 and allocated > 0:
        return "mixed"
    if allocated > 0:
        return "allocated"
    if seat_claimed > 0:
        return "unallocated"
    return "captured"


def _merge_trust_labels(labels: set[CostTrust], direct: float, allocated: float) -> CostTrust:
    """Merge per-month trust labels into a single label for the aggregate.

    v5.19/B-trust-merge: first-month-wins was wrong — a January row with
    captured cost combined with February's allocated subscription stayed
    labelled "captured", erasing the fact that part of the spend was
    estimated. We re-derive from the aggregated totals using the same
    rules as :func:`_trust_label`, with two extra promotions that only
    apply at the aggregate level:

      * Any month already promoted to ``mixed`` keeps that promotion.
      * If captured AND allocated were both seen across months, promote
        to ``mixed`` even when one of the aggregated totals rounded to
        zero (e.g. a $0.0001 captured row should not be lost).

    ``inferred`` is propagated separately via ``has_inferred_attribution``;
    it is a column on the entry, not a trust label.
    """
    if "mixed" in labels:
        return "mixed"
    if direct > 0 and allocated > 0:
        return "mixed"
    has_direct = "captured" in labels or "calculated" in labels
    has_alloc = "allocated" in labels or "unallocated" in labels
    if has_direct and has_alloc:
        return "mixed"
    if allocated > 0 or "allocated" in labels:
        return "allocated"
    if "unallocated" in labels:
        return "unallocated"
    return "captured"
