"""v5.19 parallel-review round 3 — regression coverage for findings the
third outside audit caught across the full live worktree.

Findings covered:
  * P1 aggregated ledger buckets by session.end (matches billing-period
    selection) instead of session.start.
  * P1 month-specific evidence pins the ledger to the requested month,
    not min(s.start), so a subscription that's active in the requested
    month is allocated even when the session starts on the prior month's
    last day.
  * P2 cursor stop hook clears session state only AFTER successful
    persistence (or a deliberate non-turn rejection) — a crash in
    workspace parsing no longer permanently discards a recoverable turn.
  * P2 aggregated ledger merges trust labels across months — Jan
    captured + Feb allocated promotes the row to "mixed".
  * P2 rate_history_from_git uses structural TOML parsing, so a client
    with >3 lines between `slug` and `hourly_rate` still gets its rate
    changes recorded.
  * P2 log_agent branch filter reads first-class AiSession.branch.
  * P3 dashboard 401 hint references real commands, not "halyard bridge".
  * P3 trust-model recovery docs point at `halyard config integrity-migrate`.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from halyard.ai_log import AiSession

# ---------------------------------------------------------------------------
# P1 aggregated ledger buckets by session.end
# ---------------------------------------------------------------------------


def test_aggregated_ledger_buckets_cross_month_by_end(tmp_path: Path) -> None:
    """A session starting Jan 31 23:50 and ending Feb 1 00:10 is *February*
    work for billing — it must land in Feb's plan allocation, not Jan's."""
    from datetime import date

    from halyard.ai_plans import AiPlan
    from halyard.ledger import build_aggregated_ledger

    # Two plans matching the same tool. Only ONE applies per month: the
    # first match wins inside build_ledger, and `is_active_in` gates by
    # date. So we make them tile (Jan and Feb) and rely on the
    # session.end → correct-month bucketing to pick Feb.
    jan_plan = AiPlan(
        slug="jan-only",
        tool="claude-code",
        billing="seat",
        monthly_usd=0.0,
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 1, 31),
    )
    feb_plan = AiPlan(
        slug="feb-only",
        tool="claude-code",
        billing="seat",
        monthly_usd=100.0,
        starts_on=date(2026, 2, 1),
        ends_on=date(2026, 2, 28),
    )
    cross_month = AiSession(
        start=datetime(2026, 1, 31, 23, 50),
        end=datetime(2026, 2, 1, 0, 10),
        tool="claude-code",
        model="opus-4",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.0,
        project="acme:web",
    )
    summary = build_aggregated_ledger([cross_month], [jan_plan, feb_plan], [], period_label="cross")
    # The Feb plan must allocate; the Jan plan must not.
    assert summary.total_allocated_usd == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# P1 month-specific evidence pins ledger to requested month
# ---------------------------------------------------------------------------


def test_evidence_data_month_uses_requested_period(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A May evidence report containing a session whose start is in April
    (end on May 1) used to run the ledger for April → May plan inactive →
    $0. The fix pins build_ledger to the REQUESTED period, not
    ``min(s.start)``. We monkeypatch the report builder to bypass its own
    start-month filter so the cross-boundary session reaches the
    evidence path; the regression we're guarding is in `evidence.py`."""
    from datetime import date

    from halyard.evidence import build_evidence_data

    (tmp_path / "halyard.toml").write_text(
        '[business]\nname = "Test"\ncurrency = "USD"\n', encoding="utf-8"
    )
    (tmp_path / "time.timeclock").write_text("", encoding="utf-8")
    (tmp_path / "ai-plans.toml").write_text(
        '[[plan]]\nslug = "claude-seat"\ntool = "claude-code"\n'
        'billing = "seat"\nmonthly_usd = 100\n'
        "starts_on = 2026-05-01\nends_on = 2026-05-31\n",
        encoding="utf-8",
    )
    sess = AiSession(
        start=datetime(2026, 4, 30, 23, 50),
        end=datetime(2026, 5, 1, 0, 10),
        tool="claude-code",
        model="opus-4",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.0,
        project="acme:web",
    )

    def _fake_report(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        from halyard.reports import summarize_ai_sessions

        return summarize_ai_sessions([sess], period_label="May 2026")

    # The standalone evidence-report path imports `build_filtered_ai_report`
    # inside the function body, so patch the source module.
    import halyard.reports as reports_mod

    monkeypatch.setattr(reports_mod, "build_filtered_ai_report", _fake_report)

    # Sanity: assert the plan parses as expected.
    from halyard.ai_plans import read_ai_plans

    [plan] = read_ai_plans(tmp_path)
    assert plan.is_active_in(2026, 5) is True

    data = build_evidence_data(tmp_path, month="2026-05")
    cost = data["cost"]
    assert isinstance(cost, dict)
    # The May plan was active and a session ending May 1 reached evidence —
    # the appendix MUST report allocated cost. Before the fix this was $0
    # because the ledger ran for April (min(s.start).month).
    assert cost["allocated_usd"] == pytest.approx(100.0)

    # Force-touch the plan's date so the import stays meaningful (silences
    # linters; the plan was already validated above).
    assert plan.starts_on == date(2026, 5, 1)


# ---------------------------------------------------------------------------
# P2 cursor stop hook clears state only after persist
# ---------------------------------------------------------------------------


def test_cursor_hook_preserves_state_on_post_parse_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash after token parsing but before persistence must NOT discard
    the session-start file — the next stop fire (or `halyard repair`) needs
    it to claim the recoverable turn."""
    import json

    from halyard.collectors import cursor as cursor_mod

    session_file = tmp_path / "cursor-session"
    monkeypatch.setattr(cursor_mod, "_CURSOR_SESSION_FILE", session_file)
    session_file.parent.mkdir(parents=True, exist_ok=True)
    recent = datetime.now().replace(microsecond=0).isoformat()
    session_file.write_text(json.dumps({"start": recent}), encoding="utf-8")

    payload = {
        "model": "claude-opus-4",
        "usage": {"input_tokens": 10, "output_tokens": 20},
        "workspace_roots": [],
    }
    monkeypatch.setattr(cursor_mod, "_read_payload", lambda: payload)
    monkeypatch.setattr(cursor_mod, "find_hub", lambda: None)
    monkeypatch.setattr(cursor_mod, "_resolve_project_dir", lambda payload: None)
    monkeypatch.setattr(cursor_mod, "read_active_project", lambda: None)
    monkeypatch.setattr(cursor_mod, "maybe_show_dashboard_hint", lambda: None)

    # Make persistence crash AFTER we've already parsed the payload — this
    # is the new "later-stage crash" case the reviewer flagged.
    def _explode(_session) -> Path:  # type: ignore[no-untyped-def]
        raise RuntimeError("disk full")

    monkeypatch.setattr(cursor_mod, "write_unattributed_session", _explode)

    # We don't catch — the outer `_run_hook` does. We only care about state.
    import contextlib

    with contextlib.suppress(RuntimeError):
        cursor_mod.handle_stop_hook()

    # The state file MUST still exist so the next fire can recover.
    assert session_file.exists(), "session-start file was cleared before persistence completed"


def test_cursor_hook_clears_state_after_successful_persist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: persistence succeeds → state is cleared."""
    import json

    from halyard.collectors import cursor as cursor_mod

    session_file = tmp_path / "cursor-session"
    monkeypatch.setattr(cursor_mod, "_CURSOR_SESSION_FILE", session_file)
    session_file.parent.mkdir(parents=True, exist_ok=True)
    recent = datetime.now().replace(microsecond=0).isoformat()
    session_file.write_text(json.dumps({"start": recent}), encoding="utf-8")

    payload = {
        "model": "claude-opus-4",
        "usage": {"input_tokens": 10, "output_tokens": 20},
        "workspace_roots": [],
    }
    monkeypatch.setattr(cursor_mod, "_read_payload", lambda: payload)
    monkeypatch.setattr(cursor_mod, "find_hub", lambda: None)
    monkeypatch.setattr(cursor_mod, "_resolve_project_dir", lambda payload: None)
    monkeypatch.setattr(cursor_mod, "read_active_project", lambda: None)
    monkeypatch.setattr(cursor_mod, "maybe_show_dashboard_hint", lambda: None)
    monkeypatch.setattr(cursor_mod, "write_unattributed_session", lambda _s: Path("x"))

    cursor_mod.handle_stop_hook()
    assert not session_file.exists(), "state was not cleared after successful persistence"


# ---------------------------------------------------------------------------
# P2 aggregated ledger trust labels merge correctly
# ---------------------------------------------------------------------------


def test_aggregated_trust_promotes_captured_plus_allocated_to_mixed(
    tmp_path: Path,
) -> None:
    """A January row with captured cost + a February row with allocated cost
    must aggregate to "mixed", not stay as "captured" from the first month."""
    from datetime import date

    from halyard.ai_plans import AiPlan
    from halyard.ledger import build_aggregated_ledger

    feb_plan = AiPlan(
        slug="feb-seat",
        tool="claude-code",
        billing="seat",
        monthly_usd=100.0,
        starts_on=date(2026, 2, 1),
        ends_on=date(2026, 2, 28),
    )
    jan_direct = AiSession(
        start=datetime(2026, 1, 15, 9, 0),
        end=datetime(2026, 1, 15, 10, 0),
        tool="anthropic-api",  # not matched by feb_plan
        model="opus-4",
        input_tokens=100,
        output_tokens=50,
        cost_usd=4.20,
        project="acme:web",
    )
    feb_seat = AiSession(
        start=datetime(2026, 2, 15, 9, 0),
        end=datetime(2026, 2, 15, 10, 0),
        tool="claude-code",  # matched by feb_plan
        model="opus-4",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.0,
        project="acme:web",
    )
    summary = build_aggregated_ledger([jan_direct, feb_seat], [feb_plan], [], period_label="2026")
    acme = next(e for e in summary.entries if e.project == "acme:web")
    assert acme.direct_usd > 0
    assert acme.allocated_usd > 0
    assert acme.trust == "mixed", f"expected mixed, got {acme.trust!r}"


# ---------------------------------------------------------------------------
# P2 rate-history structural parsing
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
            "GIT_AUTHOR_DATE": "2026-06-01T10:00:00",
            "GIT_COMMITTER_DATE": "2026-06-01T10:00:00",
            "PATH": "/usr/bin:/bin",
        },
    )


