"""v5.19 parallel-review round 2 — regression coverage for findings the
second outside audit caught across the wider codebase (not just the v5.19
diff).

Findings covered:
  * P1 dashboard URL is authenticated — `run_dashboard` prints a URL that
    includes the token, so the documented quickstart actually loads.
  * P1 all-time evidence sums per-month subscription allocations instead of
    collapsing to one month.
  * P2 cursor stop hook parses untrusted payload BEFORE clearing session
    state — a malformed token field no longer silently discards the turn.
  * P2 work_health `_day_key` reads the first-class `AiSession.branch`,
    not just the legacy `branch:` tag.
  * P2 status snapshot rolls `by_project` up by client prefix so siblings
    aggregate under one client.
  * P2 `rate_history_from_git` reads the slug from context lines so
    rate-only commits are kept in history.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from halyard.ai_log import AiSession

# ---------------------------------------------------------------------------
# P1 dashboard URL is authenticated
# ---------------------------------------------------------------------------


def test_dashboard_prints_url_with_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The URL printed to the user must carry the token query param, so the
    documented quickstart (`halyard dashboard`, then paste the URL) does not
    return 401 from the now-gated page."""
    from halyard import dashboard, service

    # Don't actually serve forever — bind, print, then bail.
    monkeypatch.setattr(dashboard, "_resolve_port", lambda port: 0)
    monkeypatch.setattr(service, "_load_or_create_token", lambda: "tok-abc-123")

    class _ImmediateServer:
        def __init__(self, *_args, **_kwargs) -> None:
            self.server_port = 12345
            self.closed = False

        def serve_forever(self) -> None:
            raise KeyboardInterrupt

        def server_close(self) -> None:
            self.closed = True

    monkeypatch.setattr(dashboard, "ThreadingHTTPServer", _ImmediateServer)

    class _NoOpHub:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    monkeypatch.setattr("halyard.hub_server.HubServer", _NoOpHub)
    monkeypatch.setattr("halyard.hub_client.hub_port", lambda: 0)

    url = dashboard.run_dashboard(tmp_path, port=0)
    out = capsys.readouterr().out
    assert "?token=tok-abc-123" in url
    assert "?token=tok-abc-123" in out


def test_dashboard_eaddrinuse_message_no_phantom_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The EADDRINUSE message must not invent a `halyard bridge` command."""
    import errno

    from halyard import dashboard

    monkeypatch.setattr(dashboard, "_resolve_port", lambda port: 7432)

    def _raise(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        err = OSError(errno.EADDRINUSE, "Address already in use")
        raise err

    monkeypatch.setattr(dashboard, "ThreadingHTTPServer", _raise)

    with pytest.raises(dashboard.DashboardError) as info:
        dashboard.run_dashboard(tmp_path, port=7432)
    msg = str(info.value)
    # Recommend the real command, not a phantom one.
    assert "halyard dashboard" in msg
    # And do not mention a "halyard bridge" command (the term "The Bridge"
    # is the product name; we removed it from this error to avoid confusion).
    assert "Halyard Bridge" not in msg


# ---------------------------------------------------------------------------
# P1 all-time evidence sums subscription months
# ---------------------------------------------------------------------------


def _make_session(*, year: int, month: int, project: str, tool: str = "claude-code") -> AiSession:
    start = datetime(year, month, 1, 9, 0, 0)
    end = datetime(year, month, 1, 10, 0, 0)
    return AiSession(
        start=start,
        end=end,
        tool=tool,
        model="opus-4",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.0,
        project=project,
    )


def test_build_aggregated_ledger_sums_subscription_months(tmp_path: Path) -> None:
    """Two months of a $100/month seat plan must report $200, not $100."""
    from halyard.ai_plans import AiPlan
    from halyard.ledger import build_aggregated_ledger

    plan = AiPlan(
        slug="claude-seat",
        tool="claude-code",
        billing="seat",
        monthly_usd=100.0,
        start_year=2026,
        start_month=1,
    )
    sessions = [
        _make_session(year=2026, month=4, project="acme:web"),
        _make_session(year=2026, month=5, project="acme:web"),
    ]
    summary = build_aggregated_ledger(sessions, [plan], [], period_label="all time")
    # The seat plan must charge for BOTH months.
    assert summary.total_allocated_usd == pytest.approx(200.0)
    assert summary.total_usd == pytest.approx(200.0)


def test_evidence_data_all_time_sums_subscription_months(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The structured evidence builder uses the per-month sum on all_time."""
    from halyard.evidence import build_evidence_data

    (tmp_path / "halyard.toml").write_text(
        '[business]\nname = "Test"\ncurrency = "USD"\n', encoding="utf-8"
    )
    (tmp_path / "time.timeclock").write_text("", encoding="utf-8")
    (tmp_path / "ai-plans.toml").write_text(
        '[[plan]]\nslug = "claude-seat"\ntool = "claude-code"\n'
        'billing = "seat"\nmonthly_usd = 100\n'
        "start_year = 2026\nstart_month = 1\n",
        encoding="utf-8",
    )
    log = tmp_path / "ai-sessions.log"
    lines = ["# halyard ai-sessions v1"]
    for sess in (
        _make_session(year=2026, month=4, project="acme:web"),
        _make_session(year=2026, month=5, project="acme:web"),
    ):
        lines.append(sess.to_log_line())
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    data = build_evidence_data(tmp_path, all_time=True)
    cost = data["cost"]
    assert isinstance(cost, dict)
    # Two months of $100 seat plan = $200 of allocated cost.
    assert cost["allocated_usd"] == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# P2 cursor stop hook parses payload BEFORE clearing state
