"""Local Glass Cockpit dashboard server."""

# ruff: noqa: E501

from __future__ import annotations

import html
import socket
import webbrowser
from collections.abc import Iterable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from halyard.ai_log import AiSession
from halyard.reports import (
    CostBucket,
    DashboardState,
    TimeBucket,
    build_dashboard_state,
    format_minutes,
)


def run_dashboard(project_dir: Path, *, port: int = 0, open_browser: bool = False) -> str:
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


def _handler_for(project_dir: Path) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._send_dashboard(include_body=True)

        def do_HEAD(self) -> None:
            self._send_dashboard(include_body=False)

        def _send_dashboard(self, *, include_body: bool) -> None:
            if self.path not in {"/", "/index.html"}:
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            body = render_dashboard(project_dir).encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if include_body:
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
    timer_label = state.active_timer.slug if state.active_timer else "No active timer"
    timer_started = (
        f"{state.active_timer.elapsed_label} elapsed"
        if state.active_timer
        else "Start one with halyard start"
    )
    health_level = _overall_health(state)

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
      <div>
        <p class="eyebrow">Halyard Glass Cockpit</p>
        <h1>{_e(state.project_dir.name)}</h1>
      </div>
      <div class="status status-{health_level}">{_e(health_level.title())}</div>
    </header>

    <section class="metrics" aria-label="Today summary">
      {_metric("Active Project", timer_label, timer_started, "focus")}
      {_metric("Human Time", format_minutes(human_time.today_minutes), "today", "normal")}
      {_metric("AI Sessions", str(len(report.sessions)), report.period_label, "normal")}
      {_metric("AI Cost", f"${report.total_cost:.2f}", "captured API cost", "money")}
    </section>

    <section class="grid">
      <article class="panel span-7">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Live Stream</p>
            <h2>Recent AI Sessions</h2>
          </div>
          <span class="pill">refreshes every 10s</span>
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

      <article class="panel span-6">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Human Work</p>
            <h2>Timeclock</h2>
          </div>
          <span class="pill">{_e(format_minutes(human_time.month_minutes))} this month</span>
        </div>
        {_time_table(human_time.by_project)}
      </article>

      <article class="panel span-6">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Attribution</p>
            <h2>Projects</h2>
          </div>
        </div>
        {_bucket_table(report.by_project, "Project")}
      </article>

      <article class="panel span-3">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Mix</p>
            <h2>Models</h2>
          </div>
        </div>
        {_bucket_table(report.by_model, "Model")}
      </article>

      <article class="panel span-3">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Capture</p>
            <h2>Tools</h2>
          </div>
        </div>
        {_bucket_table(report.by_tool, "Tool")}
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


def _sessions_table(sessions: Iterable[AiSession]) -> str:
    rows = []
    for session in list(sessions)[-8:][::-1]:
        rows.append(
            "<tr>"
            f"<td>{_e(session.end.strftime('%H:%M'))}</td>"
            f"<td>{_e(session.project or '(unattributed)')}</td>"
            f"<td>{_e(session.model)}</td>"
            f"<td>{session.input_tokens:,} / {session.output_tokens:,}</td>"
            f"<td>${session.cost_usd:.4f}</td>"
            "</tr>"
        )
    if not rows:
        return '<p class="empty">No AI sessions captured for this period.</p>'
    return (
        "<table><thead><tr><th>Time</th><th>Project</th><th>Model</th>"
        "<th>Tokens</th><th>Cost</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _bucket_table(buckets: Iterable[CostBucket], label: str) -> str:
    rows = []
    for bucket in buckets:
        rows.append(
            "<tr>"
            f"<td>{_e(bucket.label)}</td>"
            f"<td>{bucket.sessions}</td>"
            f"<td>${bucket.cost_usd:.2f}</td>"
            "</tr>"
        )
    if not rows:
        return f'<p class="empty">No {label.lower()} data yet.</p>'
    return (
        f"<table><thead><tr><th>{_e(label)}</th><th>Sessions</th><th>Cost</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _time_table(buckets: Iterable[TimeBucket]) -> str:
    rows = []
    for bucket in buckets:
        rows.append(
            f"<tr><td>{_e(bucket.label)}</td><td>{_e(format_minutes(bucket.minutes))}</td></tr>"
        )
    if not rows:
        return '<p class="empty">No human time recorded this month.</p>'
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


def _e(value: object) -> str:
    return html.escape(str(value))


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
.span-6 { grid-column: span 6; }
.span-5 { grid-column: span 5; }
.span-3 { grid-column: span 3; }
.panel-head { min-height: 42px; display: flex; align-items: start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
th, td { border-bottom: 1px solid rgba(37, 64, 74, .72); padding: 10px 8px; text-align: left; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
th { color: var(--muted); font-size: 11px; text-transform: uppercase; }
.empty { min-height: 150px; display: grid; place-items: center; color: var(--muted); border: 1px dashed var(--line); border-radius: 8px; margin: 0; }
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
@media (max-width: 1100px) {
  body { min-width: 760px; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .span-7, .span-6, .span-5, .span-3 { grid-column: span 12; }
}
"""
