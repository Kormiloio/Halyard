"""Tests for org identity, OrgSession normalization, org store, sync, and reports."""

from __future__ import annotations

import textwrap
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard.ai_log import AI_LOG_FILENAME, AiSession
from halyard.cost_centers import (
    CostCenterConfig,
    ProjectCostMapping,
    TeamCostMapping,
    read_cost_center_config,
    read_project_cost_centers,
    resolve_cost_center,
)
from halyard.org import (
    Department,
    Member,
    OrgConfig,
    OrgInfo,
    OrgSession,
    Team,
    normalize_session,
    read_org_config,
)
from halyard.org_store import (
    ORG_DB_FILENAME,
    finance_export,
    governance_gaps,
    insert_session,
    insert_sessions,
    org_monthly_summary,
    project_monthly_rollup,
    purge_user,
    read_sync_audit,
    record_sync,
    team_monthly_rollup,
    user_monthly_rollup,
)
from halyard.sync import sync_project

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _org_config(
    org_id: str = "acme",
    members: list[tuple[str, str]] | None = None,
) -> OrgConfig:
    member_list = [
        Member(email=email, team_id=team_id)
        for email, team_id in (members or [("alice@acme.example", "auth-team")])
    ]
    return OrgConfig(
        org=OrgInfo(id=org_id, name="Acme Corp"),
        teams=(Team(id="auth-team", name="Auth", department_id="engineering"),),
        departments=(Department(id="engineering", name="Engineering"),),
        members=tuple(member_list),
    )


def _session(
    tool: str = "claude-code",
    model: str = "claude-sonnet-4-6",
    cost: float = 1.50,
    project: str | None = "acme:auth",
    user: str | None = "alice@acme.example",
    billing: str = "api",
    credits: float | None = None,
    minutes: int = 10,
    tags: list[str] | None = None,
) -> AiSession:
    start = datetime(2026, 5, 7, 10, 0)
    return AiSession(
        start=start,
        end=start + timedelta(minutes=minutes),
        tool=tool,
        model=model,
        input_tokens=1000,
        output_tokens=500,
        cost_usd=cost,
        project=project,
        user=user,
        billing=billing,
        credits=credits,
        tags=tags or [],
    )


def _org_session(
    org_id: str = "acme",
    team_id: str = "auth-team",
    user_id: str = "alice@acme.example",
    project_id: str = "acme:auth",
    tool: str = "claude-code",
    model: str = "claude-sonnet-4-6",
    cost_usd: float = 1.50,
    allocated_usd: float = 0.0,
    trust: str = "captured",
    attribution_state: str = "confirmed",
    line_hash: str = "abc123",
) -> OrgSession:
    start = datetime(2026, 5, 7, 10, 0)
    return OrgSession(
        org_id=org_id,
        team_id=team_id,
        user_id=user_id,
        project_id=project_id,
        attribution_state=attribution_state,  # type: ignore[arg-type]
        tool=tool,
        model=model,
        billing="api",
        start=start,
        end=start + timedelta(minutes=10),
        cost_usd=cost_usd,
        allocated_usd=allocated_usd,
        trust=trust,  # type: ignore[arg-type]
        local_log_line_hash=line_hash,
    )


# ---------------------------------------------------------------------------
# OrgConfig — identity resolution
# ---------------------------------------------------------------------------


def test_resolve_known_user():
    cfg = _org_config()
    user_id, team_id = cfg.resolve_user("alice@acme.example")
    assert user_id == "alice@acme.example"
    assert team_id == "auth-team"


def test_resolve_unknown_user_falls_back():
    cfg = _org_config()
    user_id, team_id = cfg.resolve_user("unknown@example.com")
    assert user_id == "unknown@example.com"
    assert team_id == "(unassigned)"


def test_resolve_is_case_insensitive():
    cfg = _org_config()
    _, team_id = cfg.resolve_user("Alice@ACME.EXAMPLE")
    assert team_id == "auth-team"


def test_resolve_empty_email_falls_back():
    cfg = _org_config()
    _, team_id = cfg.resolve_user("")
    assert team_id == "(unassigned)"