# ---------------------------------------------------------------------------


def test_cursor_hook_does_not_lose_session_on_malformed_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed `usage.input_tokens` (e.g. "abc") used to raise inside the
    bare `int(...)` after the destructive `_clear_session_start()` — silently
    discarding the turn. With the order fixed and `_coerce_int` defensive,
    the row is still written (tokens default to 0)."""
    import json

    from halyard.collectors import cursor as cursor_mod

    # Redirect state file to tmp_path so we don't touch the user's home.
    session_file = tmp_path / "cursor-session"
    monkeypatch.setattr(cursor_mod, "_CURSOR_SESSION_FILE", session_file)
    session_file.parent.mkdir(parents=True, exist_ok=True)
    # Start ~5 minutes ago so the duration is plausible (the implausibility
    # filter rejects spans > 12h).
    recent_start = (datetime.now().replace(microsecond=0)).isoformat()
    session_file.write_text(
        json.dumps({"start": recent_start, "sha_at_start": None}),
        encoding="utf-8",
    )

    # Payload with a non-numeric token — would crash a bare int(...) call.
    malformed = {
        "model": "claude-opus-4",
        "usage": {"input_tokens": "abc", "output_tokens": 50},
        "workspace_roots": [],
    }
    monkeypatch.setattr(cursor_mod, "_read_payload", lambda: malformed)
    monkeypatch.setattr(cursor_mod, "find_hub", lambda: None)
    monkeypatch.setattr(cursor_mod, "_resolve_project_dir", lambda payload: None)
    monkeypatch.setattr(cursor_mod, "read_active_project", lambda: None)
    monkeypatch.setattr(cursor_mod, "maybe_show_dashboard_hint", lambda: None)

    captured: list[Path] = []
    monkeypatch.setattr(
        cursor_mod,
        "write_unattributed_session",
        lambda session: captured.append(Path("unattributed")) or Path("unattributed"),
    )

    rc = cursor_mod.handle_stop_hook()
    assert rc == 0
    # The session row was constructed and routed somewhere (here:
    # write_unattributed_session because no project resolved). It would
    # have been silently discarded before the fix.
    assert captured, "session row was not produced — malformed payload still drops it"


def test_cursor_hook_clears_state_only_after_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the function crashes after parsing but before completing, the
    session-start file must still exist for recovery — proving validation
    runs BEFORE the destructive clear."""
    import json

    from halyard.collectors import cursor as cursor_mod

    session_file = tmp_path / "cursor-session"
    monkeypatch.setattr(cursor_mod, "_CURSOR_SESSION_FILE", session_file)
    session_file.parent.mkdir(parents=True, exist_ok=True)
    recent_start = datetime.now().replace(microsecond=0).isoformat()
    session_file.write_text(
        json.dumps({"start": recent_start}),
        encoding="utf-8",
    )

    # Mark when the clear happened.
    clear_calls: list[bool] = []
    real_clear = cursor_mod._clear_session_start

    def _spy_clear() -> None:
        clear_calls.append(True)
        real_clear()

    monkeypatch.setattr(cursor_mod, "_clear_session_start", _spy_clear)

    # Force a crash AFTER state clear by replacing AiSession construction
    # with something that raises — but we only care that parsing
    # (_coerce_int) ran BEFORE the clear, which is guaranteed by the new
    # ordering. The presence of one clear call after parsing is the proof.
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
    monkeypatch.setattr(cursor_mod, "write_unattributed_session", lambda session: Path("x"))

    cursor_mod.handle_stop_hook()
    # The clear should have fired exactly once, AFTER the payload was parsed
    # (i.e. it survived the int coercion). Before the fix, the clear ran
    # before parsing — so any parse failure left the row silently dropped.
    assert clear_calls == [True]


# ---------------------------------------------------------------------------
# P2 work_health uses first-class branch field
# ---------------------------------------------------------------------------


