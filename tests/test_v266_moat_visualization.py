"""v2.66 — moat visualization surface."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.moat import (
    confidence_trend,
    cost_by_client,
    leakage,
    link_repo_command,
    project_evidence,
)

_MON = datetime(2026, 5, 11, 10, 0, 0)  # a Monday


def _s(
    *,
    project: str | None,
    attr: str | None = "timer",
    cost: float = 1.0,
    start: datetime = _MON,
    pr_state: str | None = None,
    remote: str | None = None,
) -> AiSession:
    return AiSession(
        start=start,
        end=start + timedelta(minutes=3),
        tool="claude-code",
        model="claude-opus-4-7",
        input_tokens=100,
        output_tokens=50,
        cost_usd=cost,
        project=project,
        attr_method=attr,
        pr_state=pr_state,
        remote=remote,
    )


def test_cost_by_client_buckets_by_week_and_project() -> None:
    pts = cost_by_client(
        [
            _s(project="acme:web", cost=2.0),
            _s(project="acme:web", cost=1.0, start=_MON + timedelta(days=7)),
            _s(project=None, cost=0.5),
        ]
    )
    by = {(p.period.isoformat(), p.project): p.cost_usd for p in pts}
    assert by[("2026-05-11", "acme:web")] == 2.0
    assert by[("2026-05-18", "acme:web")] == 1.0
    assert by[("2026-05-11", "(adrift)")] == 0.5  # adrift labelled, not dropped


def test_confidence_trend_uses_v265_bands() -> None:
    pts = confidence_trend(
        [
            _s(project="a:b", attr="timer"),
            _s(project="a:b", attr="git"),  # legacy → auto
            _s(project=None, attr=None),  # none
        ]
    )
    bands = {p.band: p.sessions for p in pts}
    assert bands == {"timer": 1, "auto": 1, "none": 1}


def test_project_evidence_joins_outcomes_and_confidence(tmp_path: Path) -> None:
    ev = project_evidence(
        [
            _s(project="acme:web", attr="timer", cost=3.0, pr_state="merged"),
            _s(project="acme:web", attr="timer", cost=1.0, pr_state="open"),
            _s(project="acme:web", attr="timer", cost=1.0, pr_state=None),
            _s(project=None, attr=None),  # adrift excluded from cards
        ],
        None,
    )
    assert len(ev) == 1
    e = ev[0]
    assert e.project == "acme:web"
    assert e.ai_cost_usd == 5.0
    assert (e.shipped, e.in_flight, e.abandoned, e.no_pr) == (1, 1, 0, 1)
    assert e.confidence == "timer"
    assert e.human_minutes is None  # no timeclock → None, not 0


def test_leakage_proposes_command_writes_nothing(tmp_path: Path) -> None:
    log = tmp_path / "unattributed.log"
    log.write_text(HEADER)
    s = _s(project=None, attr=None, cost=0.4, remote="git@github.com:acme/web.git")
    with log.open("a") as fh:
        fh.write(s.to_log_line() + "\n")
    before = log.read_text()

    rows = leakage(log)
    assert len(rows) == 1
    assert rows[0].remote == "git@github.com:acme/web.git"
    assert rows[0].cost_usd == 0.4
    assert rows[0].fix_command.startswith("halyard link-repo client:")
    assert "--remote git@github.com:acme/web.git" in rows[0].fix_command
    assert log.read_text() == before  # read-only


def test_leakage_absent_log() -> None:
    assert leakage(Path("/no/such/unattributed.log")) == []


def test_shared_link_repo_builder_is_single_source() -> None:
    # doctor must delegate to moat.link_repo_command (one source).
    from halyard import doctor

    remote = "git@github.com:acme/web.git"
    assert doctor._link_repo_command(remote) == link_repo_command(remote)


def test_moat_panel_renders_above_commodity(tmp_path: Path) -> None:
    from halyard.dashboard import render_dashboard

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "halyard.toml").write_text("[business]\n")
    (proj / "time.timeclock").write_text("; t\n")
    (proj / AI_LOG_FILENAME).write_text(HEADER)
    append_session(proj, _s(project="acme:web", attr="timer", cost=2.0))

    html = render_dashboard(proj)
    moat_at = html.find('data-panel="moat"')
    usage_at = html.find('data-panel="usage"')
    assert moat_at != -1 and usage_at != -1
    # Moat is primary: it renders before the commodity Usage panel.
    assert moat_at < usage_at
