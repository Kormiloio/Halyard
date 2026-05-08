"""Org-level rollup aggregation for v3 org admin dashboard."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from halyard.ai_log import AiSession
from halyard.cost_centers import CostCenterConfig
from halyard.org import OrgConfig

_UNASSIGNED = "(unassigned)"


def _display_name(org: OrgConfig, email: str) -> str:
    for m in org.members:
        if m.email.lower() == email.lower():
            return m.display_name or email
    return email


def _team_for_user(org: OrgConfig, email: str) -> str:
    _, team_id = org.resolve_user(email)
    return team_id
_UNATTRIBUTED = "(unattributed)"
_UNATTRIBUTED_THRESHOLD = 0.10  # 10% unattributed triggers governance flag


# ---------------------------------------------------------------------------
# Trust derivation
# ---------------------------------------------------------------------------


def session_trust(s: AiSession) -> str:
    """Derive a trust label from a session's billing and cost fields."""
    if s.cost_usd > 0:
        if s.billing == "credits":
            return "allocated"
        return "captured"
    if s.credits is not None and s.credits > 0:
        return "allocated"
    return "missing"


def aggregate_trust(labels: list[str]) -> str:
    """Reduce a list of trust labels to a single aggregate label."""
    unique = set(labels)
    if not unique:
        return "missing"
    if len(unique) == 1:
        return next(iter(unique))
    return "mixed"


# ---------------------------------------------------------------------------
# Rollup data model
# ---------------------------------------------------------------------------


@dataclass
class UserRollup:
    user: str
    display_name: str | None
    team_id: str
    sessions: int
    active_days: int
    tools: dict[str, int]
    total_cost: float
    trust: str


@dataclass
class TeamRollup:
    team_id: str
    team_name: str
    department_id: str | None
    sessions: int
    active_users: int
    total_cost: float
    direct_usd: float
    allocated_usd: float
    trust: str
    unattributed_count: int
    per_project: dict[str, float] = field(default_factory=dict)
    user_rollups: list[UserRollup] = field(default_factory=list)


@dataclass
class ProjectRollup:
    project_id: str
    sessions: int
    total_cost: float
    trust: str
    per_team: dict[str, float] = field(default_factory=dict)


@dataclass
class GovernanceFlag:
    category: str  # unattributed_rate | no_capture | unknown_model
    team_id: str | None
    user: str | None
    detail: str


@dataclass
class FinanceRow:
    billing_period: str
    cost_center: str
    team_id: str
    project_id: str
    tool: str
    sessions: int
    direct_usd: float
    allocated_usd: float
    total_usd: float
    trust: str


@dataclass
class OrgSummary:
    org_name: str
    period: str
    total_sessions: int
    total_cost: float
    active_users: int
    teams: list[TeamRollup]
    projects: list[ProjectRollup]
    trust: str
    governance_flags: list[GovernanceFlag]
    finance_rows: list[FinanceRow]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_org_summary(
    sessions: list[AiSession],
    org: OrgConfig,
    cost_centers: CostCenterConfig,
    period: str,
    known_models: set[str] | None = None,
) -> OrgSummary:
    # --- Resolve user → team for every session ---
    team_sessions: dict[str, list[AiSession]] = defaultdict(list)
    user_sessions: dict[str, list[AiSession]] = defaultdict(list)

    for s in sessions:
        team_id = _team_for_user(org, s.user) if s.user else _UNASSIGNED
        team_sessions[team_id].append(s)
        if s.user:
            user_sessions[s.user].append(s)

    # --- Team rollups ---
    team_rollups: list[TeamRollup] = []
    for team in org.teams:
        t_sessions = team_sessions.get(team.id, [])
        tr = _build_team_rollup(team.id, team.name, team.department_id, t_sessions, org)
        team_rollups.append(tr)

    # Unassigned group (users not in org.toml)
    unassigned_sessions = team_sessions.get(_UNASSIGNED, [])
    if unassigned_sessions:
        tr = _build_team_rollup(
            _UNASSIGNED, _UNASSIGNED, None, unassigned_sessions, org
        )
        team_rollups.append(tr)

    # --- Project rollups ---
    project_map: dict[str, dict[str, list[AiSession]]] = defaultdict(lambda: defaultdict(list))
    for s in sessions:
        proj = s.project or _UNATTRIBUTED
        team_id = _team_for_user(org, s.user) if s.user else _UNASSIGNED
        project_map[proj][team_id].append(s)

    project_rollups: list[ProjectRollup] = []
    for proj_id, by_team in sorted(project_map.items()):
        all_proj_sessions = [s for ss in by_team.values() for s in ss]
        per_team = {
            tid: round(sum(s.cost_usd for s in ss), 4)
            for tid, ss in by_team.items()
        }
        trust = aggregate_trust([session_trust(s) for s in all_proj_sessions])
        project_rollups.append(
            ProjectRollup(
                project_id=proj_id,
                sessions=len(all_proj_sessions),
                total_cost=round(sum(s.cost_usd for s in all_proj_sessions), 4),
                trust=trust,
                per_team=per_team,
            )
        )

    # --- Governance flags ---
    flags = _governance_flags(sessions, team_rollups, org, known_models or set())

    # --- Finance rows ---
    billing_period = _billing_period_label(period)
    finance_rows = _build_finance_rows(
        sessions, org, cost_centers, billing_period
    )

    # --- Org-level aggregates ---
    total_sessions = len(sessions)
    total_cost = round(sum(s.cost_usd for s in sessions), 4)
    active_users = len({s.user for s in sessions if s.user})
    trust = aggregate_trust([session_trust(s) for s in sessions])

    return OrgSummary(
        org_name=org.org.name,
        period=period,
        total_sessions=total_sessions,
        total_cost=total_cost,
        active_users=active_users,
        teams=team_rollups,
        projects=project_rollups,
        trust=trust,
        governance_flags=flags,
        finance_rows=finance_rows,
    )