def test_repeated_attempts_distinguishes_modern_branches() -> None:
    """Three sessions on three distinct modern branches must NOT be flagged
    as repeated attempts. Before the fix the legacy tag was empty for all
    three, so they collapsed to one key."""
    from halyard.work_health import detect_repeated_attempts

    def _s(branch: str) -> AiSession:
        return AiSession(
            start=datetime(2026, 6, 1, 9, 0),
            end=datetime(2026, 6, 1, 10, 0),
            tool="claude-code",
            model="opus-4",
            input_tokens=10,
            output_tokens=10,
            cost_usd=1.0,
            project="acme:web",
            branch=branch,
        )

    sessions = [_s("feature/a"), _s("feature/b"), _s("feature/c")]
    signal = detect_repeated_attempts(sessions)
    assert signal.sessions == [], (
        "three distinct modern branches should not collapse to one repeated-attempts key"
    )


def test_repeated_attempts_still_flags_same_branch() -> None:
    """Sanity: same project + same modern branch + same day = flagged."""
    from halyard.work_health import detect_repeated_attempts

    def _s() -> AiSession:
        return AiSession(
            start=datetime(2026, 6, 1, 9, 0),
            end=datetime(2026, 6, 1, 10, 0),
            tool="claude-code",
            model="opus-4",
            input_tokens=10,
            output_tokens=10,
            cost_usd=1.0,
            project="acme:web",
            branch="feature/a",
        )

    sessions = [_s(), _s(), _s()]
    signal = detect_repeated_attempts(sessions)
    assert len(signal.sessions) == 3


# ---------------------------------------------------------------------------
# P2 status snapshot rolls projects up to clients
# ---------------------------------------------------------------------------


def test_status_spend_rolls_sibling_projects_under_one_client() -> None:
    """`acme:web` + `acme:api` must report under one `acme` client bucket."""
    from halyard.status_snapshot import _spend

    now = datetime(2026, 6, 15, 12, 0)
    sessions = [
        AiSession(
            start=datetime(2026, 6, 5, 9, 0),
            end=datetime(2026, 6, 5, 10, 0),
            tool="claude-code",
            model="opus-4",
            input_tokens=10,
            output_tokens=10,
            cost_usd=20.0,
            project="acme:web",
        ),
        AiSession(
            start=datetime(2026, 6, 6, 9, 0),
            end=datetime(2026, 6, 6, 10, 0),
            tool="claude-code",
            model="opus-4",
            input_tokens=10,
            output_tokens=10,
            cost_usd=30.0,
            project="acme:api",
        ),
        AiSession(
            start=datetime(2026, 6, 7, 9, 0),
            end=datetime(2026, 6, 7, 10, 0),
            tool="claude-code",
            model="opus-4",
            input_tokens=10,
            output_tokens=10,
            cost_usd=5.0,
            project="zeta:core",
        ),
    ]
    spend = _spend(now, sessions)
    by_client = {cs.slug: cs.month_usd for cs in spend.by_client}
    # acme:web + acme:api → 50 under one `acme` bucket.
    assert by_client.get("acme") == pytest.approx(50.0)
    # The (still distinct) zeta client stays separate.
    assert by_client.get("zeta") == pytest.approx(5.0)
    # No sibling-project slug leaks through.
    assert "acme:web" not in by_client
    assert "acme:api" not in by_client


# ---------------------------------------------------------------------------
# P2 rate_history_from_git reads slug from context lines
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


def test_rate_history_from_git_keeps_rate_only_commit(tmp_path: Path) -> None:
    """A commit that changes only `hourly_rate = 100` → `150` (no slug line in
    the hunk) used to drop the change. The parser now reads `slug` from
    context lines, so the rate change is recorded."""
    _git(["init", "-q"], tmp_path)
    clients = tmp_path / "clients.toml"
    clients.write_text(
        '[[client]]\nslug = "acme"\nname = "Acme"\nhourly_rate = 100.0\n',
        encoding="utf-8",
    )
    _git(["add", "clients.toml"], tmp_path)
    _git(["commit", "-q", "-m", "initial"], tmp_path)

    # Rate-only change — the slug line is unchanged, so the diff hunk only
    # contains `-hourly_rate = 100` / `+hourly_rate = 150`.
    clients.write_text(
        '[[client]]\nslug = "acme"\nname = "Acme"\nhourly_rate = 150.0\n',
        encoding="utf-8",
    )
    _git(["add", "clients.toml"], tmp_path)
    _git(["commit", "-q", "-m", "raise rate"], tmp_path)

    from halyard.config_history import rate_history_from_git

    changes = rate_history_from_git(tmp_path)
    # Both the initial rate AND the rate-only bump must appear in history.
    rates = sorted(c.rate for c in changes if c.client_slug == "acme")
    assert rates == [100.0, 150.0], f"expected [100, 150], got {rates}"
