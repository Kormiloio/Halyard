"""Tests for the local Glass Cockpit dashboard."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

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
    assert "Glass Cockpit" in result.output


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

    assert "Halyard Glass Cockpit" in html
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