def test_rate_history_handles_wide_slug_to_rate_gap(tmp_path: Path) -> None:
    """A client with several fields between `slug` and `hourly_rate` (>3
    diff-context lines) used to silently lose rate-only commits. The
    structural parser doesn't depend on diff geometry, so it stays
    consistent regardless of field count."""
    _git(["init", "-q"], tmp_path)
    clients = tmp_path / "clients.toml"
    clients.write_text(
        "[[client]]\n"
        'slug = "acme"\n'
        'name = "Acme Corp"\n'
        'email = "billing@acme.example"\n'
        'address = "1 Big Tower"\n'
        'notes = "primary"\n'
        'tax_id = "EU1234"\n'
        "default_terms = 30\n"
        "hourly_rate = 100.0\n",
        encoding="utf-8",
    )
    _git(["add", "clients.toml"], tmp_path)
    _git(["commit", "-q", "-m", "initial"], tmp_path)

    # Rate-only change with the slug ~7 lines away from hourly_rate.
    clients.write_text(
        "[[client]]\n"
        'slug = "acme"\n'
        'name = "Acme Corp"\n'
        'email = "billing@acme.example"\n'
        'address = "1 Big Tower"\n'
        'notes = "primary"\n'
        'tax_id = "EU1234"\n'
        "default_terms = 30\n"
        "hourly_rate = 150.0\n",
        encoding="utf-8",
    )
    _git(["add", "clients.toml"], tmp_path)
    _git(["commit", "-q", "-m", "raise rate"], tmp_path)

    from halyard.config_history import rate_history_from_git

    changes = rate_history_from_git(tmp_path)
    rates = sorted(c.rate for c in changes if c.client_slug == "acme")
    # The diff-only parser dropped the bump here; the structural parser
    # captures both rates.
    assert rates == [100.0, 150.0], f"expected [100, 150], got {rates}"