def test_team_name_lookup():
    cfg = _org_config()
    assert cfg.team_name("auth-team") == "Auth"
    assert cfg.team_name("no-such-team") == "no-such-team"


# ---------------------------------------------------------------------------
# read_org_config
# ---------------------------------------------------------------------------


def test_read_org_config_missing(tmp_path: Path):
    assert read_org_config(tmp_path) is None


def test_read_org_config_parses_all_sections(tmp_path: Path):
    (tmp_path / "org.toml").write_text(
        textwrap.dedent("""\
        [org]
        id = "acme-corp"
        name = "Acme Corp"

        [[department]]
        id = "engineering"
        name = "Engineering"

        [[team]]
        id = "auth-team"
        name = "Auth"
        department_id = "engineering"

        [[member]]
        email = "alice@acme.example"
        team_id = "auth-team"
        display_name = "Alice"
        """)
    )
    cfg = read_org_config(tmp_path)
    assert cfg is not None
    assert cfg.org.id == "acme-corp"
    assert len(cfg.departments) == 1
    assert len(cfg.teams) == 1
    assert len(cfg.members) == 1
    _, team = cfg.resolve_user("alice@acme.example")
    assert team == "auth-team"


# ---------------------------------------------------------------------------
# normalize_session
# ---------------------------------------------------------------------------


def test_normalize_basic():
    cfg = _org_config()
    s = _session()
    raw = s.to_log_line()
    org_s = normalize_session(raw, s, cfg)

    assert org_s.org_id == "acme"
    assert org_s.team_id == "auth-team"
    assert org_s.user_id == "alice@acme.example"
    assert org_s.project_id == "acme:auth"
    assert org_s.attribution_state == "confirmed"
    assert org_s.trust == "captured"
    assert org_s.local_log_line_hash != ""


def test_normalize_unknown_user_is_unassigned():
    cfg = _org_config()
    s = _session(user="bob@other.example")
    org_s = normalize_session(s.to_log_line(), s, cfg)
    assert org_s.team_id == "(unassigned)"


def test_normalize_unattributed_session():
    cfg = _org_config()
    s = _session(project=None)
    org_s = normalize_session(s.to_log_line(), s, cfg)
    assert org_s.project_id == ""
    assert org_s.attribution_state == "unattributed"


def test_normalize_allocated_trust():
    cfg = _org_config()
    s = _session(cost=0.0, billing="seat", credits=2.50)
    org_s = normalize_session(s.to_log_line(), s, cfg)
    assert org_s.trust == "allocated"
    assert org_s.allocated_usd == pytest.approx(2.50)


def test_normalize_missing_trust_for_seat_no_credits():
    cfg = _org_config()
    s = _session(cost=0.0, billing="seat", credits=None)
    org_s = normalize_session(s.to_log_line(), s, cfg)
    assert org_s.trust == "missing"


def test_normalize_strips_note_tag():
    cfg = _org_config()
    s = _session(tags=["branch:main", "note:secret stuff"])
    org_s = normalize_session(s.to_log_line(), s, cfg)
    assert not any(t.startswith("note:") for t in org_s.tags)
    assert "branch:main" in org_s.tags


def test_normalize_hash_is_deterministic():
    cfg = _org_config()
    s = _session()
    raw = s.to_log_line()
    h1 = normalize_session(raw, s, cfg).local_log_line_hash
    h2 = normalize_session(raw, s, cfg).local_log_line_hash
    assert h1 == h2


# ---------------------------------------------------------------------------
# org_store — insert / deduplication
# ---------------------------------------------------------------------------


def test_insert_session_returns_true(tmp_path: Path):
    db = tmp_path / ORG_DB_FILENAME
    inserted = insert_session(db, _org_session(line_hash="unique-1"))
    assert inserted is True


def test_insert_duplicate_returns_false(tmp_path: Path):
    db = tmp_path / ORG_DB_FILENAME
    s = _org_session(line_hash="dup-1")
    assert insert_session(db, s) is True
    assert insert_session(db, s) is False


