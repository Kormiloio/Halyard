"""Local Glass Cockpit dashboard server."""

# ruff: noqa: E501

from __future__ import annotations

import html
import socket
import webbrowser
from collections.abc import Iterable
from datetime import timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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

      <article class="panel span-12 attention-{_e("on" if report.unattributed_count else "off")}">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Needs Attention</p>
            <h2>Unattributed Sessions</h2>
          </div>
          <span class="pill">{report.unattributed_count} open</span>
        </div>
        {_unattributed_table(report.unattributed_sessions)}
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

      <article class="panel span-4">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Mix</p>
            <h2>Models</h2>
          </div>
        </div>
        {_model_table(report.by_model)}
      </article>

      <article class="panel span-4">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Capture</p>
            <h2>Tools</h2>
          </div>
        </div>
        {_bucket_table(report.by_tool, "Tool")}
      </article>

      <article class="panel span-4">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Spend Limits</p>
            <h2>Budget</h2>
          </div>
        </div>
        {_budget_panel(budgets)}
      </article>

      <article class="panel span-12">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Cost Allocation</p>
            <h2>Costs</h2>
          </div>
          <span class="pill">{_e(report.period_label)}</span>
        </div>
        {_costs_panel(ledger, report.by_project)}
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
        return '<p class="empty">No AI sessions captured for this period.</p>'
    return (
        "<table><thead><tr><th>Time</th><th>Tool</th><th>Project</th><th>Model</th>"
        "<th>Dur</th><th>Tokens</th><th>Cost</th><th>Health</th></tr></thead><tbody>"
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


def _costs_panel(ledger: LedgerSummary | None, by_project: list[CostBucket]) -> str:
    if ledger is None:
        # No plans: show simple per-project totals, note that trust needs plans
        rows = []
        for bucket in by_project:
            rows.append(
                "<tr>"
                f"<td>{_e(bucket.label)}</td>"
                f"<td class='num'>{bucket.sessions}</td>"
                f"<td class='num'>${bucket.cost_usd:.4f}</td>"
                "<td>—</td>"
                f"<td class='num'>${bucket.cost_usd:.4f}</td>"
                f"<td><span class='trust trust-captured'>captured</span></td>"
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
        inferred_marker = ' <span class="inferred-dot" title="Project inferred from timeclock">~</span>' if entry.has_inferred_attribution else ""
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
        "<th>Tokens</th><th>Cost</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _time_table(buckets: Iterable[TimeBucket]) -> str:
    rows = []
    for bucket in buckets:
        rows.append(
            f"<tr><td>{_e(bucket.label)}</td><td class='num'>{_e(format_minutes(bucket.minutes))}</td></tr>"
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
.trust-inferred { background: rgba(255,255,255,.08); color: var(--muted); }
.trust-mixed { background: rgba(176, 159, 232, .2); color: var(--purple); }
.trust-unallocated { background: rgba(255,255,255,.06); color: var(--muted); }
.inferred-dot { color: var(--muted); font-size: 11px; cursor: help; }
.costs-note { font-size: 12px; color: var(--muted); margin-top: 12px; }

@media (max-width: 1100px) {
  body { min-width: 760px; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .span-7, .span-6, .span-5, .span-4, .span-3 { grid-column: span 12; }
}
"""
