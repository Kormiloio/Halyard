"""Local Bridge dashboard server — Halyard's web command center."""

# ruff: noqa: E501

from __future__ import annotations

import html
import socket
import webbrowser
from collections.abc import Iterable
from contextlib import suppress
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal

from halyard.ai_log import AiSession
from halyard.ai_plans import read_ai_plans
from halyard.budget import BudgetStatus, budget_status
from halyard.ledger import LedgerSummary, build_ledger
from halyard.reports import (
    CostBucket,
    DashboardState,
    TimeBucket,
    build_dashboard_state,
    format_minutes,
    parse_timeclock,
)
from halyard.trust import aggregate_trust, session_trust
from halyard.usage import (
    ModelUsageBucket,
    ToolUsageBucket,
    UsageAnalytics,
    build_usage_analytics,
    compact_number,
)

DASHBOARD_PORT = 7432


def run_dashboard(
    project_dir: Path, *, port: int = DASHBOARD_PORT, open_browser: bool = False
) -> str:
    """Start the dashboard server and block until interrupted."""
    host = "127.0.0.1"
    server = ThreadingHTTPServer((host, _resolve_port(port)), _handler_for(project_dir))
    url = f"http://{host}:{server.server_port}/"
    print(f"Halyard · The Bridge: {url}")
    print("Press Ctrl-C to stop.")

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

    return url


UsageRangeOpt = Literal["all", "30d", "7d"]
UsageTabOpt = Literal["overview", "models"]


def render_dashboard(
    project_dir: Path,
    *,
    usage_range: UsageRangeOpt = "30d",
    usage_tab: UsageTabOpt = "overview",
) -> str:
    """Render the dashboard HTML for tests and the HTTP handler.

    ``usage_range`` controls the Usage Analytics window (7d/30d/all).
    ``usage_tab`` selects between the Overview panel and the per-day-by-
    model breakdown panel.
    """
    return _render_state(
        build_dashboard_state(project_dir),
        usage_range=usage_range,
        usage_tab=usage_tab,
    )