def test_insert_sessions_counts(tmp_path: Path):
    db = tmp_path / ORG_DB_FILENAME
    sessions = [_org_session(line_hash=f"h{i}") for i in range(3)]
    inserted, skipped = insert_sessions(db, sessions)
    assert inserted == 3
    assert skipped == 0

    # re-sync same sessions
    inserted2, skipped2 = insert_sessions(db, sessions)
    assert inserted2 == 0
    assert skipped2 == 3


# ---------------------------------------------------------------------------
# org_store — rollup queries
# ---------------------------------------------------------------------------


def _populated_db(tmp_path: Path) -> Path:
    db = tmp_path / ORG_DB_FILENAME
    sessions = [
        # alice, auth-team, acme:auth — May 2026
        _org_session(line_hash="a1", cost_usd=1.00, project_id="acme:auth"),
        _org_session(line_hash="a2", cost_usd=2.00, project_id="acme:auth"),
        # bob, platform-team, acme:infra — May 2026
        OrgSession(
            org_id="acme",
            team_id="platform-team",
            user_id="bob@acme.example",
            project_id="acme:infra",
            attribution_state="confirmed",
            tool="cursor",
            model="gpt-4o",
            billing="api",
            start=datetime(2026, 5, 10, 9, 0),
            end=datetime(2026, 5, 10, 9, 30),
            cost_usd=3.00,
            trust="captured",
            local_log_line_hash="b1",
        ),
        # unattributed session for alice
        OrgSession(
            org_id="acme",
            team_id="auth-team",
            user_id="alice@acme.example",
            project_id="",
            attribution_state="unattributed",
            tool="claude-code",
            model="claude-sonnet-4-6",
            billing="api",
            start=datetime(2026, 5, 15, 11, 0),
            end=datetime(2026, 5, 15, 11, 15),
            cost_usd=0.50,
            trust="captured",
            local_log_line_hash="a3",
        ),
    ]
    insert_sessions(db, sessions)
    return db


def test_team_monthly_rollup(tmp_path: Path):
    db = _populated_db(tmp_path)
    rows = team_monthly_rollup(db, "acme", 2026, 5)
    assert len(rows) == 2
    teams = {r["team_id"] for r in rows}
    assert "auth-team" in teams
    assert "platform-team" in teams


def test_team_monthly_rollup_filter(tmp_path: Path):
    db = _populated_db(tmp_path)
    rows = team_monthly_rollup(db, "acme", 2026, 5, team_id="auth-team")
    assert len(rows) == 1
    assert rows[0]["team_id"] == "auth-team"
    assert rows[0]["sessions"] == 3  # 2 attributed + 1 unattributed
    assert rows[0]["unattributed"] == 1


def test_project_monthly_rollup(tmp_path: Path):
    db = _populated_db(tmp_path)
    rows = project_monthly_rollup(db, "acme", 2026, 5)
    project_ids = {r["project_id"] for r in rows}
    assert "acme:auth" in project_ids
    assert "acme:infra" in project_ids
    # unattributed sessions excluded from project rollup
    assert "" not in project_ids


def test_user_monthly_rollup(tmp_path: Path):
    db = _populated_db(tmp_path)
    rows = user_monthly_rollup(db, "acme", 2026, 5)
    users = {r["user_id"] for r in rows}
    assert "alice@acme.example" in users
    assert "bob@acme.example" in users


def test_org_monthly_summary_totals(tmp_path: Path):
    db = _populated_db(tmp_path)
    s = org_monthly_summary(db, "acme", 2026, 5)
    assert s["sessions"] == 4
    assert s["active_users"] == 2
    assert s["total_usd"] == pytest.approx(6.50)
    assert s["unattributed"] == 1


def test_org_monthly_summary_empty_period(tmp_path: Path):
    db = _populated_db(tmp_path)
    s = org_monthly_summary(db, "acme", 2026, 6)
    assert s.get("sessions", 0) == 0


def test_governance_gaps_detects_unattributed(tmp_path: Path):
    db = _populated_db(tmp_path)
    # auth-team has 3 sessions, 1 unattributed → 33% > 10% threshold
    data = governance_gaps(db, "acme", 2026, 5, unattributed_threshold=0.10)
    alert_teams = [a["team_id"] for a in data["alerts"] if a["type"] == "unattributed_rate"]
    assert "auth-team" in alert_teams


