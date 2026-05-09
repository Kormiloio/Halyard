"""Local Glass Cockpit dashboard server."""

# ruff: noqa: E501

from __future__ import annotations

import html
import socket
import webbrowser
from collections.abc import Iterable
from contextlib import suppress
from datetime import timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from halyard.ai_log import AiSession, parse_sessions
from halyard.ai_plans import read_ai_plans
from halyard.budget import BudgetStatus, budget_status
from halyard.ledger import LedgerSummary, build_ledger
from halyard.org_rollups import aggregate_trust, session_trust
from halyard.reports import (
    CostBucket,
    DashboardState,
    TimeBucket,
    build_dashboard_state,
    format_minutes,
    parse_timeclock,
)
from halyard.usage import UsageAnalytics, build_usage_analytics, compact_number

DASHBOARD_PORT = 7432


def run_dashboard(
    project_dir: Path, *, port: int = DASHBOARD_PORT, open_browser: bool = False
) -> str:
    """Start the dashboard server and block until interrupted."""
    host = "127.0.0.1"
    server = ThreadingHTTPServer((host, _resolve_port(port)), _handler_for(project_dir))
    url = f"http://{host}:{server.server_port}/"
    print(f"Halyard Glass Cockpit: {url}")
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


def render_dashboard(project_dir: Path) -> str:
    """Render the dashboard HTML for tests and the HTTP handler."""
    return _render_state(build_dashboard_state(project_dir))


def _handler_for(project_dir: Path, token: str | None = None) -> type[BaseHTTPRequestHandler]:
    from halyard.service import _load_or_create_token

    _token: str = token if token is not None else _load_or_create_token()

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._send_dashboard(include_body=True)

        def do_HEAD(self) -> None:
            self._send_dashboard(include_body=False)

        def do_POST(self) -> None:
            from urllib.parse import parse_qs

            server_port = self.server.server_port  # type: ignore[attr-defined]

            # 2.3: Validate Host header — must be 127.0.0.1:<port>
            host = self.headers.get("Host", "")
            if host != f"127.0.0.1:{server_port}":
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
            self.send_header("Location", "/")
            self.end_headers()

        def _send_dashboard(self, *, include_body: bool) -> None:
            if self.path not in {"/", "/index.html"}:
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            body = render_dashboard(project_dir).encode()
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


def _render_state(state: DashboardState) -> str:
    report = state.report
    human_time = state.human_time
    latest = state.latest_session
    health_level = _overall_health(state)
    usage = build_usage_analytics(parse_sessions(state.project_dir), now=state.generated_at)

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
        _panel_status_pill(f"{unattr_count} open", "warning")
        if unattr_count
        else _panel_status_pill("all attributed", "healthy")
    )

    time_state = "healthy" if human_time.month_minutes > 0 else "muted"
    time_pill = _panel_status_pill(
        format_minutes(human_time.month_minutes) + " this month", time_state
    )

    proj_count = len([b for b in report.by_project if b.label != "(unattributed)"])
    if session_count == 0:
        projects_pill = _panel_status_pill("no data", "muted")
    elif proj_count == 0:
        projects_pill = _panel_status_pill("all unattributed", "warning")
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
  <title>Halyard Glass Cockpit</title>
  <style>{_CSS}</style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">
          <svg viewBox="0 0 24 24" role="img" aria-label="Halyard">
            <circle cx="12" cy="5" r="3"/>
            <path d="M12 8v14"/>
            <path d="M5 12H2a10 10 0 0 0 20 0h-3"/>
          </svg>
        </div>
        <div>
          <p class="eyebrow">Halyard Glass Cockpit</p>
          <h1>{_e(state.project_dir.name)}</h1>
        </div>
      </div>
      <div class="status status-{health_level}">{_e(health_level.title())}</div>
    </header>

    <section class="metrics" aria-label="Today summary">
      {_timer_metric(state.active_timer)}
      {_metric("Human Time", format_minutes(human_time.today_minutes), "today", "normal")}
      {_metric("AI Sessions", str(len(report.sessions)), report.period_label, "normal")}
      {_metric("AI Cost", f"${report.total_cost:.2f}", "captured API cost", "money")}
    </section>

    <section class="grid">
      <article class="panel span-12">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Usage Analytics</p>
            <h2>Overview</h2>
          </div>
          <div class="pill-group"><span class="pill">30d</span><span class="pill">{_e(usage.summary.active_days)} active days</span></div>
        </div>
        {_usage_panel(usage)}
      </article>

      <article class="panel span-7">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Live Stream</p>
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
        <div class="health-list">{"".join(_health_row(check.label, check.status, check.detail) for check in state.health)}</div>
      </article>

      <article class="panel span-12 attention-{_e("on" if report.unattributed_count else "off")}">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Needs Attention</p>
            <h2>Unattributed Sessions</h2>
          </div>
          {unattr_pill}
        </div>
        {_unattributed_table(report.unattributed_sessions)}
      </article>

      <article class="panel span-12">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Work Trail</p>
            <h2>Trail · {_e(now.strftime("%B %Y"))}</h2>
          </div>
          <div class="pill-group">{trail_pill}</div>
        </div>
        {_trail_heatmap_html(report.sessions, now)}
      </article>

      <article class="panel span-6">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Human Work</p>
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
        {_bucket_table(report.by_tool, "Tool")}
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
          <div class="pill-group"><span class="pill">{_e(report.period_label)}</span>{costs_trust_pill}</div>
        </div>
        {_costs_panel(ledger, report.by_project, report.sessions)}
      </article>
    </section>

    <footer>
      Latest session: {_latest_label(latest)} · Generated {_e(state.generated_at.strftime("%Y-%m-%d %H:%M:%S"))}
    </footer>
  </main>
