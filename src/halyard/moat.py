"""Moat rollups — project/client + $ + confidence + outcome views.

These are the views no single-tool dashboard can draw because none of
them have a project, a client, a dollar, an attribution provenance, or
an outcome. Pure read layer over data Halyard already captures plus
the v2.65 attribution confidence. No new capture, no writes.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from halyard.ai_log import AiSession
from halyard.attribution import AttributionConfidence, attribution_confidence

_ADRIFT = "(adrift)"


def link_repo_command(remote: str) -> str:
    """The single source of the adrift-remote remediation command.

    Shared by `halyard doctor` and the moat leakage funnel so the two
    never diverge. Proposes — never run automatically.
    """
    from halyard.git_context import _extract_repo_name

    repo = _extract_repo_name(remote) or "project"
    return f"halyard link-repo client:{repo} --remote {remote}"


def _week_start(d: datetime) -> date:
    day = d.date()
    return day - timedelta(days=day.weekday())  # Monday


# --- #1 cost-by-client over time -----------------------------------------


@dataclass(frozen=True)
class ClientCostPoint:
    period: date  # week-start (Monday)
    project: str  # client:project, or "(adrift)"
    cost_usd: float


def cost_by_client(sessions: list[AiSession]) -> list[ClientCostPoint]:
    agg: dict[tuple[date, str], float] = defaultdict(float)
    for s in sessions:
        agg[(_week_start(s.start), s.project or _ADRIFT)] += s.cost_usd
    return [
        ClientCostPoint(period=p, project=proj, cost_usd=round(c, 4))
        for (p, proj), c in sorted(agg.items(), key=lambda kv: (kv[0][0], kv[0][1]))
    ]


# --- #2 attribution-confidence trend -------------------------------------


@dataclass(frozen=True)
class ConfidencePoint:
    period: date
    band: AttributionConfidence
    sessions: int


def confidence_trend(sessions: list[AiSession]) -> list[ConfidencePoint]:
    agg: Counter[tuple[date, AttributionConfidence]] = Counter()
    for s in sessions:
        agg[(_week_start(s.start), attribution_confidence(s))] += 1
    return [
        ConfidencePoint(period=p, band=b, sessions=n)
        for (p, b), n in sorted(agg.items(), key=lambda kv: (kv[0][0], kv[0][1]))
    ]


# --- #3 per-project billable-evidence ------------------------------------


@dataclass(frozen=True)
class ProjectEvidence:
    project: str
    human_minutes: int | None
    ai_cost_usd: float
    sessions: int
    shipped: int
    in_flight: int
    abandoned: int
    no_pr: int
    confidence: AttributionConfidence


def _human_minutes_by_project(project_dir: Path | None) -> dict[str, int]:
    if project_dir is None:
        return {}
    try:
        from halyard.reports import build_human_time_report

        rep = build_human_time_report(project_dir)
    except (OSError, ValueError):
        return {}
    return {b.label: b.minutes for b in rep.by_project}


def project_evidence(
    sessions: list[AiSession], project_dir: Path | None = None
) -> list[ProjectEvidence]:
    by_proj: dict[str, list[AiSession]] = defaultdict(list)
    for s in sessions:
        if s.project:  # adrift is the leakage funnel's job, not a project card
            by_proj[s.project].append(s)

    human = _human_minutes_by_project(project_dir)
    out: list[ProjectEvidence] = []
    for proj, rows in sorted(by_proj.items()):
        states = Counter((r.pr_state or "none") for r in rows)
        band = Counter(attribution_confidence(r) for r in rows).most_common(1)[0][0]
        out.append(
            ProjectEvidence(
                project=proj,
                human_minutes=human.get(proj),
                ai_cost_usd=round(sum(r.cost_usd for r in rows), 4),
                sessions=len(rows),
                shipped=states.get("merged", 0),
                in_flight=states.get("open", 0),
                abandoned=states.get("closed", 0),
                no_pr=len(rows)
                - states.get("merged", 0)
                - states.get("open", 0)
                - states.get("closed", 0),
                confidence=band,
            )
        )
    out.sort(key=lambda e: e.ai_cost_usd, reverse=True)
    return out


# --- #4 leakage funnel ----------------------------------------------------


@dataclass(frozen=True)
class LeakRow:
    remote: str
    sessions: int
    cost_usd: float
    fix_command: str


def leakage(unattributed_log: Path) -> list[LeakRow]:
    """Adrift sessions grouped by remote, each with its one-command fix.

    Read-only: parses the log, proposes the fix, writes nothing.
    """
    if not unattributed_log.exists():
        return []
    agg: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))
    try:
        for raw in unattributed_log.read_text(encoding="utf-8").splitlines():
            if not raw.strip().startswith("s "):
                continue
            s = AiSession.from_log_line(raw)
            if s is None:
                continue
            remote = s.remote or "(no git remote)"
            n, c = agg[remote]
            agg[remote] = (n + 1, c + s.cost_usd)
    except OSError:
        return []
    rows = [
        LeakRow(
            remote=remote,
            sessions=n,
            cost_usd=round(c, 4),
            fix_command=link_repo_command(remote),
        )
        for remote, (n, c) in agg.items()
    ]
    rows.sort(key=lambda r: r.cost_usd, reverse=True)
    return rows