def _build_team_rollup(
    team_id: str,
    team_name: str,
    department_id: str | None,
    t_sessions: list[AiSession],
    org: OrgConfig,
) -> TeamRollup:
    unattributed = sum(1 for s in t_sessions if not s.project)
    direct = round(sum(s.cost_usd for s in t_sessions if s.billing != "credits"), 4)
    allocated = round(
        sum((s.credits or 0.0) for s in t_sessions if s.billing == "credits"), 4
    )
    trust = aggregate_trust([session_trust(s) for s in t_sessions]) if t_sessions else "missing"
    active_users_set = {s.user for s in t_sessions if s.user}

    per_project: dict[str, float] = defaultdict(float)
    for s in t_sessions:
        per_project[s.project or _UNATTRIBUTED] += s.cost_usd

    # User rollups within this team
    user_map: dict[str, list[AiSession]] = defaultdict(list)
    for s in t_sessions:
        if s.user:
            user_map[s.user].append(s)

    user_rollups = [
        _build_user_rollup(email, u_sessions, org)
        for email, u_sessions in sorted(user_map.items())
    ]

    return TeamRollup(
        team_id=team_id,
        team_name=team_name,
        department_id=department_id,
        sessions=len(t_sessions),
        active_users=len(active_users_set),
        total_cost=round(direct + allocated, 4),
        direct_usd=direct,
        allocated_usd=allocated,
        trust=trust,
        unattributed_count=unattributed,
        per_project=dict(per_project),
        user_rollups=user_rollups,
    )


def _build_user_rollup(
    email: str, u_sessions: list[AiSession], org: OrgConfig
) -> UserRollup:
    active_days = len({s.start.date() for s in u_sessions})
    tools: dict[str, int] = defaultdict(int)
    for s in u_sessions:
        tools[s.tool] += 1
    trust = aggregate_trust([session_trust(s) for s in u_sessions])
    return UserRollup(
        user=email,
        display_name=_display_name(org, email),
        team_id=_team_for_user(org, email),
        sessions=len(u_sessions),
        active_days=active_days,
        tools=dict(tools),
        total_cost=round(sum(s.cost_usd for s in u_sessions), 4),
        trust=trust,
    )


def _governance_flags(
    sessions: list[AiSession],
    team_rollups: list[TeamRollup],
    org: OrgConfig,
    known_models: set[str],
) -> list[GovernanceFlag]:
    flags: list[GovernanceFlag] = []

    # No-capture: team members with zero sessions in period
    active_users = {s.user for s in sessions if s.user}
    for m in org.members:
        if m.email not in active_users:
            flags.append(
                GovernanceFlag(
                    category="no_capture",
                    team_id=m.team_id,
                    user=m.email,
                    detail=f"{m.display_name or m.email} has no capture this period",
                )
            )

    # Unknown models (only if known_models is populated)
    if known_models:
        unknown = {s.model for s in sessions if s.model not in known_models}
        for model in sorted(unknown):
            flags.append(
                GovernanceFlag(
                    category="unknown_model",
                    team_id=None,
                    user=None,
                    detail=f"Unknown model: {model}",
                )
            )

    # Unattributed rate per team
    for tr in team_rollups:
        if tr.sessions == 0:
            continue
        rate = tr.unattributed_count / tr.sessions
        if rate > _UNATTRIBUTED_THRESHOLD:
            pct = int(rate * 100)
            flags.append(
                GovernanceFlag(
                    category="unattributed_rate",
                    team_id=tr.team_id,
                    user=None,
                    detail=(
                        f"{tr.team_name}: {pct}% unattributed "
                        f"({tr.unattributed_count}/{tr.sessions})"
                    ),
                )
            )

    return flags


