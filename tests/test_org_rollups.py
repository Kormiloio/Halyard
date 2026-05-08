"""Tests for halyard.org_rollups — pure-function aggregation layer."""

from __future__ import annotations

from datetime import datetime

from halyard.ai_log import AiSession
from halyard.cost_centers import CostCenterConfig, ProjectCostMapping, TeamCostMapping
from halyard.org import Department, Member, OrgConfig, OrgInfo, Team
from halyard.org_rollups import (
    aggregate_trust,
    build_org_summary,
    render_finance_csv,
    render_org_text,
    session_trust,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _session(
    *,
    user: str = "alice@example.com",
    project: str | None = "proj-a",
    tool: str = "claude-code",
    model: str = "claude-3-5-sonnet",
    billing: str = "api",
    cost_usd: float = 0.10,
    credits: float | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> AiSession:
    t = start or datetime(2025, 5, 1, 10, 0, 0)
    return AiSession(
        start=t,
        end=end or datetime(2025, 5, 1, 10, 30, 0),
        tool=tool,
        model=model,
        billing=billing,
        cost_usd=cost_usd,
        credits=credits,
        user=user,
        project=project,
        input_tokens=100,
        output_tokens=50,
    )


def _org(
    members: list[Member] | None = None,
    teams: list[Team] | None = None,
    departments: list[Department] | None = None,
) -> OrgConfig:
    return OrgConfig(
        org=OrgInfo(id="acme", name="Acme Corp"),
        departments=tuple(departments or []),
        teams=tuple(
            teams
            or [
                Team(id="eng", name="Engineering", department_id="product"),
                Team(id="data", name="Data", department_id="product"),
            ]
        ),
        members=tuple(
            members
            or [
                Member(email="alice@example.com", team_id="eng", display_name="Alice"),
                Member(email="bob@example.com", team_id="eng", display_name="Bob"),
                Member(email="carol@example.com", team_id="data", display_name="Carol"),
            ]
        ),
    )


def _cost_centers(
    project_mappings: list[tuple[str, str]] | None = None,
    team_mappings: list[tuple[str, str]] | None = None,
) -> CostCenterConfig:
    return CostCenterConfig(
        project_mappings=tuple(
            ProjectCostMapping(project_slug=slug, cost_center=cc)
            for slug, cc in (project_mappings or [])
        ),
        team_mappings=tuple(
            TeamCostMapping(team_id=tid, cost_center=cc) for tid, cc in (team_mappings or [])
        ),
    )


# ---------------------------------------------------------------------------
# session_trust
# ---------------------------------------------------------------------------


def test_session_trust_api_with_cost() -> None:
    s = _session(billing="api", cost_usd=0.05)
    assert session_trust(s) == "captured"


def test_session_trust_credits_billing() -> None:
    s = _session(billing="credits", cost_usd=0.0, credits=0.10)
    assert session_trust(s) == "allocated"


def test_session_trust_missing() -> None:
    s = _session(billing="credits", cost_usd=0.0, credits=None)
    assert session_trust(s) == "missing"


def test_session_trust_zero_cost_api() -> None:
    s = _session(billing="api", cost_usd=0.0)
    assert session_trust(s) == "missing"


# ---------------------------------------------------------------------------
# aggregate_trust
# ---------------------------------------------------------------------------


def test_aggregate_trust_single() -> None:
    assert aggregate_trust(["captured", "captured"]) == "captured"


def test_aggregate_trust_mixed() -> None:
    assert aggregate_trust(["captured", "allocated"]) == "mixed"


def test_aggregate_trust_empty() -> None:
    assert aggregate_trust([]) == "missing"


# ---------------------------------------------------------------------------
# build_org_summary — basic structure
# ---------------------------------------------------------------------------


def test_build_org_summary_org_name() -> None:
    org = _org()
    summary = build_org_summary([], org, _cost_centers(), period="month")
    assert summary.org_name == "Acme Corp"


def test_build_org_summary_empty_sessions() -> None:
    org = _org()
    summary = build_org_summary([], org, _cost_centers(), period="month")
    assert summary.total_sessions == 0
    assert summary.total_cost == 0.0
    assert summary.active_users == 0


def test_build_org_summary_counts() -> None:
    sessions = [
        _session(user="alice@example.com", cost_usd=0.10),
        _session(user="alice@example.com", cost_usd=0.20),
        _session(user="bob@example.com", cost_usd=0.05),
    ]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    assert summary.total_sessions == 3
    assert summary.active_users == 2
    assert abs(summary.total_cost - 0.35) < 1e-4


def test_build_org_summary_team_assignment() -> None:
    sessions = [
        _session(user="alice@example.com"),
        _session(user="carol@example.com"),
    ]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    team_ids = {tr.team_id for tr in summary.teams}
    assert "eng" in team_ids
    assert "data" in team_ids


def test_build_org_summary_unassigned_group() -> None:
    sessions = [_session(user="unknown@example.com")]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    team_ids = {tr.team_id for tr in summary.teams}
    assert "(unassigned)" in team_ids


# ---------------------------------------------------------------------------
# Team rollups
# ---------------------------------------------------------------------------


def test_team_rollup_unattributed_count() -> None:
    sessions = [
        _session(user="alice@example.com", project="proj-a"),
        _session(user="alice@example.com", project=None),
        _session(user="alice@example.com", project=None),
    ]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    eng = next(tr for tr in summary.teams if tr.team_id == "eng")
    assert eng.unattributed_count == 2


def test_team_rollup_direct_vs_allocated() -> None:
    sessions = [
        _session(user="alice@example.com", billing="api", cost_usd=0.30, credits=None),
        _session(user="alice@example.com", billing="credits", cost_usd=0.0, credits=0.20),
    ]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    eng = next(tr for tr in summary.teams if tr.team_id == "eng")
    assert abs(eng.direct_usd - 0.30) < 1e-4
    assert abs(eng.allocated_usd - 0.20) < 1e-4


def test_team_rollup_user_rollups_populated() -> None:
    sessions = [
        _session(user="alice@example.com"),
        _session(user="bob@example.com"),
    ]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    eng = next(tr for tr in summary.teams if tr.team_id == "eng")
    user_emails = {ur.user for ur in eng.user_rollups}
    assert "alice@example.com" in user_emails
    assert "bob@example.com" in user_emails


def test_user_rollup_display_name() -> None:
    sessions = [_session(user="alice@example.com")]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    eng = next(tr for tr in summary.teams if tr.team_id == "eng")
    alice = next(ur for ur in eng.user_rollups if ur.user == "alice@example.com")
    assert alice.display_name == "Alice"


# ---------------------------------------------------------------------------
# Project rollups
# ---------------------------------------------------------------------------


def test_project_rollup_created() -> None:
    sessions = [
        _session(project="proj-a"),
        _session(project="proj-b"),
        _session(project=None),
    ]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    proj_ids = {pr.project_id for pr in summary.projects}
    assert "proj-a" in proj_ids
    assert "proj-b" in proj_ids
    assert "(unattributed)" in proj_ids


def test_project_rollup_per_team_breakdown() -> None:
    sessions = [
        _session(user="alice@example.com", project="proj-x", cost_usd=0.10),
        _session(user="carol@example.com", project="proj-x", cost_usd=0.05),
    ]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    proj = next(pr for pr in summary.projects if pr.project_id == "proj-x")
    assert "eng" in proj.per_team
    assert "data" in proj.per_team
    assert abs(proj.per_team["eng"] - 0.10) < 1e-4
    assert abs(proj.per_team["data"] - 0.05) < 1e-4


# ---------------------------------------------------------------------------
# Governance flags
# ---------------------------------------------------------------------------


def test_governance_no_capture_flag() -> None:
    # Alice has no sessions — should get a no_capture flag
    sessions = [_session(user="bob@example.com")]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    no_cap = [f for f in summary.governance_flags if f.category == "no_capture"]
    users_flagged = {f.user for f in no_cap}
    assert "alice@example.com" in users_flagged
    assert "carol@example.com" in users_flagged


def test_governance_unattributed_rate_flag() -> None:
    sessions = [
        _session(user="alice@example.com", project=None),
        _session(user="alice@example.com", project=None),
        _session(user="alice@example.com", project=None),
        _session(user="alice@example.com", project=None),
        _session(user="alice@example.com", project=None),
        _session(user="alice@example.com", project=None),
        _session(user="alice@example.com", project=None),
        _session(user="alice@example.com", project=None),
        _session(user="alice@example.com", project=None),
        _session(user="alice@example.com", project=None),
        _session(user="alice@example.com", project="proj-a"),
    ]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    unattr = [f for f in summary.governance_flags if f.category == "unattributed_rate"]
    assert any(f.team_id == "eng" for f in unattr)


def test_governance_unknown_model_flag() -> None:
    sessions = [_session(model="gpt-99-turbo")]
    org = _org()
    known = {"claude-3-5-sonnet", "claude-opus-4"}
    summary = build_org_summary(sessions, org, _cost_centers(), period="month", known_models=known)
    unknown = [f for f in summary.governance_flags if f.category == "unknown_model"]
    assert any("gpt-99-turbo" in f.detail for f in unknown)


def test_governance_no_unknown_flag_when_known_models_empty() -> None:
    sessions = [_session(model="mystery-model")]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month", known_models=set())
    unknown = [f for f in summary.governance_flags if f.category == "unknown_model"]
    assert len(unknown) == 0


# ---------------------------------------------------------------------------
# Finance rows and CSV export
# ---------------------------------------------------------------------------


def test_finance_rows_cost_center_from_project_mapping() -> None:
    sessions = [_session(user="alice@example.com", project="proj-a")]
    org = _org()
    cc_config = _cost_centers(project_mappings=[("proj-a", "CC-ENG-01")])
    summary = build_org_summary(sessions, org, cc_config, period="month")
    row = next(r for r in summary.finance_rows if r.project_id == "proj-a")
    assert row.cost_center == "CC-ENG-01"


def test_finance_rows_cost_center_from_team_fallback() -> None:
    sessions = [_session(user="alice@example.com", project="proj-z")]
    org = _org()
    cc_config = _cost_centers(team_mappings=[("eng", "CC-ENG-FALLBACK")])
    summary = build_org_summary(sessions, org, cc_config, period="month")
    row = next(r for r in summary.finance_rows if r.project_id == "proj-z")
    assert row.cost_center == "CC-ENG-FALLBACK"


def test_finance_rows_no_cost_center() -> None:
    sessions = [_session(user="alice@example.com", project="proj-unknown")]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    row = next(r for r in summary.finance_rows if r.project_id == "proj-unknown")
    assert row.cost_center == "(none)"


def test_render_finance_csv_header() -> None:
    sessions = [_session(user="alice@example.com", project="proj-a", cost_usd=0.10)]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    csv_text = render_finance_csv(summary.finance_rows)
    assert csv_text.startswith("billing_period,cost_center,team_id,project_id")


def test_render_finance_csv_row_count() -> None:
    sessions = [
        _session(user="alice@example.com", project="proj-a"),
        _session(user="carol@example.com", project="proj-b"),
    ]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    csv_text = render_finance_csv(summary.finance_rows)
    lines = csv_text.strip().splitlines()
    assert len(lines) == 1 + len(summary.finance_rows)


# ---------------------------------------------------------------------------
# Text renderer
# ---------------------------------------------------------------------------


def test_render_org_text_contains_org_name() -> None:
    sessions = [_session()]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    text = render_org_text(summary)
    assert "Acme Corp" in text


def test_render_org_text_contains_teams_section() -> None:
    sessions = [_session()]
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    text = render_org_text(summary)
    assert "Teams" in text


def test_render_org_text_governance_section_when_flags() -> None:
    sessions = [_session(user="alice@example.com", project=None)] * 10
    org = _org()
    summary = build_org_summary(sessions, org, _cost_centers(), period="month")
    text = render_org_text(summary)
    assert "Governance" in text
