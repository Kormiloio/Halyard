"""Tests for the Halyard Bridge dashboard."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.cli import app
from halyard.dashboard import render_dashboard

runner = CliRunner()


def _init_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n")
    (tmp_path / "time.timeclock").write_text("; time\n")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER)


def test_dashboard_command_registered() -> None:
    result = runner.invoke(app, ["dashboard", "--help"])

    assert result.exit_code == 0
    assert "dashboard" in result.output


def test_render_dashboard_shows_cockpit_and_session(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.01,
            project="acme:auth",
        ),
    )

    html = render_dashboard(tmp_path)

    assert "Halyard · The Bridge" in html
    assert "Recent AI Sessions" in html
    assert "Usage Analytics" in html
    assert "Favorite model" in html
    assert "acme:auth" in html
    assert "claude-sonnet-4-6" in html


def test_render_dashboard_shows_human_time(tmp_path: Path) -> None:
    _init_project(tmp_path)
    (tmp_path / "time.timeclock").write_text(
        "i 2026-05-07 09:00:00 acme:auth\no 2026-05-07 10:00:00\n"
    )

    html = render_dashboard(tmp_path)

    assert "Human Time" in html
    assert "Timeclock" in html
    assert "acme:auth" in html


def test_render_dashboard_health_column_with_tool_telemetry(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 8, 10, 0),
            end=datetime(2026, 5, 8, 10, 30),
            tool="gemini-cli",
            model="gemini-2.0-flash",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.0012,
            project="acme:auth",
            tool_calls=20,
            tool_errors=3,
            code_added=45,
            code_removed=12,
        ),
    )

    html = render_dashboard(tmp_path)

    assert "Health" in html
    assert "20c" in html
    assert "3e" in html
    assert "+45/-12" in html


def test_render_dashboard_health_column_no_telemetry(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 8, 10, 0),
            end=datetime(2026, 5, 8, 10, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.005,
            project="acme:auth",
        ),
    )

    html = render_dashboard(tmp_path)

    assert "Health" in html
    assert "—" in html


def test_render_dashboard_marks_unattributed_sessions(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="codex",
            model="codex-local",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0,
        ),
    )

    html = render_dashboard(tmp_path)

    assert "· · · — — — · · ·" in html
    assert "Sessions Adrift" in html
    assert "codex-local" in html


def test_costs_panel_api_sessions_show_captured(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.02,
            project="acme:auth",
            billing="api",
        ),
    )

    html = render_dashboard(tmp_path)

    assert "trust-captured" in html
    assert ">captured<" in html


def test_costs_panel_credits_sessions_show_allocated(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="cursor",
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0,
            credits=20.0,
            project="acme:auth",
            billing="credits",
        ),
    )

    html = render_dashboard(tmp_path)

    assert "trust-allocated" in html
    assert ">allocated<" in html


def test_costs_panel_zero_cost_no_credits_shows_missing(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="cursor",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0,
            project="acme:auth",
        ),
    )

    html = render_dashboard(tmp_path)

    assert "trust-missing" in html
    assert ">missing<" in html


def test_costs_panel_mixed_sessions_show_mixed(tmp_path: Path) -> None:
    _init_project(tmp_path)
    for billing, cost, credits in [("api", 0.02, None), ("credits", 0.0, 10.0)]:
        append_session(
            tmp_path,
            AiSession(
                start=datetime(2026, 5, 7, 10, 0),
                end=datetime(2026, 5, 7, 10, 30),
                tool="claude-code",
                model="claude-sonnet-4-6",
                input_tokens=500,
                output_tokens=200,
                cost_usd=cost,
                credits=credits,
                project="acme:auth",
                billing=billing,
            ),
        )

    html = render_dashboard(tmp_path)

    assert "trust-mixed" in html
    assert ">mixed<" in html


def test_costs_panel_no_plans_shows_note(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.01,
            project="acme:auth",
        ),
    )

    html = render_dashboard(tmp_path)

    assert "ai-plans.toml" in html
    assert "costs-note" in html


def test_costs_panel_unattributed_project_label(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.01,
        ),
    )

    html = render_dashboard(tmp_path)

    assert "(unattributed)" in html
    assert "trust-captured" in html


def test_panel_status_pills_no_sessions(tmp_path: Path) -> None:
    _init_project(tmp_path)

    html = render_dashboard(tmp_path)

    assert "no captures yet" in html
    assert "manifest clean" in html
    assert "no data" in html  # projects pill


def test_panel_status_sessions_pill_healthy(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.01,
            project="acme:auth",
        ),
    )

    html = render_dashboard(tmp_path)

    assert "pill-healthy" in html
    assert "1 captured" in html
    assert "1 project" in html


def test_panel_status_unattributed_warning(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.01,
        ),
    )

    html = render_dashboard(tmp_path)

    assert "pill-warning" in html
    assert "1 adrift" in html
    assert "all adrift" in html  # projects pill


def test_panel_status_costs_trust_pill_warning(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="cursor",
            model="gpt-4o",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.0,
            project="acme:auth",
        ),
    )

    html = render_dashboard(tmp_path)

    assert "1 missing" in html  # costs trust pill


# ---------------------------------------------------------------------------
# H-1: CSRF — Origin header validation on POST endpoints
# ---------------------------------------------------------------------------


_CSRF_TOKEN = "c" * 64  # fixed test token so auth doesn't interfere with CSRF checks


def _make_request(
    project_dir: Path,
    path: str,
    body: bytes,
    headers: dict[str, str],
) -> tuple[int, str]:
    """Spin up a real ThreadingHTTPServer, fire one POST, return (status, reason).

    Injects a fixed token and correct Host header by default so tests that
    exercise Origin/CSRF logic are not blocked by the host or token checks.
    Callers may override Host or omit Cookie to test those checks specifically.
    """
    import threading
    from http.server import ThreadingHTTPServer

    from halyard.dashboard import _handler_for

    handler_cls = _handler_for(project_dir, token=_CSRF_TOKEN)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_port

    status_box: list[int] = []
    reason_box: list[str] = []

    def _serve_one() -> None:
        server.handle_request()

    t = threading.Thread(target=_serve_one, daemon=True)
    t.start()

    import http.client

    # Default headers ensure Host + token are valid unless overridden by caller
    default_headers: dict[str, str] = {
        "Content-Length": str(len(body)),
        "Host": f"127.0.0.1:{port}",
        "Cookie": f"halyard_token={_CSRF_TOKEN}",
    }
    default_headers.update(headers)

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", path, body=body, headers=default_headers)
    resp = conn.getresponse()
    status_box.append(resp.status)
    reason_box.append(resp.reason)
    conn.close()
    server.server_close()
    t.join(timeout=2)

    return status_box[0], reason_box[0]


def test_csrf_rejects_cross_origin_post(tmp_path: Path) -> None:
    """A POST with a foreign Origin header must be rejected with 403."""
    _init_project(tmp_path)
    body = b"project=acme/auth"
    status, _reason = _make_request(
        tmp_path,
        "/api/start",
        body,
        {"Content-Type": "application/x-www-form-urlencoded", "Origin": "http://evil.example.com"},
    )
    assert status == 403


def test_csrf_allows_same_origin_post(tmp_path: Path) -> None:
    """A POST from the dashboard's own origin must be processed (not 403)."""
    _init_project(tmp_path)
    # Write a minimal timeclock file so the endpoint has something to work with
    (tmp_path / "time.timeclock").write_text("; timeclock\n")
    body = b"project=acme/auth"

    import http.client
    import threading
    from http.server import ThreadingHTTPServer

    from halyard.dashboard import _handler_for

    handler_cls = _handler_for(tmp_path, token=_CSRF_TOKEN)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_port

    results: list[int] = []

    def _serve_one() -> None:
        server.handle_request()

    t = threading.Thread(target=_serve_one, daemon=True)
    t.start()

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(
        "POST",
        "/api/start",
        body=body,
        headers={
            "Content-Length": str(len(body)),
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": f"127.0.0.1:{port}",
            "Cookie": f"halyard_token={_CSRF_TOKEN}",
            "Origin": f"http://127.0.0.1:{port}",
        },
    )
    resp = conn.getresponse()
    results.append(resp.status)
    conn.close()
    server.server_close()
    t.join(timeout=2)

    assert results[0] != 403