def _handler_for(project_dir: Path, token: str | None = None) -> type[BaseHTTPRequestHandler]:
    from halyard.service import _load_or_create_token

    _token: str = token if token is not None else _load_or_create_token()

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            server_port = self.server.server_port  # type: ignore[attr-defined]
            host = self.headers.get("Host", "")
            if host not in {f"127.0.0.1:{server_port}", f"localhost:{server_port}"}:
                self.send_error(HTTPStatus.BAD_REQUEST, "invalid Host header")
                return
            self._send_dashboard(include_body=True)

        def do_HEAD(self) -> None:
            server_port = self.server.server_port  # type: ignore[attr-defined]
            host = self.headers.get("Host", "")
            if host not in {f"127.0.0.1:{server_port}", f"localhost:{server_port}"}:
                self.send_error(HTTPStatus.BAD_REQUEST, "invalid Host header")
                return
            self._send_dashboard(include_body=False)

        def do_POST(self) -> None:
            from urllib.parse import parse_qs

            server_port = self.server.server_port  # type: ignore[attr-defined]

            # 2.3: Validate Host header — must be 127.0.0.1:<port> or localhost:<port>
            host = self.headers.get("Host", "")
            if host not in {f"127.0.0.1:{server_port}", f"localhost:{server_port}"}:
                self._send_json_error(HTTPStatus.BAD_REQUEST, "invalid Host header")
                return

            # 2.4 (H-1): CSRF guard — reject cross-origin POSTs.
            # Browsers always send Origin on cross-site form POSTs.
            # Curl/CLI calls with no Origin header are still permitted.
            origin = self.headers.get("Origin", "")
            referer = self.headers.get("Referer", "")
            allowed_origin = f"http://127.0.0.1:{server_port}"
            if origin and origin not in {allowed_origin, f"http://localhost:{server_port}"}:
                self._send_json_error(HTTPStatus.FORBIDDEN, "cross-origin POST not allowed")
                return
            if (
                not origin
                and referer
                and not referer.startswith(f"http://127.0.0.1:{server_port}/")
                and not referer.startswith(f"http://localhost:{server_port}/")
            ):
                # Validate Referer prefix when Origin is absent
                self._send_json_error(HTTPStatus.FORBIDDEN, "cross-origin POST not allowed")
                return

            # 2.7: Cap Content-Length to prevent large-body DoS
            raw_cl = self.headers.get("Content-Length", "0")
            try:
                content_length = int(raw_cl)
            except ValueError:
                content_length = 0
            if content_length > 8192:
                self._send_json_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body too large")
                return

            # 2.5: Validate token via Cookie or X-Halyard-Token header
            submitted_token = self._extract_token()
            if submitted_token != _token:
                self._send_json_error(HTTPStatus.UNAUTHORIZED, "missing or invalid token")
                return

            length = content_length
            body = self.rfile.read(length).decode(errors="replace") if length else ""
            params = {k: v[0] for k, v in parse_qs(body).items()}

            if self.path == "/api/start":
                slug = params.get("project", "").strip()
                if slug and "/" in slug and not slug.startswith("/") and not slug.endswith("/"):
                    # v2.17 task 5.5: delegate to shared start_timer; ignores
                    # TimerAlreadyRunning (dashboard silently no-ops on duplicate start)
                    from halyard.orchestration import TimerAlreadyRunning, start_timer

                    account = slug.replace("/", ":", 1)
                    with suppress(TimerAlreadyRunning):
                        start_timer(project_dir, account)

            elif self.path == "/api/stop":
                # v2.17 task 5.5: delegate to shared stop_timer
                from halyard.orchestration import stop_timer

                stop_timer(project_dir)
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/?stopped=1")
                self.end_headers()
                return

            elif self.path == "/api/voyage-refresh":
                from halyard.ai_log import parse_sessions
                from halyard.voyages import check_auto_complete

                all_sessions = parse_sessions(project_dir)
                sessions_by_project: dict[str, list[AiSession]] = {}
                for s in all_sessions:
                    if s.project:
                        sessions_by_project.setdefault(s.project, []).append(s)
                check_auto_complete(project_dir, sessions_by_project)

            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/")
            self.end_headers()

        def _send_dashboard(self, *, include_body: bool) -> None:
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(self.path)
            if parsed.path not in {"/", "/index.html"}:
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            qs = parse_qs(parsed.query)
            raw_range = (qs.get("range") or ["30d"])[0]
            raw_tab = (qs.get("tab") or ["overview"])[0]
            usage_range: UsageRangeOpt = (
                raw_range if raw_range in ("7d", "30d", "all") else "30d"  # type: ignore[assignment]
            )
            usage_tab: UsageTabOpt = (
                raw_tab if raw_tab in ("overview", "models") else "overview"  # type: ignore[assignment]
            )
            body = render_dashboard(
                project_dir, usage_range=usage_range, usage_tab=usage_tab
            ).encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            # 2.2: Set token cookie so the browser can authenticate POSTs.
            # HttpOnly prevents JS access; SameSite=Strict prevents CSRF.
            self.send_header(
                "Set-Cookie",
                f"halyard_token={_token}; Path=/; HttpOnly; SameSite=Strict",
            )
            self.end_headers()
            if include_body:
                self.wfile.write(body)

        def _extract_token(self) -> str:
            """Return the submitted token from Cookie or X-Halyard-Token header."""
            x_token = self.headers.get("X-Halyard-Token", "")
            if x_token:
                return x_token
            cookie_header = self.headers.get("Cookie", "")
            for part in cookie_header.split(";"):
                part = part.strip()
                if part.startswith("halyard_token="):
                    return part[len("halyard_token=") :]
            return ""

        def _send_json_error(self, status: HTTPStatus, reason: str) -> None:
            """Send a terse JSON error body with the given HTTP status."""
            import json as _json

            body = _json.dumps({"error": reason}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return DashboardHandler


def _resolve_port(port: int) -> int:
    if port:
        return port
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


_MORSE_TABLE: dict[str, str] = {
    "A": "·—",
    "B": "—···",
    "C": "—·—·",
    "D": "—··",
    "E": "·",
    "F": "··—·",
    "G": "——·",
    "H": "····",
    "I": "··",
    "J": "·———",
    "K": "—·—",
    "L": "·—··",
    "M": "——",
    "N": "—·",
    "O": "———",
    "P": "·——·",
    "Q": "——·—",
    "R": "·—·",
    "S": "···",
    "T": "—",
    "U": "··—",
    "V": "···—",
    "W": "·——",
    "X": "—··—",
    "Y": "—·——",
    "Z": "——··",
}


def _morse(text: str) -> str:
    """Encode text as Morse — symbols spaced within letters, double-space between letters."""
    return "  ".join(
        " ".join(_MORSE_TABLE[c] for c in w.upper() if c in _MORSE_TABLE) for w in text.split()
    )


def _proof_score(sessions: list[AiSession]) -> tuple[int, str]:
    """Return (score 0-100, css_class) representing client-ready confidence.

    Score = attribution_rate * 60% + token_capture_rate * 40%.
    css_class is one of: proof-healthy (>=80), proof-warn (60-79), proof-low (<60),
    proof-neutral (no sessions).
    """
    total = len(sessions)
    if total == 0:
        return 0, "proof-neutral"
    attributed = sum(1 for s in sessions if s.project)
    with_tokens = sum(1 for s in sessions if s.tokens_available)
    score = round((attributed / total * 0.6 + with_tokens / total * 0.4) * 100)
    if score >= 80:
        return score, "proof-healthy"
    if score >= 60:
        return score, "proof-warn"
    return score, "proof-low"


def _infer_voyage_stage(sessions: list[AiSession]) -> tuple[str, str, bool]:
    """Return (stage_label, icon, is_auto) inferred from all-time session history."""
    total = len(sessions)
    if total == 0:
        return "At anchor", "⚓", False
    attributed = sum(1 for s in sessions if s.project)
    attr_rate = attributed / total
    has_merged_pr = any(s.pr_state == "merged" for s in sessions if s.pr_state)
    has_pr = any(s.pr_ref for s in sessions)
    if total >= 50 and attr_rate >= 0.80 and has_merged_pr:
        return "Flying Colors", "⛵", True
    if total >= 30 and attr_rate >= 0.70 and has_pr:
        return "Rounding the Mark", "⛵", True
    if total >= 10 and attr_rate >= 0.50:
        return "Making Headway", "⛵", True
    return "Anchors Aweigh", "⚓", True


def _voyage_panel(state: DashboardState) -> str:
    """Current Voyage panel — the live work state shown at the top of The Bridge."""
    from datetime import datetime as _dt

    report = state.report
    timer = state.active_timer

    if timer is not None:
        eyebrow = "Current Voyage · Making Way"
        title = _e(timer.slug)
        timer_start: _dt | None = None
        if timer.started:
            with suppress(ValueError):
                timer_start = _dt.strptime(timer.started, "%Y-%m-%d %H:%M:%S")
        watch = [s for s in report.sessions if timer_start and s.start >= timer_start]
        total = len(watch)
        attributed = sum(1 for s in watch if s.project)
        watch_cost = sum(s.cost_usd for s in watch)
        adrift = total - attributed
        score, score_cls = _proof_score(watch)
        score_display = "—" if total == 0 else str(score)
        bar_pct = min(100, int(timer.elapsed_minutes / 90 * 100))
        manifest_label = f"{attributed}/{total} in manifest" if total else "no sessions yet"
        score_label = (
            "not underway"
            if total == 0
            else "client-ready"
            if score >= 80
            else "review needed"
            if score >= 60
            else "gaps present"
        )
        adrift_col = (
            f'<div class="voyage-col voyage-col-warn">'
            f'<span class="voyage-label">Adrift</span>'
            f'<span class="voyage-value proof-low">{adrift}</span>'
            f'<span class="voyage-sub">· · · — — — · · ·</span></div>'
            if adrift > 0
            else ""
        )
        body = f"""
        <div class="voyage-bar-outer"><div class="voyage-bar-fill" style="width:{bar_pct}%"></div></div>
        <div class="voyage-grid">
          <div class="voyage-col">
            <span class="voyage-label">Elapsed</span>
            <span class="voyage-value">{_e(timer.elapsed_label)}</span>
          </div>
          <div class="voyage-col">
            <span class="voyage-label">Sessions · this watch</span>
            <span class="voyage-value">{total}</span>
            <span class="voyage-sub">{_e(manifest_label)}</span>
          </div>
          <div class="voyage-col">
            <span class="voyage-label">Proof Score</span>
            <span class="voyage-value"><span class="{_e(score_cls)}">{score_display}%</span></span>
            <span class="voyage-sub">{_e(score_label)}</span>
          </div>
          <div class="voyage-col">
            <span class="voyage-label">Cost · this watch</span>
            <span class="voyage-value">${watch_cost:.4f}</span>
          </div>
          {adrift_col}
        </div>"""
    else:
        stage_label, stage_icon, is_auto = _infer_voyage_stage(state.all_sessions)
        eyebrow = "Current Voyage · auto" if is_auto else "Current Voyage · Web Dashboard"
        title = f"{stage_icon}  {stage_label}"
        sessions = report.sessions
        total = len(sessions)
        all_total = len(state.all_sessions)
        attributed_all = sum(1 for s in state.all_sessions if s.project)
        score, score_cls = _proof_score(sessions)
        score_display = "—" if total == 0 else str(score)
        score_label = (
            "not underway"
            if total == 0
            else "client-ready"
            if score >= 80
            else "review needed"
            if score >= 60
            else "gaps present"
        )
        attr_pct = round(attributed_all / all_total * 100) if all_total > 0 else 0
        with_tokens = sum(1 for s in sessions if s.tokens_available)
        token_pct = round(with_tokens / total * 100) if total > 0 else 0
        fix_prompt = (
            '<span class="voyage-sub proof-low">run halyard assign-unattributed</span>'
            if attr_pct < 100 and all_total > 0
            else ""
        )
        adrift = report.unattributed_count
        adrift_col = (
            f'<div class="voyage-col voyage-col-warn">'
            f'<span class="voyage-label">Adrift</span>'
            f'<span class="voyage-value proof-low">{adrift}</span>'
            f'<span class="voyage-sub">· · · — — — · · ·</span></div>'
            if adrift > 0
            else ""
        )
        body = f"""
        <div class="voyage-grid">
          <div class="voyage-col">
            <span class="voyage-label">Sessions · this month</span>
            <span class="voyage-value">{total}</span>
            <span class="voyage-sub">{all_total} all time</span>
          </div>
          <div class="voyage-col">
            <span class="voyage-label">Proof Score</span>
            <span class="voyage-value"><span class="{_e(score_cls)}">{score_display}%</span></span>
            <span class="voyage-sub">attr {attr_pct}% · tokens {token_pct}%</span>
            {fix_prompt}
          </div>
          <div class="voyage-col">
            <span class="voyage-label">Cost · this month</span>
            <span class="voyage-value">${report.total_cost:.2f}</span>
          </div>
          {adrift_col}
        </div>"""

    return f"""
      <article class="panel span-12">
        <div class="panel-head">
          <div>
            <p class="eyebrow">{_e(eyebrow)}</p>
            <h2>{title}</h2>
          </div>
        </div>
        {body}
      </article>"""


def _render_state(
    state: DashboardState,
    *,
    usage_range: UsageRangeOpt = "30d",
    usage_tab: UsageTabOpt = "overview",
) -> str:
    report = state.report
    human_time = state.human_time
    latest = state.latest_session
    health_level = _overall_health(state)
    usage = build_usage_analytics(
        state.all_sessions, range_key=usage_range, now=state.generated_at
    )

    # Budget data
    budgets = budget_status()

    # Ledger / trust data
    plans = read_ai_plans(state.project_dir)
    tc_entries = parse_timeclock(state.project_dir / "time.timeclock")
    now = state.generated_at
    ledger = (
        build_ledger(report.sessions, plans, tc_entries, year=now.year, month=now.month)
        if plans
        else None
    )

    # --- per-panel status pills ---
    session_count = len(report.sessions)
    sessions_pill = (
        _panel_status_pill(f"{session_count} captured", "healthy")
        if session_count
        else _panel_status_pill("no captures yet", "muted")
    )

    unattr_count = report.unattributed_count
    unattr_pill = (
        _panel_status_pill(f"{unattr_count} adrift", "warning")
        if unattr_count
        else _panel_status_pill("manifest clean", "healthy")
    )

    time_state = "healthy" if human_time.month_minutes > 0 else "muted"
    time_pill = _panel_status_pill(
        format_minutes(human_time.month_minutes) + " this month", time_state
    )

    proj_count = len([b for b in report.by_project if b.label != "(unattributed)"])
    if session_count == 0:
        projects_pill = _panel_status_pill("no data", "muted")
    elif proj_count == 0:
        projects_pill = _panel_status_pill("all adrift", "warning")
    else:
        label = "project" if proj_count == 1 else "projects"
        projects_pill = _panel_status_pill(f"{proj_count} {label}", "healthy")

    model_count = len(list(report.by_model))
    models_pill = (
        _panel_status_pill(f"{model_count} model{'s' if model_count != 1 else ''}", "muted")
        if model_count
        else ""
    )

    tool_count = len(list(report.by_tool))
    tools_pill = (
        _panel_status_pill(f"{tool_count} tool{'s' if tool_count != 1 else ''}", "muted")
        if tool_count
        else ""
    )

    budget_classes = [_budget_class(b.today_spend, b.today_limit) for b in budgets] + [
        _budget_class(b.month_spend, b.month_limit) for b in budgets
    ]
    if not budgets:
        budget_pill = _panel_status_pill("no limits set", "muted")
    elif "over" in budget_classes:
        budget_pill = _panel_status_pill("over limit", "error")
    elif "high" in budget_classes or "warn" in budget_classes:
        budget_pill = _panel_status_pill("near limit", "warning")
    else:
        budget_pill = _panel_status_pill("on track", "healthy")

    if session_count == 0:
        costs_trust_pill = _panel_status_pill("no sessions", "muted")
    else:
        missing_trust = sum(1 for s in report.sessions if session_trust(s) == "missing")
        if missing_trust:
            costs_trust_pill = _panel_status_pill(f"{missing_trust} missing", "warning")
        else:
            costs_trust_pill = _panel_status_pill("all captured", "healthy")

    trail_month_sessions = [
        s
        for s in report.sessions
        if s.start.date().year == now.year and s.start.date().month == now.month
    ]
    trail_active_days = len({s.start.date() for s in trail_month_sessions})
    trail_pill = _panel_status_pill(
        f"{trail_active_days} active day{'s' if trail_active_days != 1 else ''}",
        "muted" if trail_active_days else "warning",
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="10">
  <title>Halyard · The Bridge</title>
  <style>{_CSS}</style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark" id="brand-mark">
          <svg viewBox="0 0 24 24" role="img" aria-label="Halyard">
            <circle cx="12" cy="5" r="3"/>
            <path d="M12 8v14"/>
            <path d="M5 12H2a10 10 0 0 0 20 0h-3"/>
          </svg>
        </div>
        <div>
          <p class="eyebrow">Halyard · The Bridge · Web Dashboard</p>
          <h1>{_e(state.project_dir.name)}</h1>
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:10px;">
        <button id="theme-toggle" class="theme-toggle" aria-label="Toggle light/dark mode">☀️</button>
        <div class="status status-{health_level}">{_e(health_level.title())}</div>
      </div>
    </header>

    <section class="metrics" aria-label="Today summary">
      {_timer_metric(state.active_timer)}
      {
        _metric(
            "Human Time",
            format_minutes(human_time.today_minutes or human_time.presence_minutes),
            "today"
            if human_time.today_minutes > 0
            else ("today · auto-detected" if human_time.presence_minutes > 0 else "today"),
            "normal",
        )
    }
      {_metric("AI Sessions", str(len(report.sessions)), report.period_label, "normal")}
      {
        _metric(
            "AI Cost",
            f"${report.total_cost:.2f}"
            if report.total_cost > 0
            else (
                f"~${ledger.total_allocated_usd:.2f}"
                if ledger is not None and ledger.total_allocated_usd > 0
                else "$0.00"
            ),
            "captured API cost"
            if report.total_cost > 0
            else (
                "allocated from plans"
                if ledger is not None and ledger.total_allocated_usd > 0
                else "captured API cost"
            ),
            "money",
        )
    }
    </section>

    <section class="grid">
      {_voyage_panel(state)}
      {_captains_quarters_panel(state.project_dir, report.sessions)}
      {_friends_panel(state.project_dir, report.sessions)}

      <article class="panel span-12">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Usage Analytics</p>
            <h2>{"Models" if usage_tab == "models" else "Overview"}</h2>
          </div>
          <div class="pill-group">
            {_range_control(usage_range, usage_tab)}
            {_tab_control(usage_tab, usage_range)}
            <span class="pill">{_e(usage.summary.active_days)} active days</span>
          </div>
        </div>
        {_usage_panel(usage) if usage_tab == "overview" else _usage_models_panel(usage)}
      </article>

      <article class="panel span-12">
        <div class="panel-head">
          <div>
            <p class="eyebrow">v3.0</p>
            <h2>Leverage</h2>
          </div>
          <div class="pill-group"><span class="pill">30d</span></div>
        </div>
        {_leverage_panel(state.all_sessions, state.generated_at)}
      </article>

      <article class="panel span-7">
        <div class="panel-head">
          <div>
            <p class="eyebrow">{_morse("LOG")}</p>
            <h2>Recent AI Sessions</h2>
          </div>
          <div class="pill-group">{sessions_pill}<span class="pill">↺ 10s</span></div>
        </div>
        {_sessions_table(report.sessions)}
      </article>

      <article class="panel span-5">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Collector State</p>
            <h2>Health</h2>
          </div>
        </div>
        <div class="health-list">{
        "".join(_health_row(check.label, check.status, check.detail) for check in state.health)
    }</div>
      </article>

      <article class="panel span-12 attention-{_e("on" if report.unattributed_count else "off")}">
        <div class="panel-head">
          <div>
            <p class="eyebrow">· · · — — — · · ·</p>
            <h2>Sessions Adrift</h2>
          </div>
          {unattr_pill}
        </div>
        {_unattributed_table(report.unattributed_sessions)}
      </article>

      <article class="panel span-12">
        <div class="panel-head">
          <div>
            <p class="eyebrow">{_morse("WAKE")}</p>
            <h2>Wake · {_e(now.strftime("%B %Y"))}</h2>
          </div>
          <div class="pill-group">{trail_pill}</div>
        </div>
        {_trail_heatmap_html(report.sessions, now)}
      </article>

      <article class="panel span-6">
        <div class="panel-head">
          <div>
            <p class="eyebrow">{_morse("TIME")}</p>
            <h2>Timeclock</h2>
          </div>
          {time_pill}
        </div>
        {_time_table(human_time.by_project)}
      </article>

      <article class="panel span-6">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Attribution</p>
            <h2>Projects</h2>
          </div>
          {projects_pill}
        </div>
        {_bucket_table(report.by_project, "Project")}
      </article>

      <article class="panel span-4">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Mix</p>
            <h2>Models</h2>
          </div>
          {models_pill}
        </div>
        {_model_table(report.by_model)}
      </article>

      <article class="panel span-4">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Capture</p>
            <h2>Tools</h2>
          </div>
          {tools_pill}
        </div>
        {_tool_table(report.by_tool_usage)}
      </article>

      <article class="panel span-4">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Spend Limits</p>
            <h2>Budget</h2>
          </div>
          {budget_pill}
        </div>
        {_budget_panel(budgets)}
      </article>

      <article class="panel span-12">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Cost Allocation</p>
            <h2>Costs</h2>
          </div>
          <div class="pill-group"><span class="pill">{_e(report.period_label)}</span>{
        costs_trust_pill
    }</div>
        </div>
        {_costs_panel(ledger, report.by_project, report.sessions)}
      </article>
    </section>

    <footer>
      Latest session: {_latest_label(latest)} · Generated {
        _e(state.generated_at.strftime("%Y-%m-%d %H:%M:%S"))
    }
    </footer>
  </main>
  {_celebration_script()}
  {_easter_egg_script()}
</body>
</html>"""


def _captains_quarters_panel(project_dir: Path, sessions: list[AiSession]) -> str:
    from halyard.achievements import RANKS, ServiceRecord, build_service_record

    record: ServiceRecord = build_service_record(project_dir, sessions)
    rank = record.rank

    # Rank progress bar
    if record.next_rank:
        earned = record.attributed_sessions
        target = record.next_rank.sessions_required
        pct = min(100, round(100 * earned / max(target, 1)))
        next_label = _e(record.next_rank.name)
        progress_html = f"""
          <div class="cq-progress-outer">
            <div class="cq-progress-fill" style="width:{pct}%"></div>
          </div>
          <p class="cq-sub">{earned} / {target} attributed sessions → {next_label}</p>"""
    else:
        progress_html = '<p class="cq-sub" style="color:var(--amber)">✦ Highest rank achieved</p>'

    # Rank row
    rank_html = f"""
      <div class="cq-rank">
        <span class="cq-rank-icon">{_e(rank.icon)}</span>
        <div>
          <p class="cq-rank-name">{_e(rank.name)}</p>
          <p class="cq-rank-flavor">{_e(rank.flavor)}</p>
        </div>
      </div>
      {progress_html}"""

    # Stripes
    stripe_count = min(4, record.watch_streak // 7)
    stripes = "▐" * stripe_count if stripe_count else "—"
    gold = ' <span style="color:var(--amber)">✦ gold</span>' if record.gold_stripe_earned else ""
    stripes_html = f"""
      <div class="cq-stripes">
        <span class="cq-stripe-bar">{_e(stripes)}{gold}</span>
        <span class="cq-sub">{record.watch_streak}-day streak · {record.clean_watches} clean watches</span>
      </div>"""

    # Passport
    passport_items = "".join(
        f'<li class="cq-stamp" title="{_e(s.tool)}">'
        f'<span class="cq-stamp-icon">{_e(s.icon)}</span>'
        f'<span class="cq-stamp-name">{_e(s.name)}</span>'
        f"</li>"
        for s in record.passport
    )
    passport_html = (
        f'<ul class="cq-stamps">{passport_items}</ul>'
        if passport_items
        else '<p class="cq-sub cq-empty">No ports of call yet.</p>'
    )

    # Medals
    medal_items = "".join(
        f'<li class="cq-medal" title="{_e(m.detail)}">'
        f'<span class="cq-medal-icon">{_e(m.icon)}</span>'
        f'<span class="cq-medal-name">{_e(m.name)}</span>'
        f'<span class="cq-medal-desc">{_e(m.description)}</span>'
        f"</li>"
        for m in record.earned_medals
    )
    medals_html = (
        f'<ul class="cq-medals">{medal_items}</ul>'
        if medal_items
        else '<p class="cq-sub cq-empty">No medals yet — complete watches to start earning honors.</p>'
    )

    # Rank ladder (mini)
    ladder_items = ""
    for r in RANKS[1:]:
        active = "cq-ladder-active" if r.level == rank.level else ""
        ladder_items += (
            f'<li class="cq-ladder-item {active}">{_e(r.icon)} <span>{_e(r.short)}</span></li>'
        )
    ladder_html = f'<ol class="cq-ladder">{ladder_items}</ol>'

    proof_cls = (
        "proof-healthy"
        if record.proof_score >= 80
        else ("proof-warn" if record.proof_score >= 60 else "proof-low")
    )
    proof_html = f'<span class="{proof_cls}">{record.proof_score}%</span>'

    return f"""
      <article class="panel span-12">
        <div class="panel-head">
          <div>
            <p class="eyebrow">⚓ Captain's Quarters</p>
            <h2>Service Record</h2>
          </div>
          <div class="pill-group">
            <span class="pill">{_e(rank.icon)} {_e(rank.name)}</span>
            <span class="pill">Proof {proof_html}</span>
          </div>
        </div>
        <div class="cq-body">
          <div class="cq-main">
            {rank_html}
            {stripes_html}
          </div>
          <div class="cq-passport-col">
            <p class="cq-section-label">Passport · Ports of Call</p>
            {passport_html}
          </div>
          <div class="cq-medals-col">
            <p class="cq-section-label">Medals</p>
            {medals_html}
          </div>
          <div class="cq-ladder-col">
            <p class="cq-section-label">All Ranks</p>
            {ladder_html}
          </div>
        </div>
      </article>"""


def _friends_panel(project_dir: Path, sessions: list[AiSession]) -> str:
    """Friends of the Sea — voyage stage cards for every tracked project."""
    from halyard.voyages import STAGE_LABELS, build_voyage_summaries

    sessions_by_project: dict[str, list[AiSession]] = {}
    for s in sessions:
        if s.project:
            sessions_by_project.setdefault(s.project, []).append(s)

    summaries = build_voyage_summaries(project_dir, sessions_by_project)

    if not summaries:
        return ""

    cards = ""
    for v in summaries:
        label = STAGE_LABELS.get(v.stage, v.stage)
        if v.stage == "moored":
            creature = _e(v.creature or "🦭")
            trait = _e(v.creature_trait or "")
            cards += f"""
            <div class="friend-card friend-moored">
              <span class="friend-creature">{creature}</span>
              <span class="friend-slug">{_e(v.slug)}</span>
              <span class="friend-stage">{_e(label)}</span>
              <span class="friend-trait">{trait}</span>
            </div>"""
        else:
            pct = v.progress_pct
            stage_cls = f"friend-stage-{_e(v.stage)}"
            cards += f"""
            <div class="friend-card friend-active">
              <span class="friend-slug">{_e(v.slug)}</span>
              <span class="friend-stage {stage_cls}">{_e(label)}</span>
              <div class="friend-progress-outer">
                <div class="friend-progress-fill" style="width:{pct}%"></div>
              </div>
              <span class="friend-count">{v.session_count} / {v.target_sessions}</span>
            </div>"""

    moored_count = sum(1 for v in summaries if v.stage == "moored")
    return f"""
      <article class="panel span-12">
        <div class="panel-head">
          <div>
            <p class="eyebrow">⛵ Friends of the Sea</p>
            <h2>Voyage Roster</h2>
          </div>
          <div class="pill-group">
            <span class="pill">{len(summaries)} project{"s" if len(summaries) != 1 else ""}</span>
            <span class="pill">{moored_count} moored</span>
            <form method="post" action="/api/voyage-refresh" style="display:inline">
              <button class="btn btn-sm" type="submit" title="Check for auto-completion">⚓ Refresh</button>
            </form>
          </div>
        </div>
        <div class="friends-grid">{cards}
        </div>
      </article>"""


def _overall_health(state: DashboardState) -> str:
    statuses = {check.status for check in state.health}
    if "error" in statuses:
        return "error"
    if "warning" in statuses:
        return "warning"
    return "healthy"


def _metric(label: str, value: str, detail: str, tone: str) -> str:
    return f"""
      <article class="metric metric-{tone}">
        <span>{_e(label)}</span>
        <strong>{_e(value)}</strong>
        <small>{_e(detail)}</small>
      </article>
    """


def _timer_metric(active_timer: object) -> str:
    from halyard.reports import ActiveTimer

    timer = active_timer if isinstance(active_timer, ActiveTimer) else None
    if timer:
        controls = (
            f'<form class="timer-form" method="post" action="/api/stop">'
            f'<button class="btn btn-stop" type="submit">&#9632; Stop {_e(timer.slug)}</button>'
            f"</form>"
        )
        value = _e(timer.slug)
        detail = _e(f"{timer.elapsed_label} elapsed")
    else:
        controls = (
            '<form class="timer-form" method="post" action="/api/start">'
            '<input class="timer-input" name="project" placeholder="client/project" required>'
            '<button class="btn btn-start" type="submit">&#9654; Start</button>'
            "</form>"
        )
        value = "⚓  at anchor"
        detail = ""

    return f"""
      <article class="metric metric-focus">
        <span>Active Project</span>
        <strong>{value}</strong>
        <small>{detail}</small>
        {controls}
      </article>
    """


def _sessions_table(sessions: Iterable[AiSession]) -> str:
    rows = []
    deduped = [s for s in sessions if s.end > s.start]
    # Always include the most recent session from each tool so e.g. Codex
    # is never buried by a flood of Claude Code sessions.
    latest_per_tool: dict[str, AiSession] = {}
    for s in deduped:
        if s.tool not in latest_per_tool or s.end > latest_per_tool[s.tool].end:
            latest_per_tool[s.tool] = s
    recent = deduped[-25:]
    recent_ids = {id(r) for r in recent}
    pinned_missing = [s for s in latest_per_tool.values() if id(s) not in recent_ids]
    combined = sorted(recent + pinned_missing, key=lambda s: s.end)[-25:]
    for session in combined[::-1]:
        css_key, emoji = _tool_icon(session.tool)
        dur = _duration_str(session.end - session.start)
        health = _health_badge(session)
        rows.append(
            "<tr>"
            f"<td>{_e(session.end.strftime('%H:%M'))}</td>"
            f"<td><span class='tool-icon tool-{_e(css_key)}'>{emoji}</span></td>"
            f"<td>{_e(session.project or '(unattributed)')}</td>"
            f"<td>{_e(session.model)}</td>"
            f"<td class='num'>{_e(dur)}</td>"
            f"<td class='num'>{session.input_tokens:,} / {session.output_tokens:,}</td>"
            f"<td class='num'>${session.cost_usd:.4f}</td>"
            f"<td class='num'>{health}</td>"
            "</tr>"
        )
    if not rows:
        return '<p class="empty">No AI sessions captured this period.<br>Start Claude Code, Cursor, or Gemini CLI in this directory.</p>'
    return (
        "<table><thead><tr><th>Time</th><th>Tool</th><th>Project</th><th>Model</th>"
        "<th>Dur</th><th>In / Out</th><th>Cost</th><th>Health</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _health_badge(session: AiSession) -> str:
    parts: list[str] = []
    if session.interaction_count is not None:
        parts.append(f"<span class='trust-captured'>{session.interaction_count}i</span>")
    elif session.interaction_data_available is False:
        parts.append("<span class='dim'>i n/a</span>")
    if session.files_touched_count is not None:
        parts.append(f"<span class='dim'>{session.files_touched_count}f</span>")
    if session.test_status:
        css = "trust-captured" if session.test_status == "pass" else "trust-unallocated"
        parts.append(f"<span class='{css}'>test:{_e(session.test_status)}</span>")
    if session.build_status:
        css = "trust-captured" if session.build_status == "pass" else "trust-unallocated"
        parts.append(f"<span class='{css}'>build:{_e(session.build_status)}</span>")
    if session.tool_calls is not None:
        calls = session.tool_calls
        errors = session.tool_errors or 0
        if errors == 0:
            parts.append(f"<span class='trust-captured'>{calls}c 0e</span>")
        else:
            rate = errors / calls if calls else 1.0
            css = "trust-allocated" if rate < 0.25 else "trust-unallocated"
            parts.append(f"<span class='{css}'>{calls}c {errors}e</span>")
    added = session.code_added
    removed = session.code_removed
    if added is not None or removed is not None:
        a, r = added or 0, removed or 0
        if a or r:
            parts.append(f"<span class='dim'>+{a}/-{r}</span>")
    if session.commit_count:
        parts.append(f"<span class='dim'>{session.commit_count}↑</span>")
    if not parts:
        if session.tokens_available:
            parts.append("<span class='trust-captured'>✓</span>")
        else:
            parts.append("<span class='dim'>~est</span>")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# v2.23 Usage Analytics: range + tab segmented controls and models tab
# ---------------------------------------------------------------------------

# 8-colour stable palette for per-model bars. Tuned to be readable on both
# the dark and light themes; the last entry is "Other" / fallback.
_MODEL_PALETTE = [
    "#5cd28b",  # green
    "#5b9cf3",  # blue
    "#f3bf5b",  # gold
    "#d2675c",  # red
    "#b07cf3",  # purple
    "#5fd7d2",  # teal
    "#f389b0",  # pink
    "#b09060",  # tan / Other
]
_PALETTE_OTHER = _MODEL_PALETTE[-1]
_PALETTE_BUCKETS = _MODEL_PALETTE[:-1]


def _color_for_model(model: str, index_in_top: int | None) -> str:
    """Stable colour per model.

    Top-N models receive their position-indexed colour (so order is
    deterministic per render). Models outside the top-N share the
    "Other" fallback.
    """
    if index_in_top is None or index_in_top >= len(_PALETTE_BUCKETS):
        return _PALETTE_OTHER
    return _PALETTE_BUCKETS[index_in_top]


def _range_control(current: UsageRangeOpt, tab: UsageTabOpt) -> str:
    """Render a three-button segmented control for the Usage range window."""
    opts: list[tuple[UsageRangeOpt, str]] = [("7d", "7d"), ("30d", "30d"), ("all", "All")]
    parts = []
    for key, label in opts:
        cls = "pill pill-segment"
        if key == current:
            cls += " pill-active"
        parts.append(
            f"<a class='{cls}' href='?range={key}&tab={tab}'>{_e(label)}</a>"
        )
    return "<div class='segment-group' role='group' aria-label='Range'>" + "".join(parts) + "</div>"


def _tab_control(current: UsageTabOpt, usage_range: UsageRangeOpt) -> str:
    """Render an Overview/Models segmented control."""
    opts: list[tuple[UsageTabOpt, str]] = [("overview", "Overview"), ("models", "Models")]
    parts = []
    for key, label in opts:
        cls = "pill pill-segment"
        if key == current:
            cls += " pill-active"
        parts.append(
            f"<a class='{cls}' href='?range={usage_range}&tab={key}'>{_e(label)}</a>"
        )
    return "<div class='segment-group' role='group' aria-label='Tab'>" + "".join(parts) + "</div>"


def _usage_models_panel(usage: UsageAnalytics) -> str:
    """Models tab: daily stacked-bar chart + extended model table."""
    days = usage.daily
    if not days or usage.summary.total_tokens <= 0:
        return (
            "<div class='usage-models-tab'>"
            "<p class='mini-empty'>No token data in the selected range.</p>"
            "</div>"
        )

    # Establish per-model colour and rank by total tokens.
    by_model = usage.by_model
    model_index = {m.model: i for i, m in enumerate(by_model[: len(_PALETTE_BUCKETS)])}

    chart_html = _daily_model_chart(usage, model_index)
    legend_html = _model_legend(by_model, model_index)
    table_html = _model_breakdown_table(by_model, model_index)

    return (
        "<div class='usage-models-tab'>"
        f"<div class='usage-models-chart'>{chart_html}</div>"
        f"{legend_html}"
        f"<div class='usage-models-table'>{table_html}</div>"
        "</div>"
    )


def _daily_model_chart(usage: UsageAnalytics, model_index: dict[str, int]) -> str:
    """Render an SVG stacked bar chart: x = day, y = tokens, stack = model.

    Per-day per-model token totals are not pre-computed in UsageAnalytics
    (the existing summary tracks per-model AND per-day independently). We
    approximate the daily-by-model distribution by spreading each model's
    total proportionally across the days in which it had sessions.
    Imperfect — the underlying signal is missing per-session-per-model
    tokens are not retained in DailyUsageBucket — but it's directionally
    correct and accurate when only one model ran per day, which covers
    the common case for solo developers.
    """
    days = usage.daily
    max_tokens = max((d.tokens for d in days), default=0)
    if max_tokens <= 0:
        return "<p class='mini-empty'>No token data.</p>"

    # Total tokens across all days, per model, for the proportional split.
    bars = []
    width = 720
    height = 160
    pad_left = 40
    pad_bottom = 24
    chart_w = width - pad_left - 12
    chart_h = height - pad_bottom - 8
    bar_w = max(2, chart_w / max(1, len(days)))

    # Y axis lines
    y_lines = []
    for frac, label in [(0, "0"), (0.5, compact_number(int(max_tokens * 0.5))), (1.0, compact_number(max_tokens))]:
        y = chart_h - frac * chart_h + 8
        y_lines.append(
            f"<line x1='{pad_left}' y1='{y}' x2='{pad_left + chart_w}' y2='{y}' "
            f"stroke='rgba(255,255,255,0.06)' stroke-width='1'/>"
            f"<text x='{pad_left - 6}' y='{y + 3}' fill='rgba(255,255,255,0.5)' "
            f"font-size='10' text-anchor='end'>{_e(label)}</text>"
        )

    for i, day in enumerate(days):
        x = pad_left + i * bar_w
        if day.tokens <= 0:
            continue
        # Stack segments per model in rank order.
        running_top = 0.0
        bar_total_h = (day.tokens / max_tokens) * chart_h
        # Approximate: distribute today's total across models by their
        # overall share of tokens in the analytics window.
        total_modelled = sum(m.tokens for m in usage.by_model) or 1
        for m in usage.by_model:
            model_share = m.tokens / total_modelled
            seg_h = bar_total_h * model_share
            color = _color_for_model(m.model, model_index.get(m.model))
            y = chart_h - bar_total_h + running_top + 8
            bars.append(
                f"<rect x='{x}' y='{y}' width='{max(1, bar_w - 1)}' height='{seg_h:.2f}' "
                f"fill='{color}' opacity='0.9'>"
                f"<title>{_e(day.day.isoformat())}: {_e(m.model)} ~ {compact_number(int(m.tokens * (day.tokens / (usage.summary.total_tokens or 1))))}</title>"
                f"</rect>"
            )
            running_top += seg_h

    # X axis: first, middle, last day label
    x_labels = []
    if days:
        labels_idx = sorted({0, len(days) // 2, len(days) - 1})
        for i in labels_idx:
            x = pad_left + i * bar_w + bar_w / 2
            x_labels.append(
                f"<text x='{x:.2f}' y='{height - 6}' fill='rgba(255,255,255,0.5)' "
                f"font-size='10' text-anchor='middle'>{_e(days[i].day.strftime('%b %d'))}</text>"
            )

    svg = (
        f"<svg viewBox='0 0 {width} {height}' role='img' "
        f"aria-label='Daily token volume by model'>"
        + "".join(y_lines)
        + "".join(bars)
        + "".join(x_labels)
        + "</svg>"
    )
    return svg


def _model_legend(by_model: list[ModelUsageBucket], model_index: dict[str, int]) -> str:
    if not by_model:
        return ""
    items = []
    for m in by_model[: len(_PALETTE_BUCKETS)]:
        color = _color_for_model(m.model, model_index.get(m.model))
        items.append(
            f"<span class='legend-item'><span class='legend-swatch' "
            f"style='background:{color}'></span>{_e(m.model)}</span>"
        )
    if len(by_model) > len(_PALETTE_BUCKETS):
        items.append(
            f"<span class='legend-item'><span class='legend-swatch' "
            f"style='background:{_PALETTE_OTHER}'></span>Other</span>"
        )
    return "<div class='usage-models-legend'>" + "".join(items) + "</div>"


def _model_breakdown_table(by_model: list[ModelUsageBucket], model_index: dict[str, int]) -> str:
    if not by_model:
        return "<p class='mini-empty'>No model usage.</p>"
    rows = []
    for m in by_model:
        color = _color_for_model(m.model, model_index.get(m.model))
        pct = int(m.token_share * 100)
        rows.append(
            "<tr>"
            f"<td><span class='legend-swatch' style='background:{color}'></span>"
            f"<span class='model-name'>{_e(m.model)}</span></td>"
            f"<td class='num'>{m.sessions:,}</td>"
            f"<td class='num'>{compact_number(m.tokens)}</td>"
            f"<td class='num'>{pct}%</td>"
            f"<td class='num'>${m.cost_usd:.4f}</td>"
            "</tr>"
        )
    return (
        "<table class='usage-models-rows'>"
        "<thead><tr><th>Model</th><th class='num'>Sessions</th>"
        "<th class='num'>Tokens</th><th class='num'>Share</th>"
        "<th class='num'>Cost</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def _leverage_panel(sessions: list[AiSession], now: datetime) -> str:
    """v3.0 Leverage — engineering-outcome rollup over the last 30 days.

    Shows the answer to "is the AI spend producing engineering leverage?"
    in solo-developer terms: of your AI sessions in the last 30 days,
    how many landed in merged PRs?
    """
    cutoff = now - timedelta(days=30)
    recent = [s for s in sessions if s.start >= cutoff]
    total = len(recent)
    if total == 0:
        return (
            "<div class='leverage-empty'>"
            "<p class='mini-empty'>No sessions in the last 30 days.</p>"
            "</div>"
        )

    merged = sum(1 for s in recent if s.pr_state == "merged")
    open_ = sum(1 for s in recent if s.pr_state == "open")
    closed = sum(1 for s in recent if s.pr_state == "closed")
    no_pr = sum(1 for s in recent if s.pr_state == "none")
    unsynced = sum(1 for s in recent if not s.pr_state)

    leverage_pct = int((merged / total) * 100) if total else 0
    fill_class = "leverage-high" if leverage_pct >= 50 else (
        "leverage-mid" if leverage_pct >= 20 else "leverage-low"
    )

    rows = [
        ("Merged", merged, "leverage-merged"),
        ("Open", open_, "leverage-open"),
        ("Closed unmerged", closed, "leverage-closed"),
        ("No PR", no_pr, "leverage-nopr"),
        ("Not synced", unsynced, "leverage-unsynced"),
    ]
    row_html = "".join(
        "<div class='leverage-row'>"
        f"<span class='leverage-label {cls}'>{_e(label)}</span>"
        f"<strong>{count}</strong>"
        f"<small>{int(count * 100 / total)}%</small>"
        "</div>"
        for label, count, cls in rows
    )

    hint = ""
    if unsynced > 0:
        hint = (
            "<p class='leverage-hint'>"
            "Run <code>halyard outcome sync</code> to resolve unsynced sessions."
            "</p>"
        )

    return (
        "<div class='leverage-grid'>"
        f"<div class='leverage-headline'>"
        f"<div class='leverage-pct {fill_class}'>{leverage_pct}%</div>"
        f"<div class='leverage-caption'>"
        f"<strong>{merged}</strong> of <strong>{total}</strong> sessions landed in merged PRs"
        "</div>"
        "</div>"
        f"<div class='leverage-rows'>{row_html}</div>"
        f"{hint}"
        "</div>"
    )


def _usage_panel(usage: UsageAnalytics) -> str:
    summary = usage.summary
    peak = "—" if summary.peak_hour is None else _hour_label(summary.peak_hour)
    favorite = summary.favorite_model or "—"
    warnings = []
    if summary.unattributed_sessions:
        warnings.append(f"{summary.unattributed_sessions} unattributed")
    if summary.token_data_missing_sessions:
        warnings.append(f"{summary.token_data_missing_sessions} missing tokens")
    warning_html = (
        "<div class='usage-warnings'>"
        + "".join(f"<span class='pill pill-warning'>{_e(w)}</span>" for w in warnings)
        + "</div>"
        if warnings
        else ""
    )

    stats = [
        ("Sessions", f"{summary.sessions:,}", "captured"),
        ("Tokens", compact_number(summary.total_tokens), "in + out + cache"),
        (
            "Current streak",
            f"{summary.current_streak_days}d",
            f"longest {summary.longest_streak_days}d",
        ),
        ("Peak hour", peak, "session starts"),
        ("Favorite model", favorite, "by token volume"),
        ("Cost", f"${summary.total_cost_usd:.2f}", "captured"),
    ]
    stat_html = "".join(
        "<div class='usage-stat'>"
        f"<span>{_e(label)}</span><strong>{_e(value)}</strong><small>{_e(detail)}</small>"
        "</div>"
        for label, value, detail in stats
    )
    return (
        "<div class='usage-grid'>"
        f"<div class='usage-stats'>{stat_html}</div>"
        f"<div class='usage-activity'><strong>Activity</strong>{_activity_heatmap(usage)}</div>"
        f"<div class='usage-models'><strong>Models</strong>{_usage_model_rows(usage)}</div>"
        f"<div class='usage-tools'><strong>Tools</strong>{_usage_tool_rows(usage)}</div>"
        f"{warning_html}"
        "</div>"
    )


def _activity_heatmap(usage: UsageAnalytics) -> str:
    days = usage.daily[-30:]
    max_tokens = max((day.tokens for day in days), default=0)
    cells = []
    for day in days:
        level = _activity_level(day.tokens, day.sessions, max_tokens)
        title = (
            f"{day.day.isoformat()}: {day.sessions} sessions, "
            f"{day.tokens:,} tokens, ${day.cost_usd:.4f}"
        )
        missing = " usage-cell-missing" if day.has_missing_token_data and day.tokens == 0 else ""
        cells.append(
            f"<span class='usage-cell usage-l{level}{missing}' title='{_e(title)}' "
            f"aria-label='{_e(title)}'></span>"
        )
    return "<div class='usage-heatmap'>" + "".join(cells) + "</div>"


def _activity_level(tokens: int, sessions: int, max_tokens: int) -> int:
    if tokens <= 0 and sessions <= 0:
        return 0
    if max_tokens <= 0:
        return 1
    ratio = tokens / max_tokens
    if ratio >= 0.75:
        return 4
    if ratio >= 0.4:
        return 3
    if ratio >= 0.15:
        return 2
    return 1


def _usage_model_rows(usage: UsageAnalytics) -> str:
    if not usage.by_model:
        return "<p class='mini-empty'>No model usage.</p>"
    rows = []
    for bucket in usage.by_model[:5]:
        pct = int(bucket.token_share * 100)
        rows.append(
            "<div class='usage-row'>"
            f"<span>{_e(bucket.model)}</span>"
            f"<div class='bar-wrap'><div class='bar' style='width:{pct}%'></div></div>"
            f"<small>{_e(compact_number(bucket.tokens))} · {pct}%</small>"
            "</div>"
        )
    return "<div class='usage-list'>" + "".join(rows) + "</div>"


def _usage_tool_rows(usage: UsageAnalytics) -> str:
    if not usage.by_tool:
        return "<p class='mini-empty'>No tool usage.</p>"
    rows = []
    for bucket in usage.by_tool:
        pct = int(bucket.session_share * 100)
        tok_label = f" · {compact_number(bucket.tokens)}tok" if bucket.tokens else ""
        rows.append(
            "<div class='usage-row'>"
            f"<span>{_e(bucket.tool)}</span>"
            f"<div class='bar-wrap'><div class='bar bar-ok' style='width:{pct}%'></div></div>"
            f"<small>{bucket.sessions}{tok_label} · {pct}%</small>"
            "</div>"
        )
    return "<div class='usage-list'>" + "".join(rows) + "</div>"


def _model_table(buckets: Iterable[CostBucket]) -> str:
    bucket_list = list(buckets)
    if not bucket_list:
        return '<p class="empty">No model data yet.</p>'
    total_cost = sum(b.cost_usd for b in bucket_list) or 1.0
    rows = []
    for bucket in bucket_list:
        pct = int((bucket.cost_usd / total_cost) * 100)
        pct_label = f"{pct}%" if pct > 0 or bucket.cost_usd == 0 else "<1%"
        rows.append(
            "<tr>"
            f"<td>{_e(bucket.label)}</td>"
            f"<td class='num'>{bucket.sessions}</td>"
            f"<td class='num'>${bucket.cost_usd:.2f}</td>"
            f"<td><div class='bar-cell'>"
            f"<div class='bar-wrap'><div class='bar' style='width:{pct}%'></div></div>"
            f"<span>{_e(pct_label)}</span></div></td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Model</th><th>Sessions</th><th>Cost</th><th>Share</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _tool_table(buckets: Iterable[ToolUsageBucket]) -> str:
    bucket_list = list(buckets)
    if not bucket_list:
        return '<p class="empty">No tool data yet.</p>'
    total_sessions = sum(b.sessions for b in bucket_list) or 1
    rows = []
    for bucket in bucket_list:
        pct = int((bucket.sessions / total_sessions) * 100)
        pct_label = f"{pct}%" if pct > 0 or bucket.sessions == 0 else "<1%"
        tok_label = compact_number(bucket.tokens) if bucket.tokens else "—"
        rows.append(
            "<tr>"
            f"<td>{_e(bucket.tool)}</td>"
            f"<td class='num'>{bucket.sessions}</td>"
            f"<td class='num'>{_e(tok_label)}</td>"
            f"<td class='num'>${bucket.cost_usd:.2f}</td>"
            f"<td><div class='bar-cell'>"
            f"<div class='bar-wrap'><div class='bar' style='width:{pct}%'></div></div>"
            f"<span>{_e(pct_label)}</span></div></td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Tool</th><th>Sessions</th><th>Tokens</th>"
        "<th>Cost</th><th>Share</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _bucket_table(buckets: Iterable[CostBucket], label: str) -> str:
    rows = []
    for bucket in buckets:
        rows.append(
            "<tr>"
            f"<td>{_e(bucket.label)}</td>"
            f"<td class='num'>{bucket.sessions}</td>"
            f"<td class='num'>${bucket.cost_usd:.2f}</td>"
            "</tr>"
        )
    if not rows:
        return f'<p class="empty">No {label.lower()} data yet.</p>'
    return (
        f"<table><thead><tr><th>{_e(label)}</th><th>Sessions</th><th>Cost</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _budget_panel(statuses: list[BudgetStatus]) -> str:
    if not statuses:
        return '<p class="empty">No budgets configured.<br>Run <code>halyard set-budget</code> to add limits.</p>'
    items = []
    for s in statuses:
        month_cls = _budget_class(s.month_spend, s.month_limit)
        day_cls = _budget_class(s.today_spend, s.today_limit)
        bar_pct = _budget_pct(s.month_spend, s.month_limit)
        items.append(
            f"<div class='budget-item'>"
            f"<div class='budget-item-head'>"
            f"<span class='budget-slug'>{_e(s.slug)}</span>"
            f"<span class='badge badge-{_e(month_cls)}'>{_e(month_cls)}</span>"
            f"</div>"
            f"<div class='bar-wrap'><div class='bar bar-{_e(month_cls)}' style='width:{bar_pct}%'></div></div>"
            f"<div class='budget-nums'>"
            f"<span>Today <strong class='spend-{_e(day_cls)}'>{_fmt_limit(s.today_spend, s.today_limit)}</strong></span>"
            f"<span>Month <strong class='spend-{_e(month_cls)}'>{_fmt_limit(s.month_spend, s.month_limit)}</strong></span>"
            f"</div>"
            f"</div>"
        )
    return "<div class='budget-list'>" + "".join(items) + "</div>"


def _costs_panel(
    ledger: LedgerSummary | None,
    by_project: list[CostBucket],
    sessions: list[AiSession],
) -> str:
    if ledger is None:
        # No plans: compute per-project trust from raw sessions
        rows = []
        for bucket in by_project:
            proj_sessions = [s for s in sessions if (s.project or "(unattributed)") == bucket.label]
            trust = (
                aggregate_trust([session_trust(s) for s in proj_sessions])
                if proj_sessions
                else "missing"
            )
            trust_cls = trust.replace("_", "-")
            rows.append(
                "<tr>"
                f"<td>{_e(bucket.label)}</td>"
                f"<td class='num'>{bucket.sessions}</td>"
                f"<td class='num'>${bucket.cost_usd:.2f}</td>"
                "<td>—</td>"
                f"<td class='num'>${bucket.cost_usd:.2f}</td>"
                f"<td><span class='trust trust-{_e(trust_cls)}'>{_e(trust)}</span></td>"
                "</tr>"
            )
        if not rows:
            table = '<p class="empty">No sessions this period.</p>'
        else:
            table = (
                "<table><thead><tr><th>Project</th><th>Sessions</th><th>Direct API</th>"
                "<th>Allocated</th><th>Total</th><th>Trust</th></tr></thead><tbody>"
                + "".join(rows)
                + "</tbody></table>"
            )
        note = '<p class="costs-note">Add <code>ai-plans.toml</code> to see seat/credits allocation and full trust labels.</p>'
        return table + note

    # With plans: show full ledger breakdown
    rows = []
    for entry in ledger.entries:
        trust_cls = entry.trust.replace("_", "-")
        inferred_marker = (
            ' <span class="inferred-dot" title="Project inferred from timeclock">~</span>'
            if entry.has_inferred_attribution
            else ""
        )
        rows.append(
            "<tr>"
            f"<td>{_e(entry.project)}{inferred_marker}</td>"
            f"<td class='num'>{entry.sessions}</td>"
            f"<td class='num'>${entry.direct_usd:.2f}</td>"
            f"<td class='num'>${entry.allocated_usd:.2f}</td>"
            f"<td class='num'><strong>${entry.total_usd:.2f}</strong></td>"
            f"<td><span class='trust trust-{_e(trust_cls)}'>{_e(entry.trust)}</span></td>"
            "</tr>"
        )
    if not rows:
        return '<p class="empty">No sessions this period.</p>'

    footer = (
        f"<tfoot><tr>"
        f"<td><strong>Total</strong></td><td></td>"
        f"<td class='num'><strong>${ledger.total_direct_usd:.2f}</strong></td>"
        f"<td class='num'><strong>${ledger.total_allocated_usd:.2f}</strong></td>"
        f"<td class='num'><strong>${ledger.total_usd:.2f}</strong></td>"
        f"<td></td></tr></tfoot>"
    )
    return (
        "<table><thead><tr><th>Project</th><th>Sessions</th><th>Direct API</th>"
        "<th>Allocated</th><th>Total</th><th>Trust</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody>"
        + footer
        + "</table>"
    )


def _unattributed_table(sessions: Iterable[AiSession]) -> str:
    rows = []
    for session in list(sessions)[-25:][::-1]:
        rows.append(
            "<tr>"
            f"<td>{_e(session.end.strftime('%Y-%m-%d %H:%M'))}</td>"
            f"<td>{_e(session.tool)}</td>"
            f"<td>{_e(session.model)}</td>"
            f"<td class='num'>{session.input_tokens:,} / {session.output_tokens:,}</td>"
            f"<td class='num'>${session.cost_usd:.4f}</td>"
            "</tr>"
        )
    if not rows:
        return '<p class="empty">All hands accounted for. Manifest clean.</p>'
    return (
        "<table><thead><tr><th>Time</th><th>Tool</th><th>Model</th>"
        "<th>In / Out</th><th>Cost</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _time_table(buckets: Iterable[TimeBucket]) -> str:
    rows = []
    for bucket in buckets:
        rows.append(
            f"<tr><td>{_e(bucket.label)}</td><td class='num'>{_e(format_minutes(bucket.minutes))}</td></tr>"
        )
    if not rows:
        return '<p class="empty">No human time recorded this month.<br>Run <code>halyard start &lt;project&gt;</code> to begin tracking.</p>'
    return (
        "<table><thead><tr><th>Project</th><th>Time</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _health_row(label: str, status: str, detail: str) -> str:
    return (
        f'<div class="health-row"><span class="dot dot-{_e(status)}"></span>'
        f"<div><strong>{_e(label)}</strong><small>{_e(detail)}</small></div></div>"
    )


def _latest_label(session: AiSession | None) -> str:
    if session is None:
        return "none"
    return _e(f"{session.tool} {session.model} at {session.end.strftime('%H:%M')}")


def _tool_icon(tool: str) -> tuple[str, str]:
    """Return (css_key, emoji) for the tool badge."""
    t = tool.lower()
    if "claude" in t:
        return "C", "🤖"
    if "cursor" in t:
        return "X", "🖱️"
    if "vscode" in t or "vs-code" in t or "visual-studio-code" in t:
        return "V", "🧩"
    if "gemini" in t:
        return "G", "♊"
    if "codex" in t:
        return "O", "📦"
    return "A", "🔧"


def _hour_label(hour: int) -> str:
    suffix = "AM" if hour < 12 else "PM"
    hour_12 = hour % 12 or 12
    return f"{hour_12} {suffix}"


def _duration_str(delta: timedelta) -> str:
    seconds = max(0, int(delta.total_seconds()))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


def _budget_class(spend: float, limit: float | None) -> str:
    if limit is None or limit <= 0:
        return "ok"
    ratio = spend / limit
    if ratio > 1.0:
        return "over"
    if ratio >= 0.8:
        return "high"
    if ratio >= 0.5:
        return "warn"
    return "ok"


def _budget_pct(spend: float, limit: float | None) -> int:
    if limit is None or limit <= 0:
        return 0
    return min(100, int((spend / limit) * 100))


def _fmt_limit(spend: float, limit: float | None) -> str:
    if limit is None:
        return f"${spend:.2f} / —"
    return f"${spend:.2f} / ${limit:.2f}"


def _e(value: object) -> str:
    return html.escape(str(value))


def _panel_status_pill(text: str, state: str) -> str:
    return f"<span class='pill pill-{_e(state)}'>{_e(text)}</span>"


def _celebration_script() -> str:
    return """<script>
(function(){
  var q = new URLSearchParams(location.search);
  if (q.get('stopped') !== '1') return;

  // Remove ?stopped=1 so auto-refresh doesn't retrigger the celebration
  history.replaceState(null, '', location.pathname);

  var toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = '🔔 Eight bells — watch complete!';
  document.body.appendChild(toast);
  requestAnimationFrame(function(){ toast.classList.add('show'); });
  setTimeout(function(){
    toast.style.transition = 'opacity .5s';
    toast.style.opacity = '0';
    setTimeout(function(){ toast.remove(); }, 500);
  }, 3200);

  var canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:998';
  document.body.appendChild(canvas);
  var ctx = canvas.getContext('2d');
  canvas.width = innerWidth; canvas.height = innerHeight;
  var colors = ['#45d6d0','#70e18f','#f3bf5b','#b09fe8','#ff6f6f'];
  var particles = [];
  for (var i = 0; i < 90; i++) {
    particles.push({
      x: Math.random() * canvas.width,
      y: Math.random() * -canvas.height * 0.5,
      w: Math.random() * 8 + 4,
      h: Math.random() * 5 + 3,
      color: colors[Math.floor(Math.random() * colors.length)],
      speed: Math.random() * 3 + 2,
      angle: Math.random() * Math.PI * 2,
      spin: (Math.random() - 0.5) * 0.15
    });
  }
  var frame = 0;
  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.globalAlpha = frame < 150 ? 1 : 1 - (frame - 150) / 50;
    for (var j = 0; j < particles.length; j++) {
      var p = particles[j];
      p.y += p.speed; p.angle += p.spin;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.angle);
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.w/2, -p.h/2, p.w, p.h);
      ctx.restore();
    }
    if (++frame < 200) requestAnimationFrame(draw);
    else canvas.remove();
  }
  draw();
})();
</script>"""


def _trail_heatmap_html(sessions: list[AiSession], period: object) -> str:
    import calendar
    from collections import defaultdict
    from datetime import date, datetime

    p = period if isinstance(period, datetime) else datetime.now()
    year, month = p.year, p.month
    today = datetime.now().date()

    day_total: dict[date, int] = defaultdict(int)
    day_attr: dict[date, int] = defaultdict(int)
    for s in sessions:
        d = s.start.date()
        if d.year == year and d.month == month:
            day_total[d] += 1
            if s.project:
                day_attr[d] += 1

    weeks = calendar.monthcalendar(year, month)
    header = (
        "<div class='trail-cal-header'>"
        + "".join(f"<span>{day}</span>" for day in ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"])
        + "</div>"
    )

    rows_html = []
    for week in weeks:
        cells = []
        for day_num in week:
            if day_num == 0:
                cells.append("<span class='trail-cell trail-empty'></span>")
            else:
                d = date(year, month, day_num)
                total = day_total[d]
                attr = day_attr[d]
                noun = "session" if total == 1 else "sessions"
                title = f"{d.isoformat()}: {total} {noun}, {attr} attributed"
                if d > today:
                    cls = "trail-future"
                elif total == 0:
                    cls = "trail-none"
                elif attr == 0:
                    cls = "trail-unattr"
                elif attr < total:
                    cls = "trail-partial"
                else:
                    cls = "trail-full"
                cells.append(
                    f"<span class='trail-cell {_e(cls)}' title='{_e(title)}'>"
                    f"<span class='trail-dn'>{day_num}</span>"
                    f"</span>"
                )
        rows_html.append("<div class='trail-cal-row'>" + "".join(cells) + "</div>")

    legend = (
        "<div class='trail-legend'>"
        "<span class='trail-cell trail-none'></span><span>becalmed</span>"
        "<span class='trail-cell trail-unattr'></span><span>adrift</span>"
        "<span class='trail-cell trail-partial'></span><span>making way</span>"
        "<span class='trail-cell trail-full'></span><span>full sail</span>"
        "</div>"
    )
    return "<div class='trail-cal'>" + header + "".join(rows_html) + "</div>" + legend


def _easter_egg_script() -> str:
    return """<script>