def _build_finance_rows(
    sessions: list[AiSession],
    org: OrgConfig,
    cost_centers: CostCenterConfig,
    billing_period: str,
) -> list[FinanceRow]:
    # Group by (project, team, cost_center, tool)
    buckets: dict[tuple[str, str, str, str], list[AiSession]] = defaultdict(list)
    for s in sessions:
        proj = s.project or _UNATTRIBUTED
        team_id = _team_for_user(org, s.user) if s.user else _UNASSIGNED
        cc = cost_centers.resolve(s.project or "", team_id) or "(none)"
        buckets[(proj, team_id, cc, s.tool)].append(s)

    rows: list[FinanceRow] = []
    for (proj, team_id, cc, tool), group in sorted(buckets.items()):
        direct = round(sum(s.cost_usd for s in group if s.billing != "credits"), 4)
        allocated = round(
            sum((s.credits or 0.0) for s in group if s.billing == "credits"), 4
        )
        trust = aggregate_trust([session_trust(s) for s in group])
        rows.append(
            FinanceRow(
                billing_period=billing_period,
                cost_center=cc,
                team_id=team_id,
                project_id=proj,
                tool=tool,
                sessions=len(group),
                direct_usd=direct,
                allocated_usd=allocated,
                total_usd=round(direct + allocated, 4),
                trust=trust,
            )
        )
    return rows


def _billing_period_label(period: str) -> str:
    from datetime import datetime

    now = datetime.now()
    if period == "month":
        return now.strftime("%Y-%m")
    if period == "today":
        return now.strftime("%Y-%m-%d")
    return period


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

_CSV_HEADER = (
    "billing_period,cost_center,team_id,project_id,tool,"
    "sessions,direct_usd,allocated_usd,total_usd,trust"
)


def render_finance_csv(rows: list[FinanceRow]) -> str:
    lines = [_CSV_HEADER]
    for r in rows:
        lines.append(
            f"{r.billing_period},{r.cost_center},{r.team_id},{r.project_id},"
            f"{r.tool},{r.sessions},{r.direct_usd:.4f},{r.allocated_usd:.4f},"
            f"{r.total_usd:.4f},{r.trust}"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Text renderer
# ---------------------------------------------------------------------------

_RULE = "─" * 56


def render_org_text(summary: OrgSummary) -> str:
    lines: list[str] = []
    lines.append(f"AI Org Report — {summary.org_name} — {summary.period}")
    lines.append(_RULE)

    lines.append(
        f"{summary.active_users} users  •  {summary.total_sessions} sessions  "
        f"•  ${summary.total_cost:.2f}  •  {len(summary.teams)} teams"
    )
    lines.append("")

    # Teams
    lines.append("Teams")
    lines.append("─" * 28)
    for tr in sorted(summary.teams, key=lambda t: -t.total_cost):
        trust_note = f"  [{tr.trust}]" if tr.trust != "captured" else ""
        unattr_note = (
            f"  ⚠ {tr.unattributed_count} unattributed" if tr.unattributed_count else ""
        )
        lines.append(
            f"  {tr.team_name:<22} {tr.sessions:>4} sessions  "
            f"${tr.total_cost:>7.2f}"
            f"  {tr.active_users} users{trust_note}{unattr_note}"
        )

    lines.append("")

    # Projects
    lines.append("Projects")
    lines.append("─" * 28)
    for pr in sorted(summary.projects, key=lambda p: -p.total_cost):
        trust_note = f"  [{pr.trust}]" if pr.trust != "captured" else ""
        lines.append(
            f"  {pr.project_id:<30} {pr.sessions:>4} sessions  "
            f"${pr.total_cost:>7.2f}{trust_note}"
        )

    lines.append("")

    # Governance
    if summary.governance_flags:
        lines.append("Governance")
        lines.append("─" * 28)
        for flag in summary.governance_flags:
            lines.append(f"  ● {flag.detail}")
        lines.append("")

    lines.append(_RULE)
    return "\n".join(lines)