def test_csrf_allows_no_origin_post(tmp_path: Path) -> None:
    """A POST with no Origin header (curl/CLI) must not be blocked by the CSRF check."""
    _init_project(tmp_path)
    body = b"project=acme/auth"
    # No Origin header — default _make_request supplies Host + token
    status, _reason = _make_request(
        tmp_path,
        "/api/start",
        body,
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status != 403


# ---------------------------------------------------------------------------
# Security: Host validation on GET/HEAD
# ---------------------------------------------------------------------------


def _make_get_request(
    project_dir: Path,
    method: str = "GET",
    host_override: str | None = None,
) -> int:
    """Spin up a real server, fire one GET or HEAD, return status code."""
    import http.client
    import threading
    from http.server import ThreadingHTTPServer

    from halyard.dashboard import _handler_for

    handler_cls = _handler_for(project_dir, token="t" * 64)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_port

    def _serve_one() -> None:
        server.handle_request()

    t = threading.Thread(target=_serve_one, daemon=True)
    t.start()

    host_header = host_override if host_override is not None else f"127.0.0.1:{port}"
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, "/", headers={"Host": host_header})
    resp = conn.getresponse()
    status = resp.status
    conn.close()
    server.server_close()
    t.join(timeout=2)
    return status


def test_get_valid_host_127_returns_200(tmp_path: Path) -> None:
    _init_project(tmp_path)
    assert _make_get_request(tmp_path, "GET") == 200