def test_rate_history_ignores_commits_without_clients_toml(tmp_path: Path) -> None:
    """A clean repo with no clients.toml history returns []."""
    _git(["init", "-q"], tmp_path)
    (tmp_path / "README.md").write_text("hi\n", encoding="utf-8")
    _git(["add", "README.md"], tmp_path)
    _git(["commit", "-q", "-m", "no clients.toml"], tmp_path)

    from halyard.config_history import rate_history_from_git

    assert rate_history_from_git(tmp_path) == []


def test_rate_history_skips_malformed_historical_toml(tmp_path: Path) -> None:
    """A malformed historical clients.toml must not abort the whole audit."""
    _git(["init", "-q"], tmp_path)
    clients = tmp_path / "clients.toml"

    # First commit: well-formed.
    clients.write_text('[[client]]\nslug = "acme"\nhourly_rate = 100.0\n', encoding="utf-8")
    _git(["add", "clients.toml"], tmp_path)
    _git(["commit", "-q", "-m", "ok"], tmp_path)

    # Second commit: malformed.
    clients.write_text("not [valid toml at all\n", encoding="utf-8")
    _git(["add", "clients.toml"], tmp_path)
    _git(["commit", "-q", "-m", "broken"], tmp_path)

    # Third commit: well-formed again with a new rate.
    clients.write_text('[[client]]\nslug = "acme"\nhourly_rate = 150.0\n', encoding="utf-8")
    _git(["add", "clients.toml"], tmp_path)
    _git(["commit", "-q", "-m", "fixed + raise"], tmp_path)

    from halyard.config_history import rate_history_from_git

    rates = sorted(c.rate for c in rate_history_from_git(tmp_path))
    # Both well-formed snapshots contribute; the broken middle commit is
    # skipped without aborting.
    assert rates == [100.0, 150.0]