</body>
</html>"""


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
        value = "No active timer"
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
    for session in list(sessions)[-8:][::-1]:
        icon = _tool_icon(session.tool)
        dur = _duration_str(session.end - session.start)
        health = _health_badge(session)
        rows.append(
            "<tr>"
            f"<td>{_e(session.end.strftime('%H:%M'))}</td>"
            f"<td><span class='tool-icon tool-{_e(icon)}'>{_e(icon)}</span></td>"
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
    if session.tool_calls is not None:
        calls = session.tool_calls
        errors = session.tool_errors or 0
        if errors == 0:
            parts.append(f"<span class='trust-captured'>{calls}c 0e</span>")
        else:
            rate = errors / calls if calls else 1.0
            css = "trust-allocated" if rate < 0.25 else "trust-unallocated"
            parts.append(f"<span class='{css}'>{calls}c {errors}e</span>")
    if session.code_added is not None or session.code_removed is not None:
        added = session.code_added or 0
        removed = session.code_removed or 0
        parts.append(f"<span class='dim'>+{added}/-{removed}</span>")
    return " ".join(parts) if parts else "<span class='dim'>—</span>"


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
    for bucket in usage.by_tool[:4]:
        pct = int(bucket.session_share * 100)
        rows.append(
            "<div class='usage-row'>"
            f"<span>{_e(bucket.tool)}</span>"
            f"<div class='bar-wrap'><div class='bar bar-ok' style='width:{pct}%'></div></div>"
            f"<small>{bucket.sessions} · {pct}%</small>"
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
        rows.append(
            "<tr>"
            f"<td>{_e(bucket.label)}</td>"
            f"<td class='num'>{bucket.sessions}</td>"
            f"<td class='num'>${bucket.cost_usd:.2f}</td>"
            f"<td><div class='bar-cell'>"
            f"<div class='bar-wrap'><div class='bar' style='width:{pct}%'></div></div>"
            f"<span>{pct}%</span></div></td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Model</th><th>Sessions</th><th>Cost</th><th>Share</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
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
                f"<td class='num'>${bucket.cost_usd:.4f}</td>"
                "<td>—</td>"
                f"<td class='num'>${bucket.cost_usd:.4f}</td>"
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
            f"<td class='num'>${entry.direct_usd:.4f}</td>"
            f"<td class='num'>${entry.allocated_usd:.4f}</td>"
            f"<td class='num'><strong>${entry.total_usd:.4f}</strong></td>"
            f"<td><span class='trust trust-{_e(trust_cls)}'>{_e(entry.trust)}</span></td>"
            "</tr>"
        )
    if not rows:
        return '<p class="empty">No sessions this period.</p>'

    footer = (
        f"<tfoot><tr>"
        f"<td><strong>Total</strong></td><td></td>"
        f"<td class='num'><strong>${ledger.total_direct_usd:.4f}</strong></td>"
        f"<td class='num'><strong>${ledger.total_allocated_usd:.4f}</strong></td>"
        f"<td class='num'><strong>${ledger.total_usd:.4f}</strong></td>"
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
    for session in list(sessions)[-8:][::-1]:
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
        return '<p class="empty">No unattributed sessions. Everything is invoice-ready.</p>'
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


def _tool_icon(tool: str) -> str:
    t = tool.lower()
    if "claude" in t:
        return "C"
    if "cursor" in t:
        return "X"
    if "gemini" in t:
        return "G"
    if "codex" in t:
        return "O"
    return "A"


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
        "<span class='trail-cell trail-none'></span><span>none</span>"
        "<span class='trail-cell trail-unattr'></span><span>unattributed</span>"
        "<span class='trail-cell trail-partial'></span><span>partial</span>"
        "<span class='trail-cell trail-full'></span><span>attributed</span>"
        "</div>"
    )
    return "<div class='trail-cal'>" + header + "".join(rows_html) + "</div>" + legend


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
.tool-icon { display: inline-block; width: 18px; height: 18px; border-radius: 4px; font-size: 11px; font-weight: 800; text-align: center; line-height: 18px; }
.tool-C { background: rgba(69, 214, 208, .15); color: var(--cyan); }
.tool-X { background: rgba(112, 225, 143, .12); color: var(--green); }
.tool-G { background: rgba(243, 191, 91, .12); color: var(--amber); }
.tool-O, .tool-A { background: rgba(255,255,255,.08); color: var(--muted); }

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

@media (max-width: 1100px) {
  body { min-width: 760px; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .span-7, .span-6, .span-5, .span-4, .span-3 { grid-column: span 12; }
  .usage-grid { grid-template-columns: 1fr; }
  .usage-stats, .usage-warnings { grid-column: span 1; }
  .usage-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
"""