def test_get_valid_host_localhost_returns_200(tmp_path: Path) -> None:
    _init_project(tmp_path)
    import http.client
    import threading
    from http.server import ThreadingHTTPServer

    from halyard.dashboard import _handler_for

    handler_cls = _handler_for(tmp_path, token="t" * 64)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_port

    def _serve() -> None:
        server.handle_request()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/", headers={"Host": f"localhost:{port}"})
    status = conn.getresponse().status
    conn.close()
    server.server_close()
    t.join(timeout=2)
    assert status == 200


def test_get_wrong_host_returns_400(tmp_path: Path) -> None:
    _init_project(tmp_path)
    assert _make_get_request(tmp_path, "GET", host_override="evil.example.com") == 400


def test_get_missing_host_returns_400(tmp_path: Path) -> None:
    _init_project(tmp_path)
    assert _make_get_request(tmp_path, "GET", host_override="") == 400


def test_head_valid_host_returns_200(tmp_path: Path) -> None:
    _init_project(tmp_path)
    assert _make_get_request(tmp_path, "HEAD") == 200


def test_head_wrong_host_returns_400(tmp_path: Path) -> None:
    _init_project(tmp_path)
    assert _make_get_request(tmp_path, "HEAD", host_override="evil.example.com") == 400


# ---------------------------------------------------------------------------
# Proof score
# ---------------------------------------------------------------------------


def _make_session(
    *,
    project: str | None = "acme:auth",
    input_tokens: int = 1000,
    tokens_available: bool = True,
) -> AiSession:
    s = AiSession(
        start=datetime(2026, 5, 9, 10, 0),
        end=datetime(2026, 5, 9, 10, 30),
        tool="claude-code",
        model="claude-sonnet-4-6",
        input_tokens=input_tokens,
        output_tokens=200,
        cost_usd=0.01,
        project=project,
    )
    s.tokens_available = tokens_available
    return s


def test_proof_score_empty_sessions() -> None:
    from halyard.dashboard import _proof_score

    score, cls = _proof_score([])
    assert score == 0
    assert cls == "proof-neutral"


def test_proof_score_fully_attributed_with_tokens() -> None:
    from halyard.dashboard import _proof_score

    sessions = [_make_session(project="acme:auth", tokens_available=True) for _ in range(5)]
    score, cls = _proof_score(sessions)
    assert score == 100
    assert cls == "proof-healthy"