# ---------------------------------------------------------------------------
# P2 log_agent branch filter uses first-class field
# ---------------------------------------------------------------------------


def test_log_agent_branch_filter_matches_first_class_branch() -> None:
    """A session populating only `AiSession.branch` (no legacy tag) must
    still match `--branch <name>`. Before the fix the filter only checked
    `tags`, dropping every modern session."""
    from halyard.log_agent import LogQueryFilters, _filter_sessions

    modern = AiSession(
        start=datetime(2026, 6, 1, 9, 0),
        end=datetime(2026, 6, 1, 10, 0),
        tool="claude-code",
        model="opus-4",
        input_tokens=10,
        output_tokens=10,
        cost_usd=1.0,
        project="acme:web",
        branch="feature/x",
    )
    legacy = AiSession(
        start=datetime(2026, 6, 1, 9, 0),
        end=datetime(2026, 6, 1, 10, 0),
        tool="claude-code",
        model="opus-4",
        input_tokens=10,
        output_tokens=10,
        cost_usd=1.0,
        project="acme:web",
        tags=["branch:feature/x"],
    )
    unrelated = AiSession(
        start=datetime(2026, 6, 1, 9, 0),
        end=datetime(2026, 6, 1, 10, 0),
        tool="claude-code",
        model="opus-4",
        input_tokens=10,
        output_tokens=10,
        cost_usd=1.0,
        project="acme:web",
        branch="feature/other",
    )
    filtered = _filter_sessions([modern, legacy, unrelated], LogQueryFilters(branch="feature/x"))
    assert modern in filtered
    assert legacy in filtered  # backward compatible
    assert unrelated not in filtered


# ---------------------------------------------------------------------------
# P3 docs / hints reference real commands
# ---------------------------------------------------------------------------


def test_dashboard_401_hint_no_phantom_bridge_command() -> None:
    """The 401 body must reference the real CLI, not the phantom command."""
    from halyard import dashboard

    source = Path(dashboard.__file__).read_text(encoding="utf-8")
    assert "`halyard bridge`" not in source
    # Mentions the actual subcommand.
    assert "`halyard dashboard" in source


def test_trust_model_docs_link_to_integrity_migrate_cli() -> None:
    """The recovery section must document the new CLI command."""
    docs = (Path(__file__).resolve().parent.parent / "docs" / "trust-model.md").read_text(
        encoding="utf-8"
    )
    assert "halyard config integrity-migrate" in docs
    # And no longer recommends the "set off, rewrite via timer, re-enable" trick
    # as the *only* documented reset path — it was wrong on its own (the floor
    # blocks reads under the orphan sidecar).
    assert "start/stop the timer" not in docs