def test_governance_no_alerts_when_within_threshold(tmp_path: Path):
    db = _populated_db(tmp_path)
    # With 100% threshold nothing fires
    data = governance_gaps(db, "acme", 2026, 5, unattributed_threshold=1.0)
    unattr_alerts = [a for a in data["alerts"] if a["type"] == "unattributed_rate"]
    assert len(unattr_alerts) == 0


def test_finance_export_rows(tmp_path: Path):
    db = _populated_db(tmp_path)
    rows = finance_export(db, "acme", 2026, 5)
    assert len(rows) > 0
    # every row has required fields
    for r in rows:
        assert "billing_period" in r
        assert "team_id" in r
        assert "trust" in r
    periods = {r["billing_period"] for r in rows}
    assert periods == {"2026-05"}


# ---------------------------------------------------------------------------
# sync_project
# ---------------------------------------------------------------------------


def test_sync_project_inserts_sessions(tmp_path: Path):
    # write org.toml
    (tmp_path / "org.toml").write_text(
        textwrap.dedent("""\
        [org]
        id = "acme"
        name = "Acme"

        [[member]]
        email = "alice@acme.example"
        team_id = "auth-team"
        """)
    )
    # write ai-sessions.log
    s = _session()
    (tmp_path / AI_LOG_FILENAME).write_text(s.to_log_line() + "\n")

    result = sync_project(tmp_path, hub_dir=tmp_path)
    assert result.inserted == 1
    assert result.skipped == 0
    assert result.errors == []


def test_sync_project_idempotent(tmp_path: Path):
    (tmp_path / "org.toml").write_text("[org]\nid = \"acme\"\nname = \"Acme\"\n")
    s = _session(user="unknown@example.com")
    (tmp_path / AI_LOG_FILENAME).write_text(s.to_log_line() + "\n")

    sync_project(tmp_path, hub_dir=tmp_path)
    result = sync_project(tmp_path, hub_dir=tmp_path)
    assert result.inserted == 0
    assert result.skipped == 1


def test_sync_project_missing_org_toml_returns_error(tmp_path: Path):
    (tmp_path / AI_LOG_FILENAME).write_text("# empty\n")
    result = sync_project(tmp_path, hub_dir=tmp_path)
    assert result.inserted == 0
    assert len(result.errors) == 1
    assert "org.toml" in result.errors[0]


def test_sync_project_missing_log_returns_error(tmp_path: Path):
    (tmp_path / "org.toml").write_text("[org]\nid = \"acme\"\nname = \"Acme\"\n")
    result = sync_project(tmp_path, hub_dir=tmp_path)
    assert len(result.errors) == 1
    assert "ai-sessions.log" in result.errors[0]


# ---------------------------------------------------------------------------
# cost_centers — resolution
# ---------------------------------------------------------------------------


def test_resolve_cost_center_from_project_override(tmp_path: Path):
    overrides = {"acme:auth": "CC-001"}
    cfg = CostCenterConfig()
    result = resolve_cost_center(
        "acme:auth", "auth-team", project_overrides=overrides, org_config=cfg
    )
    assert result == "CC-001"


def test_resolve_cost_center_from_org_project_mapping():
    cfg = CostCenterConfig(
        project_mappings=(ProjectCostMapping(project_slug="acme:auth", cost_center="CC-ORG-001"),),
    )
    result = resolve_cost_center("acme:auth", "auth-team", project_overrides={}, org_config=cfg)
    assert result == "CC-ORG-001"


def test_resolve_cost_center_falls_back_to_team_mapping():
    cfg = CostCenterConfig(
        team_mappings=(TeamCostMapping(team_id="auth-team", cost_center="CC-TEAM-010"),),
    )
    result = resolve_cost_center("acme:auth", "auth-team", project_overrides={}, org_config=cfg)
    assert result == "CC-TEAM-010"


def test_resolve_cost_center_project_override_beats_org_mapping():
    cfg = CostCenterConfig(
        project_mappings=(ProjectCostMapping(project_slug="acme:auth", cost_center="CC-ORG-001"),),
    )
    overrides = {"acme:auth": "CC-LOCAL-999"}
    result = resolve_cost_center(
        "acme:auth", "auth-team", project_overrides=overrides, org_config=cfg
    )
    assert result == "CC-LOCAL-999"