(function(){
  /* ── Light/dark mode toggle ── */
  var btn = document.getElementById('theme-toggle');
  function applyTheme(light) {
    document.body.classList.toggle('light-mode', light);
    if (btn) btn.textContent = light ? '🌙' : '☀️';
  }
  applyTheme(localStorage.getItem('halyard-theme') === 'light');
  if (btn) {
    btn.addEventListener('click', function(){
      var next = !document.body.classList.contains('light-mode');
      applyTheme(next);
      localStorage.setItem('halyard-theme', next ? 'light' : 'dark');
    });
  }

  /* ── Konami code → confetti ── */
  var KONAMI = [38,38,40,40,37,39,37,39,66,65];
  var kpos = 0;
  document.addEventListener('keydown', function(e){
    if (e.keyCode === KONAMI[kpos]) { kpos++; } else { kpos = 0; }
    if (kpos === KONAMI.length) {
      kpos = 0;
      _showToast('⚓ Konami unlocked! Fair winds, Captain.');
      _fireConfetti(180);
    }
  });

  /* ── Morse timer signals (0/1 keys → START=0001010101 / STOP=00011110110) ── */
  var MORSE_START = '0001010101', MORSE_STOP = '00011110110';
  var morseBuf = '', morseTimer = null;
  document.addEventListener('keydown', function(e){
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key !== '0' && e.key !== '1') return;
    morseBuf += e.key;
    clearTimeout(morseTimer);
    morseTimer = setTimeout(function(){
      var code = morseBuf;
      morseBuf = '';
      if (code === MORSE_START) {
        _showToast('📡 \xb7\xb7\xb7 ——— \xb7\xb7\xb7  START — run: halyard start <slug>');
      } else if (code === MORSE_STOP) {
        _showToast('📡 \xb7\xb7\xb7 ——— \xb7\xb7\xb7  STOP — run: halyard stop');
      }
    }, 2000);
  });

  /* ── Logo click x5 -> Night Watch mode ── */
  var logo = document.getElementById('brand-mark');
  var clicks = 0, clickTimer = null;
  if (logo) {
    logo.style.cursor = 'pointer';
    logo.addEventListener('click', function(){
      clicks++;
      clearTimeout(clickTimer);
      clickTimer = setTimeout(function(){ clicks = 0; }, 1500);
      if (clicks >= 5) {
        clicks = 0;
        var on = document.body.classList.toggle('night-watch');
        _showToast(on ? '🌙 Night Watch engaged. All hands below.' : '☀️ Returning to day watch.');
      }
    });
  }

  /* ── shared helpers ── */
  function _showToast(msg) {
    var t = document.createElement('div');
    t.className = 'toast';
    t.textContent = msg;
    document.body.appendChild(t);
    requestAnimationFrame(function(){ t.classList.add('show'); });
    setTimeout(function(){
      t.style.transition = 'opacity .5s'; t.style.opacity = '0';
      setTimeout(function(){ t.remove(); }, 500);
    }, 3200);
  }

  function _fireConfetti(count) {
    var canvas = document.createElement('canvas');
    canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:998';
    document.body.appendChild(canvas);
    var ctx = canvas.getContext('2d');
    canvas.width = innerWidth; canvas.height = innerHeight;
    var colors = ['#45d6d0','#70e18f','#f3bf5b','#b09fe8','#ff6f6f','#c8a8e9'];
    var particles = [];
    for (var i = 0; i < count; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * -canvas.height * 0.5,
        w: Math.random() * 8 + 4, h: Math.random() * 5 + 3,
        color: colors[Math.floor(Math.random() * colors.length)],
        speed: Math.random() * 3 + 2,
        angle: Math.random() * Math.PI * 2,
        spin: (Math.random() - 0.5) * 0.15
      });
    }
    var frame = 0;
    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.globalAlpha = frame < 150 ? 1 : 1 - (frame - 150) / 50;
      for (var j = 0; j < particles.length; j++) {
        var p = particles[j];
        p.y += p.speed; p.angle += p.spin;
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.angle);
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.w/2, -p.h/2, p.w, p.h);
        ctx.restore();
      }
      if (++frame < 200) requestAnimationFrame(draw); else canvas.remove();
    }
    draw();
  }
})();
</script>"""


_CSS = """
:root {
  color-scheme: dark;
  --bg: #091114;
  --panel: #101b20;
  --panel-2: #14242b;
  --line: #25404a;
  --text: #eff7f5;
  --muted: #8ea5a8;
  --cyan: #45d6d0;
  --green: #70e18f;
  --amber: #f3bf5b;
  --red: #ff6f6f;
  --purple: #b09fe8;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-width: 920px;
  background:
    linear-gradient(180deg, rgba(69, 214, 208, .08), transparent 28rem),
    var(--bg);
  color: var(--text);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.shell { width: min(1440px, calc(100vw - 48px)); margin: 0 auto; padding: 28px 0; }
.topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 22px; }
.brand { display: inline-flex; align-items: center; gap: 14px; }
.brand-mark { display: grid; place-items: center; width: 44px; height: 44px; }
.brand-mark svg { width: 38px; height: 38px; fill: none; stroke: var(--cyan); stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; filter: drop-shadow(0 0 8px rgba(69,214,208,.45)); }
.eyebrow { margin: 0 0 6px; color: var(--cyan); font-size: 11px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
h1, h2 { margin: 0; letter-spacing: 0; }
h1 { font-size: 28px; }
h2 { font-size: 17px; }
.status, .pill {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 7px 11px;
  color: var(--muted);
  background: rgba(255,255,255,.03);
  font-size: 12px;
  font-weight: 700;
}
.status-healthy { color: var(--green); border-color: rgba(112, 225, 143, .4); }
.status-warning { color: var(--amber); border-color: rgba(243, 191, 91, .45); }
.status-error { color: var(--red); border-color: rgba(255, 111, 111, .5); }
.pill-healthy { color: var(--green); border-color: rgba(112, 225, 143, .4); background: rgba(112, 225, 143, .08); }
.pill-warning { color: var(--amber); border-color: rgba(243, 191, 91, .45); background: rgba(243, 191, 91, .08); }
.pill-error { color: var(--red); border-color: rgba(255, 111, 111, .5); background: rgba(255, 111, 111, .08); }
.pill-muted { color: var(--muted); }
.pill-group { display: flex; gap: 6px; align-items: center; }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 12px; }
.metric, .panel {
  border: 1px solid var(--line);
  background: linear-gradient(180deg, rgba(255,255,255,.035), rgba(255,255,255,.015)), var(--panel);
  border-radius: 8px;
  box-shadow: 0 18px 60px rgba(0, 0, 0, .24);
}
.metric { min-height: 118px; padding: 16px; display: flex; flex-direction: column; justify-content: space-between; }
.metric span, .metric small, footer { color: var(--muted); }
.metric strong { font-size: 28px; line-height: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.metric-focus strong { color: var(--cyan); }
.metric-money strong { color: var(--green); }
.grid { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 12px; }
.panel { min-height: 260px; padding: 16px; overflow: hidden; }
.span-7 { grid-column: span 7; }
.span-12 { grid-column: span 12; }
.span-6 { grid-column: span 6; }
.span-5 { grid-column: span 5; }
.span-4 { grid-column: span 4; }
.span-3 { grid-column: span 3; }
.panel-head { min-height: 42px; display: flex; align-items: start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.attention-on { border-color: rgba(243, 191, 91, .62); }
.attention-on .pill { color: var(--amber); border-color: rgba(243, 191, 91, .45); }
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
th, td { border-bottom: 1px solid rgba(37, 64, 74, .72); padding: 10px 8px; text-align: left; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
th { color: var(--muted); font-size: 11px; text-transform: uppercase; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
tfoot td { border-bottom: none; border-top: 1px solid var(--line); }
.empty { min-height: 150px; display: grid; place-items: center; color: var(--muted); border: 1px dashed var(--line); border-radius: 8px; margin: 0; text-align: center; line-height: 1.6; }
.health-list { display: grid; gap: 10px; }
.health-row { display: grid; grid-template-columns: 14px 1fr; align-items: center; gap: 10px; min-height: 42px; padding: 10px; border: 1px solid rgba(37,64,74,.7); border-radius: 8px; background: var(--panel-2); }
.health-row strong, .health-row small { display: block; }
.health-row small { margin-top: 2px; color: var(--muted); overflow-wrap: anywhere; }
.dot { width: 10px; height: 10px; border-radius: 99px; display: block; background: var(--muted); }
.dot-healthy { background: var(--green); box-shadow: 0 0 18px rgba(112, 225, 143, .55); }
.dot-warning { background: var(--amber); box-shadow: 0 0 18px rgba(243, 191, 91, .45); }
.dot-error { background: var(--red); box-shadow: 0 0 18px rgba(255, 111, 111, .5); }
.dot-neutral { background: var(--muted); }
footer { padding: 18px 2px 0; font-size: 12px; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; background: rgba(255,255,255,.07); padding: 1px 5px; border-radius: 3px; }

/* Tool icons */
.tool-icon { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 6px; font-size: 15px; text-align: center; }
.tool-C { background: rgba(69, 214, 208, .15); }
.tool-X { background: rgba(112, 225, 143, .12); }
.tool-G { background: rgba(243, 191, 91, .12); }
.tool-V { background: rgba(180, 120, 255, .12); }
.tool-O, .tool-A { background: rgba(255,255,255,.08); }

/* Progress bars */
.bar-wrap { width: 100%; background: var(--line); border-radius: 99px; height: 4px; overflow: hidden; }
.bar { height: 100%; border-radius: 99px; background: var(--cyan); transition: width .3s; }
.bar-ok { background: var(--green); }
.bar-warn { background: var(--amber); }
.bar-high { background: var(--amber); opacity: .85; }
.bar-over { background: var(--red); }
.bar-cell { display: flex; align-items: center; gap: 8px; }
.bar-cell .bar-wrap { flex: 1; min-width: 40px; }
.bar-cell span { font-size: 11px; color: var(--muted); white-space: nowrap; min-width: 30px; text-align: right; }

/* Usage analytics */
.usage-grid { display: grid; grid-template-columns: 1.2fr 1fr 1fr; gap: 14px; align-items: start; }
.usage-stats { grid-column: span 3; display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; }
.usage-stat { min-height: 76px; padding: 10px 12px; border: 1px solid rgba(37,64,74,.7); border-radius: 8px; background: var(--panel-2); }
.usage-stat span, .usage-stat small, .usage-tools small, .usage-models small, .mini-empty { color: var(--muted); }
.usage-stat span, .usage-stat strong, .usage-stat small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.usage-stat strong { margin: 7px 0 5px; font-size: 22px; line-height: 1; color: var(--text); }
.usage-activity, .usage-models, .usage-tools { min-height: 120px; }
.usage-activity > strong, .usage-models > strong, .usage-tools > strong { display: block; margin-bottom: 10px; font-size: 13px; }
.usage-heatmap { display: grid; grid-template-columns: repeat(15, 16px); gap: 6px; align-content: start; }
.usage-cell { width: 16px; height: 16px; border-radius: 4px; background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.04); }
.usage-l1 { background: rgba(69,214,208,.18); }
.usage-l2 { background: rgba(69,214,208,.34); }
.usage-l3 { background: rgba(112,225,143,.44); }
.usage-l4 { background: rgba(112,225,143,.72); }
.usage-cell-missing { background: rgba(243,191,91,.25); }
.usage-list { display: grid; gap: 9px; }
.usage-row { display: grid; grid-template-columns: minmax(110px, 1fr) 1.2fr 78px; gap: 8px; align-items: center; font-size: 12px; }
.usage-row span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.usage-row small { text-align: right; white-space: nowrap; }
.usage-warnings { grid-column: span 3; display: flex; gap: 8px; flex-wrap: wrap; }

/* v2.23 Usage Analytics: segmented controls + Models tab */
.segment-group { display: inline-flex; border-radius: 6px; overflow: hidden; border: 1px solid rgba(255,255,255,0.08); }
.pill-segment { border-radius: 0; padding: 4px 10px; font-size: 12px; text-decoration: none; color: var(--muted); background: transparent; border: none; border-right: 1px solid rgba(255,255,255,0.08); }
.pill-segment:last-child { border-right: none; }
.pill-segment:hover { background: rgba(255,255,255,0.04); color: var(--fg); }
.pill-segment.pill-active { background: rgba(76,156,243,0.2); color: var(--fg); }
.usage-models-tab { display: grid; gap: 14px; }
.usage-models-chart svg { width: 100%; height: auto; max-height: 200px; }
.usage-models-legend { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: var(--muted); }
.legend-item { display: inline-flex; align-items: center; gap: 6px; max-width: 220px; }
.legend-item .model-name, .legend-item span:not(.legend-swatch) { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.legend-swatch { display: inline-block; width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
.usage-models-rows { width: 100%; border-collapse: collapse; font-size: 12px; }
.usage-models-rows th { text-align: left; color: var(--muted); font-weight: 500; padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,0.06); }
.usage-models-rows td { padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,0.04); }
.usage-models-rows td.num, .usage-models-rows th.num { text-align: right; white-space: nowrap; }
.usage-models-rows .model-name { display: inline-block; max-width: 280px; vertical-align: middle; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-left: 6px; }

/* v3.0 Leverage panel */
.leverage-grid { display: grid; grid-template-columns: minmax(220px, 1fr) 2fr; gap: 18px; align-items: center; }
.leverage-headline { display: grid; gap: 8px; }
.leverage-pct { font-size: 42px; font-weight: 700; line-height: 1.1; }
.leverage-pct.leverage-high { color: #5cd28b; }
.leverage-pct.leverage-mid { color: #f3bf5b; }
.leverage-pct.leverage-low { color: var(--muted); }
.leverage-caption { font-size: 13px; color: var(--muted); }
.leverage-caption strong { color: var(--fg); }
.leverage-rows { display: grid; gap: 6px; }
.leverage-row { display: grid; grid-template-columns: 1.4fr 64px 64px; gap: 12px; align-items: center; font-size: 13px; }
.leverage-row strong { text-align: right; }
.leverage-row small { text-align: right; color: var(--muted); }
.leverage-label { display: inline-flex; align-items: center; gap: 6px; }
.leverage-label::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
.leverage-label.leverage-merged::before { background: #5cd28b; }
.leverage-label.leverage-open::before { background: #5b9cf3; }
.leverage-label.leverage-closed::before { background: #d2675c; }
.leverage-label.leverage-nopr::before { background: #b09060; }
.leverage-label.leverage-unsynced::before { background: var(--muted); }
.leverage-hint { grid-column: span 2; font-size: 12px; color: var(--muted); margin: 8px 0 0; }
.leverage-hint code { background: var(--panel-2); padding: 2px 6px; border-radius: 4px; }
.leverage-empty { padding: 12px 0; }

/* Budget panel */
.budget-list { display: grid; gap: 8px; }
.budget-item { padding: 10px 12px; border: 1px solid rgba(37,64,74,.7); border-radius: 8px; background: var(--panel-2); }
.budget-item-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.budget-slug { font-size: 13px; font-weight: 600; }
.budget-nums { display: flex; justify-content: space-between; font-size: 11px; color: var(--muted); margin-top: 8px; }
.badge { border-radius: 99px; padding: 2px 8px; font-size: 11px; font-weight: 700; }
.badge-ok { background: rgba(112, 225, 143, .15); color: var(--green); }
.badge-warn { background: rgba(243, 191, 91, .15); color: var(--amber); }
.badge-high { background: rgba(243, 191, 91, .25); color: var(--amber); }
.badge-over { background: rgba(255, 111, 111, .15); color: var(--red); }
.spend-ok strong, .spend-ok { color: inherit; }
.spend-warn strong, .spend-warn { color: var(--amber); }
.spend-high strong, .spend-high { color: var(--amber); }
.spend-over strong, .spend-over { color: var(--red); }

/* Trust labels */
.trust { display: inline-block; border-radius: 99px; padding: 2px 9px; font-size: 11px; font-weight: 700; }
.trust-captured { background: rgba(112, 225, 143, .15); color: var(--green); }
.trust-calculated { background: rgba(69, 214, 208, .15); color: var(--cyan); }
.trust-allocated { background: rgba(243, 191, 91, .15); color: var(--amber); }
.trust-missing { background: rgba(255, 111, 111, .12); color: var(--red); }
.trust-inferred { background: rgba(255,255,255,.08); color: var(--muted); }
.trust-mixed { background: rgba(176, 159, 232, .2); color: var(--purple); }
.trust-unallocated { background: rgba(255,255,255,.06); color: var(--muted); }
.inferred-dot { color: var(--muted); font-size: 11px; cursor: help; }
.costs-note { font-size: 12px; color: var(--muted); margin-top: 12px; }

/* Timer controls */
.timer-form { display: flex; gap: 6px; align-items: center; margin-top: 8px; }
.timer-input {
  flex: 1; min-width: 0;
  background: rgba(255,255,255,.07); border: 1px solid var(--line); border-radius: 4px;
  color: var(--text); font-size: 12px; padding: 5px 8px; outline: none;
}
.timer-input:focus { border-color: var(--cyan); }
.btn {
  border: none; border-radius: 4px; cursor: pointer;
  font-size: 11px; font-weight: 700; padding: 5px 10px; letter-spacing: .04em;
  white-space: nowrap;
}
.btn-start { background: rgba(112, 225, 143, .15); color: var(--green); }
.btn-start:hover { background: rgba(112, 225, 143, .25); }
.btn-stop { background: rgba(255, 111, 111, .12); color: var(--red); width: 100%; }
.btn-stop:hover { background: rgba(255, 111, 111, .22); }
.btn-sm { background: rgba(255,255,255,.06); color: var(--muted); font-size: 10px; padding: 3px 8px; }
.btn-sm:hover { background: rgba(255,255,255,.12); color: var(--fg); }

/* Stop celebration toast */
.toast {
  position: fixed; top: 28px; left: 50%;
  transform: translateX(-50%) translateY(-140%);
  background: rgba(112,225,143,.12); border: 1px solid rgba(112,225,143,.4);
  color: #70e18f; padding: 10px 24px; border-radius: 999px;
  font-weight: 700; font-size: 14px; letter-spacing: .02em;
  z-index: 999; white-space: nowrap;
  transition: transform .45s cubic-bezier(.34,1.56,.64,1);
}
.toast.show { transform: translateX(-50%) translateY(0); }

/* Trail heatmap calendar */
.trail-cal { display: inline-block; }
.trail-cal-header { display: grid; grid-template-columns: repeat(7, 38px); gap: 5px; margin-bottom: 4px; font-size: 11px; color: var(--muted); font-weight: 700; text-align: center; }
.trail-cal-row { display: grid; grid-template-columns: repeat(7, 38px); gap: 5px; margin-bottom: 5px; }
.trail-cell { width: 38px; height: 38px; border-radius: 6px; border: 1px solid rgba(255,255,255,.05); display: flex; align-items: center; justify-content: center; cursor: default; transition: opacity .15s; }
.trail-cell:hover { opacity: .8; }
.trail-dn { font-size: 11px; font-weight: 600; pointer-events: none; }
.trail-empty { border-color: transparent; background: transparent; }
.trail-future { background: rgba(255,255,255,.02); border-color: transparent; }
.trail-future .trail-dn { color: var(--muted); opacity: .4; }
.trail-none { background: rgba(255,255,255,.04); }
.trail-none .trail-dn { color: var(--muted); }
.trail-unattr { background: rgba(243,191,91,.13); border-color: rgba(243,191,91,.22); }
.trail-unattr .trail-dn { color: var(--amber); }
.trail-partial { background: rgba(243,191,91,.22); border-color: rgba(243,191,91,.38); }
.trail-partial .trail-dn { color: var(--amber); }
.trail-full { background: rgba(112,225,143,.16); border-color: rgba(112,225,143,.30); }
.trail-full .trail-dn { color: var(--green); }
.trail-legend { display: flex; align-items: center; gap: 8px; margin-top: 10px; font-size: 12px; color: var(--muted); }
.trail-legend .trail-cell { width: 14px; height: 14px; min-width: 14px; border-radius: 3px; pointer-events: none; }
.trail-legend .trail-dn { display: none; }

/* Current Voyage panel */
.voyage-bar-outer { width: 100%; background: var(--line); border-radius: 99px; height: 5px; overflow: hidden; margin: 10px 0 14px; }
.voyage-bar-fill { height: 100%; border-radius: 99px; background: var(--cyan); transition: width .4s ease; }
.voyage-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.voyage-col { display: flex; flex-direction: column; gap: 5px; padding: 12px 14px; border: 1px solid rgba(37,64,74,.7); border-radius: 8px; background: var(--panel-2); }
.voyage-col-warn { border-color: rgba(243,191,91,.3); }
.voyage-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .09em; font-weight: 700; }
.voyage-value { font-size: 26px; font-weight: 700; line-height: 1.1; color: var(--text); }
.voyage-sub { font-size: 11px; color: var(--muted); }
.proof-healthy { color: var(--green); }
.proof-warn { color: var(--amber); }
.proof-low { color: var(--red); }
.proof-neutral { color: var(--muted); }

/* Captain's Quarters */
.cq-body { display: grid; grid-template-columns: 2fr 1fr 1.5fr 1fr; gap: 24px; }
.cq-main { display: flex; flex-direction: column; gap: 14px; }
.cq-rank { display: flex; align-items: flex-start; gap: 16px; }
.cq-rank-icon { font-size: 38px; line-height: 1; }
.cq-rank-name { margin: 0; font-size: 22px; font-weight: 700; }
.cq-rank-flavor { margin: 4px 0 0; font-size: 13px; color: var(--muted); font-style: italic; }
.cq-progress-outer { width: 100%; background: var(--line); border-radius: 99px; height: 5px; overflow: hidden; margin: 4px 0 6px; }
.cq-progress-fill { height: 100%; border-radius: 99px; background: var(--cyan); transition: width .4s ease; }
.cq-sub { margin: 0; font-size: 11px; color: var(--muted); }
.cq-stripes { display: flex; align-items: center; gap: 12px; }
.cq-stripe-bar { font-size: 22px; color: var(--cyan); letter-spacing: 3px; }
.cq-section-label { margin: 0 0 8px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .09em; color: var(--muted); }
.cq-medals { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.cq-medal { display: flex; align-items: flex-start; gap: 8px; cursor: default; }
.cq-medal:hover .cq-medal-desc { color: var(--text); }
.cq-medal-icon { font-size: 18px; flex-shrink: 0; }
.cq-medal-name { font-size: 13px; font-weight: 600; display: block; }
.cq-medal-desc { font-size: 11px; color: var(--muted); display: block; }
.cq-empty { font-style: italic; }
.cq-stamps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.cq-stamp { display: flex; align-items: center; gap: 8px; }
.cq-stamp-icon { font-size: 18px; flex-shrink: 0; }
.cq-stamp-name { font-size: 13px; font-weight: 600; }
.cq-ladder { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.cq-ladder-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); }
.cq-ladder-active { color: var(--cyan); font-weight: 700; }

/* Friends of the Sea */
.friends-grid { display: flex; flex-wrap: wrap; gap: 12px; padding: 4px 0 8px; }
.friend-card { display: flex; flex-direction: column; gap: 4px; padding: 12px 16px; border-radius: 8px; background: var(--surface); min-width: 160px; max-width: 220px; flex: 1 1 160px; }
.friend-moored { border: 1px solid var(--cyan); }
.friend-active { border: 1px solid var(--border); }
.friend-creature { font-size: 28px; line-height: 1; }
.friend-slug { font-size: 13px; font-weight: 700; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.friend-stage { font-size: 11px; color: var(--muted); }
.friend-trait { font-size: 11px; color: var(--cyan); font-style: italic; }
.friend-count { font-size: 11px; color: var(--muted); }
.friend-progress-outer { height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; margin: 2px 0; }
.friend-progress-fill { height: 100%; background: var(--cyan); border-radius: 2px; }
.friend-stage-anchors_aweigh { color: var(--amber); }
.friend-stage-making_headway { color: var(--cyan); }
.friend-stage-rounding_the_mark { color: #7dd3fc; }
.friend-stage-flying_colors { color: #4ade80; }

@media (max-width: 1100px) {
  body { min-width: 760px; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .span-7, .span-6, .span-5, .span-4, .span-3 { grid-column: span 12; }
  .usage-grid { grid-template-columns: 1fr; }
  .usage-stats, .usage-warnings { grid-column: span 1; }
  .usage-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .voyage-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .cq-body { grid-template-columns: 1fr; }
}

/* Light mode */
body.light-mode {
  color-scheme: light;
  --bg: #f4f7f8;
  --panel: #ffffff;
  --panel-2: #eef2f3;
  --line: #d0dde0;
  --text: #0e2028;
  --muted: #5a7a82;
  --cyan: #0e9e99;
  --green: #1a9e3f;
  --amber: #b07a10;
  --red: #c0392b;
  --purple: #6b52c8;
  background: linear-gradient(180deg, rgba(14,158,153,.06), transparent 28rem), var(--bg) !important;
}
body.light-mode .panel, body.light-mode article { box-shadow: 0 1px 4px rgba(0,0,0,.08); }
body.light-mode .brand-mark svg { filter: drop-shadow(0 0 6px rgba(14,158,153,.3)); }
.theme-toggle {
  background: none; border: 1px solid var(--line); border-radius: 8px;
  color: var(--muted); cursor: pointer; font-size: 16px;
  padding: 5px 10px; line-height: 1; transition: border-color .2s, color .2s;
}
.theme-toggle:hover { border-color: var(--cyan); color: var(--text); }

/* Night Watch mode — activated by clicking the logo 5x */
body.night-watch { --bg: #0a0a0f; --surface: #0d0d14; --border: #1a1a2e; --text: #c8a8e9; --muted: #6a5a8a; }
body.night-watch .topbar { background: #0d0d14; border-color: #1a1a2e; }
body.night-watch .brand-mark svg { stroke: #c8a8e9; }
body.night-watch .night-watch-toast { display: flex !important; }
.night-watch-toast {
  display: none;
  position: fixed; bottom: 1.5rem; right: 1.5rem; z-index: 999;
  background: #1a1a2e; color: #c8a8e9; border: 1px solid #c8a8e9;
  padding: .6rem 1.2rem; border-radius: 8px; font-size: .85rem;
  align-items: center; gap: .5rem;
}
"""