def test_proof_score_zero_attribution() -> None:
    from halyard.dashboard import _proof_score

    sessions = [_make_session(project=None, tokens_available=True) for _ in range(5)]
    score, cls = _proof_score(sessions)
    assert score == 40  # 0*0.6 + 1*0.4 = 0.4 → 40
    assert cls == "proof-low"


def test_proof_score_boundary_healthy() -> None:
    from halyard.dashboard import _proof_score

    # 10 sessions: 10 attributed, 6 with tokens → 1*0.6 + 0.6*0.4 = 0.84 → 84
    sessions = [_make_session(tokens_available=(i < 6)) for i in range(10)]
    score, cls = _proof_score(sessions)
    assert score == 84
    assert cls == "proof-healthy"


def test_proof_score_warn_range() -> None:
    from halyard.dashboard import _proof_score

    # 10 sessions: 8 attributed, 5 with tokens → 0.8*0.6 + 0.5*0.4 = 0.68 → 68
    sessions = [
        _make_session(project="p" if i < 8 else None, tokens_available=(i < 5)) for i in range(10)
    ]
    score, cls = _proof_score(sessions)
    assert score == 68
    assert cls == "proof-warn"


def test_proof_score_low_range() -> None:
    from halyard.dashboard import _proof_score

    # 10 sessions: 3 attributed, 0 tokens → 0.3*0.6 + 0 = 0.18 → 18
    sessions = [
        _make_session(project="p" if i < 3 else None, tokens_available=False) for i in range(10)
    ]
    score, cls = _proof_score(sessions)
    assert score == 18
    assert cls == "proof-low"


# ---------------------------------------------------------------------------
# Current Voyage panel
# ---------------------------------------------------------------------------


def test_voyage_panel_idle_shows_at_anchor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from halyard import reports

    monkeypatch.setattr(reports, "_HALYARD_ACTIVE", tmp_path / "no-active")
    _init_project(tmp_path)
    html = render_dashboard(tmp_path)
    assert "At anchor" in html
    assert "Current Voyage · Web Dashboard" in html


def test_voyage_panel_idle_shows_proof_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard import reports

    monkeypatch.setattr(reports, "_HALYARD_ACTIVE", tmp_path / "no-active")
    _init_project(tmp_path)
    append_session(tmp_path, _make_session())
    html = render_dashboard(tmp_path)
    assert "Proof Score" in html


def test_voyage_panel_active_shows_making_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard.reports import _HALYARD_ACTIVE

    _init_project(tmp_path)
    _HALYARD_ACTIVE.parent.mkdir(parents=True, exist_ok=True)
    _HALYARD_ACTIVE.write_text(
        "timeclock=/tmp/t.timeclock\nslug=acme:auth\nstarted=2026-05-09 10:00:00\n"
    )
    try:
        html = render_dashboard(tmp_path)
        assert "Making Way" in html
        assert "acme:auth" in html
    finally:
        _HALYARD_ACTIVE.unlink(missing_ok=True)


def test_voyage_panel_adrift_hidden_when_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard import reports

    monkeypatch.setattr(reports, "_HALYARD_ACTIVE", tmp_path / "no-active")
    _init_project(tmp_path)
    append_session(tmp_path, _make_session(project="acme:auth"))
    html = render_dashboard(tmp_path)
    # voyage-col-warn only appears in HTML elements when adrift > 0;
    # CSS definition always adds one occurrence, so >1 means an element rendered
    assert html.count("voyage-col-warn") == 1  # only CSS, no element


def test_voyage_panel_adrift_shown_when_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard import reports

    monkeypatch.setattr(reports, "_HALYARD_ACTIVE", tmp_path / "no-active")
    _init_project(tmp_path)
    append_session(tmp_path, _make_session(project=None))
    html = render_dashboard(tmp_path)
    assert html.count("voyage-col-warn") > 1  # CSS definition + rendered element


def test_render_dashboard_title_is_the_bridge(tmp_path: Path) -> None:
    _init_project(tmp_path)
    html = render_dashboard(tmp_path)
    assert "Halyard · The Bridge" in html
    assert "Halyard Glass Cockpit" not in html