def test_resolve_cost_center_unattributed_returns_empty():
    cfg = CostCenterConfig()
    result = resolve_cost_center("", "auth-team", project_overrides={}, org_config=cfg)
    assert result == ""


def test_read_cost_center_config_missing(tmp_path: Path):
    cfg = read_cost_center_config(tmp_path)
    assert cfg.project_mappings == ()
    assert cfg.team_mappings == ()


def test_read_cost_center_config_parses(tmp_path: Path):
    (tmp_path / "org-cost-centers.toml").write_text(
        '[[project_mapping]]\nproject_slug = "acme:auth"\ncost_center = "CC-001"\n'
        '[[team_mapping]]\nteam_id = "auth-team"\ncost_center = "CC-010"\n'
    )
    cfg = read_cost_center_config(tmp_path)
    assert len(cfg.project_mappings) == 1
    assert len(cfg.team_mappings) == 1
    assert cfg.project_mappings[0].cost_center == "CC-001"


def test_read_project_cost_centers(tmp_path: Path):
    (tmp_path / "projects.toml").write_text(
        "[[project]]\nslug = \"acme:auth\"\nclient_slug = \"acme\"\n"
        "name = \"Auth\"\ncost_center = \"CC-042\"\n"
    )
    result = read_project_cost_centers(tmp_path)
    assert result == {"acme:auth": "CC-042"}


def test_read_project_cost_centers_missing(tmp_path: Path):
    assert read_project_cost_centers(tmp_path) == {}


# ---------------------------------------------------------------------------
# sync_audit — record and read
# ---------------------------------------------------------------------------


def test_record_and_read_sync_audit(tmp_path: Path):
    db = tmp_path / ORG_DB_FILENAME
    record_sync(db, org_id="acme", synced_by="alice", inserted=5, skipped=2, source_path="/hub")
    rows = read_sync_audit(db, "acme")
    assert len(rows) == 1
    assert rows[0]["synced_by"] == "alice"
    assert rows[0]["inserted"] == 5
    assert rows[0]["skipped"] == 2
    assert rows[0]["event"] == "sync"


def test_sync_project_records_audit(tmp_path: Path):
    (tmp_path / "org.toml").write_text("[org]\nid = \"acme\"\nname = \"Acme\"\n")
    s = _session()
    (tmp_path / AI_LOG_FILENAME).write_text(s.to_log_line() + "\n")
    sync_project(tmp_path, hub_dir=tmp_path)
    rows = read_sync_audit(tmp_path / ORG_DB_FILENAME, "acme")
    assert len(rows) == 1
    assert rows[0]["inserted"] == 1


# ---------------------------------------------------------------------------
# purge_user — GDPR removal
# ---------------------------------------------------------------------------


def test_purge_user_deletes_records_and_logs_audit(tmp_path: Path):
    db = tmp_path / ORG_DB_FILENAME
    sessions = [
        _org_session(user_id="alice@acme.example", line_hash="a1"),
        _org_session(user_id="alice@acme.example", line_hash="a2"),
        _org_session(user_id="bob@acme.example", line_hash="b1"),
    ]
    insert_sessions(db, sessions)

    count = purge_user(db, "acme", "alice@acme.example", purged_by="admin")
    assert count == 2

    # Alice's sessions gone, Bob's intact
    users_remaining = set()
    for r in user_monthly_rollup(db, "acme", 2026, 5):
        users_remaining.add(r["user_id"])
    assert "alice@acme.example" not in users_remaining
    assert "bob@acme.example" in users_remaining

    # Audit trail has the purge event
    audit = read_sync_audit(db, "acme")
    purge_events = [r for r in audit if "purge" in r["event"]]
    assert len(purge_events) == 1
    assert purge_events[0]["synced_by"] == "admin"


def test_purge_user_zero_count_still_logs(tmp_path: Path):
    db = tmp_path / ORG_DB_FILENAME
    count = purge_user(db, "acme", "nobody@acme.example", purged_by="admin")
    assert count == 0
    audit = read_sync_audit(db, "acme")
    assert len(audit) == 1
