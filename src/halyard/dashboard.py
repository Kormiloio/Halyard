"""Local Bridge dashboard server — Halyard's web command center."""

# ruff: noqa: E501

from __future__ import annotations

import errno
import hmac
import html
import math
import socket
import webbrowser
from collections.abc import Iterable
from contextlib import suppress
from datetime import datetime, timedelta
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from jinja2 import Environment, Template

from halyard import leverage
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
    DailyUsageBucket,
    ModelUsageBucket,
    ToolUsageBucket,
    UsageAnalytics,
    build_usage_analytics,
    compact_number,
)

DASHBOARD_PORT = 7432

_TEMPLATE_DIR = Path(__file__).parent / "templates"


@lru_cache(maxsize=1)
def _env() -> Environment:
    """Return the shared, cached Jinja2 environment for dashboard templates.

    autoescape is on (HTML output); every injected fragment is already
    escaped via ``_e`` or is server-rendered HTML, so templates mark each
    with ``|safe``. Page chrome lives in ``templates/dashboard.html.j2`` and
    reusable panel markup in ``templates/panels/`` — this module composes the
    fragments and supplies pre-computed values.
    """
    from jinja2 import Environment, FileSystemLoader

    return Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)


@lru_cache(maxsize=1)
def _dashboard_template() -> Template:
    """Return the cached page-shell template."""
    return _env().get_template("dashboard.html.j2")


@lru_cache(maxsize=1)
def _panel_macros() -> Any:
    """Return the imported macro module from ``panels/_macros.html.j2``.

    Calling ``_panel_macros().data_table(...)`` renders a macro to a string
    so Python builders can keep their formatting logic while the table/row
    markup lives in the template.
    """
    return _env().get_template("panels/_macros.html.j2").module


class DashboardError(RuntimeError):
    """The dashboard server could not start (e.g. the port is taken).

    Carries an actionable, user-facing message so the CLI can surface a
    clean error instead of a raw socket traceback.
    """


def run_dashboard(
    project_dir: Path | None, *, port: int = DASHBOARD_PORT, open_browser: bool = False
) -> str:
    """Start the dashboard server and block until interrupted."""
    host = "127.0.0.1"
    # Bind to the loopback IP, but show the friendlier `localhost`
    # hostname (the Host-header allowlist already accepts both).
    display_host = "localhost"
    resolved = _resolve_port(port)
    try:
        server = ThreadingHTTPServer((host, resolved), _handler_for(project_dir))
    except OSError as exc:
        # Windows raises WSAEACCES (WinError 10013) → PermissionError(EACCES)
        # when a 2nd process tries to bind a port the first one already holds —
        # treat it the same as POSIX's EADDRINUSE.
        if exc.errno in (errno.EADDRINUSE, errno.EACCES):
            raise DashboardError(
                f"port {resolved} is already in use — another `halyard dashboard` "
                f"is likely running. Open the existing one at "
                f"http://{display_host}:{resolved}/, stop it with "
                f"'lsof -ti :{resolved} | xargs kill', or start this one on "
                f"another port with '--port <N>'."
            ) from exc
        raise

    # v5.19/B3-page-followup: every GET now requires the token, so the URL we
    # PRINT must carry it — otherwise the documented quickstart (`halyard
    # dashboard`, then paste the URL into a browser) returns 401. The
    # printed URL is local-only (loopback bind, Host allowlist) and the
    # token is a per-user 0600 secret, so embedding it in the line we
    # print to the user's own terminal is no worse than the launch URL we
    # already feed to the browser.
    from halyard.service import _load_or_create_token

    token = _load_or_create_token()
    base_url = f"http://{display_host}:{server.server_port}/"
    auth_url = f"{base_url}?token={token}"
    print(f"Halyard · The Bridge: {auth_url}")
    print("Press Ctrl-C to stop.")

    if open_browser:
        # v5.19/B3: hand the token to the browser via the launch URL, not via
        # an unconditional Set-Cookie on every GET. The server only returns the
        # auth cookie to a request that already presents the token, so a
        # co-located user who GETs the page cannot harvest it.
        webbrowser.open(auth_url)

    # v4.0: Halyard Hub. The Hub acts as a central telemetry broker and
    # exclusive writer for the ledger. It includes the OTLP/HTTP receiver
    # (v3.12) and the direct-ingest endpoint (v4.0).
    # Bind the configured port so the embedded Hub and hub_client agree. NOTE:
    # the OTLP/HTTP default is 4318; if HALYARD_HUB_PORT moves the Hub off 4318,
    # external OTLP emitters (e.g. VS Code) must be pointed at the new port too.
    from halyard.hub_client import hub_port
    from halyard.hub_server import HubServer

    hub: HubServer | None = HubServer(project_dir, port=hub_port())
    try:
        if hub is not None:
            hub.start()
    except OSError:
        hub = None  # best-effort: don't crash if port is taken

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if hub is not None:
            hub.stop()

    return auth_url


UsageRangeOpt = Literal["all", "30d", "7d"]
UsageTabOpt = Literal["overview", "models"]


def render_dashboard(
    project_dir: Path | None = None,
    *,
    usage_range: UsageRangeOpt = "30d",
    usage_tab: UsageTabOpt = "overview",
    wake_month: str | None = None,
) -> str:
    """Render the dashboard HTML for tests and the HTTP handler.

    ``project_dir is None`` → aggregate every real registered project
    log + hub (the default for ``halyard dashboard``). An explicit path
    scopes to that single project.

    ``usage_range`` controls the Usage Analytics window (7d/30d/all).
    ``usage_tab`` selects between the Overview panel and the per-day-by-
    model breakdown panel.

    ``wake_month`` is a ``YYYY-MM`` string scoping only the Wake panel.
    Invalid or future values fall back to the current month.
    """
    from halyard.reports import build_aggregate_dashboard_state

    state = (
        build_aggregate_dashboard_state()
        if project_dir is None
        else build_dashboard_state(project_dir)
    )
    return _render_state(
        state,
        usage_range=usage_range,
        usage_tab=usage_tab,
        wake_month_raw=wake_month,
    )


def _handler_for(
    project_dir: Path | None, token: str | None = None
) -> type[BaseHTTPRequestHandler]:
    from halyard.service import _load_or_create_token

    _token: str = token if token is not None else _load_or_create_token()

    # GET renders `project_dir` (None ⇒ aggregate every real project).
    # POST timer/voyage actions need a concrete dir: the current
    # project, else the hub, else cwd.
    def _action_dir() -> Path:
        if project_dir is not None:
            return project_dir
        from halyard.ai_log import find_project_dir
        from halyard.hub import find_hub

        return find_project_dir() or find_hub() or Path.cwd()

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            server_port = self.server.server_port  # type: ignore[attr-defined]
            host = self.headers.get("Host", "")
            if host not in {f"127.0.0.1:{server_port}", f"localhost:{server_port}"}:
                self.send_error(HTTPStatus.BAD_REQUEST, "invalid Host header")
                return
            # v5.19/B3-page: require the token to render the page itself. The
            # full dashboard HTML embeds ledger contents (costs, projects,
            # branches, session metadata, home-directory paths) and on a
            # shared host any co-located user could `curl /` for it. The
            # browser arrives via the launch URL `?token=`, which authorises
            # this request and earns the Set-Cookie for subsequent loads.
            if not self._request_token_valid():
                self._send_unauthorized()
                return
            self._send_dashboard(include_body=True)

        def do_HEAD(self) -> None:
            server_port = self.server.server_port  # type: ignore[attr-defined]
            host = self.headers.get("Host", "")
            if host not in {f"127.0.0.1:{server_port}", f"localhost:{server_port}"}:
                self.send_error(HTTPStatus.BAD_REQUEST, "invalid Host header")
                return
            if not self._request_token_valid():
                self._send_unauthorized(include_body=False)
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
            if not hmac.compare_digest(submitted_token, _token):
                self._send_json_error(HTTPStatus.UNAUTHORIZED, "missing or invalid token")
                return

            length = content_length
            body = self.rfile.read(length).decode(errors="replace") if length else ""
            params = {k: v[0] for k, v in parse_qs(body).items()}

            if self.path == "/api/start":
                slug = params.get("project", "").strip()
                from halyard.slug import is_valid_timer_slug

                if is_valid_timer_slug(slug):
                    # v2.17 task 5.5: delegate to shared start_timer; ignores
                    # TimerAlreadyRunning (dashboard silently no-ops on duplicate start)
                    from halyard.orchestration import (
                        HubStateError,
                        TimerAlreadyRunning,
                        start_timer,
                    )

                    account = slug.replace("/", ":", 1)
                    with suppress(TimerAlreadyRunning, HubStateError):
                        start_timer(_action_dir(), account)

            elif self.path == "/api/stop":
                # v2.17 task 5.5: delegate to shared stop_timer
                from halyard.orchestration import stop_timer

                stop_timer(_action_dir())
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/?stopped=1")
                self.end_headers()
                return

            elif self.path == "/api/voyage-refresh":
                from halyard.ai_log import parse_sessions
                from halyard.voyages import check_auto_complete

                _adir = _action_dir()
                all_sessions = parse_sessions(_adir)
                sessions_by_project: dict[str, list[AiSession]] = {}
                for s in all_sessions:
                    if s.project:
                        sessions_by_project.setdefault(s.project, []).append(s)
                check_auto_complete(_adir, sessions_by_project)

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
            raw_month = (qs.get("month") or [""])[0] or None
            usage_range: UsageRangeOpt = (
                raw_range if raw_range in ("7d", "30d", "all") else "30d"  # type: ignore[assignment]
            )
            usage_tab: UsageTabOpt = (
                raw_tab if raw_tab in ("overview", "models") else "overview"  # type: ignore[assignment]
            )
            body = render_dashboard(
                project_dir,
                usage_range=usage_range,
                usage_tab=usage_tab,
                wake_month=raw_month,
            ).encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            # v5.19/B3: only set the token cookie for a request that ALREADY
            # presents the token (launch-URL ?token=, header, or an existing
            # cookie). Previously every GET got the cookie, so any local user
            # could `curl` the page and harvest the token — which post-B4
            # grants full write access. HttpOnly blocks JS; SameSite=Strict
            # blocks CSRF.
            if self._request_token_valid():
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

        def _request_token_valid(self) -> bool:
            """v5.19/B3: True if the request carries the valid token via header,
            cookie, or the launch-URL ``?token=`` param. Constant-time compare."""
            from urllib.parse import parse_qs, urlparse

            submitted = self._extract_token()
            if not submitted:
                vals = parse_qs(urlparse(self.path).query).get("token")
                if vals:
                    submitted = vals[0]
            return bool(submitted) and hmac.compare_digest(submitted, _token)

        def _send_unauthorized(self, *, include_body: bool = True) -> None:
            """v5.19/B3-page: terse 401 with a hint to use the launch URL.
            Plain text so curl users get an actionable error; no token leak."""
            body = (
                b"401 Unauthorized\n\n"
                b"The Halyard dashboard requires the local token. Start it "
                b"with `halyard dashboard --open` (which launches a browser "
                b"at the authorised URL), or copy the URL printed when you "
                b"ran `halyard dashboard` (it includes a ?token=... query "
                b"param) instead of navigating to this address directly.\n"
            )
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if include_body:
                self.wfile.write(body)

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


def _moat_panel(state: DashboardState) -> str:
    """The moat surface — project/client + $ + confidence + outcome.

    Views no single-tool dashboard can draw. Rendered ABOVE the
    commodity Usage Analytics panel (moat is primary; parity is the
    floor). Server-rendered, static, no JS.
    """
    from halyard.moat import cost_by_client, leakage, project_evidence

    sessions = state.all_sessions
    if not sessions:
        return ""

    evidence = project_evidence(sessions, state.project_dir)
    cbc = cost_by_client(sessions)
    by_proj_cost: dict[str, float] = {}
    for pt in cbc:
        by_proj_cost[pt.project] = by_proj_cost.get(pt.project, 0.0) + pt.cost_usd
    max_cost = max(by_proj_cost.values(), default=0.0) or 1.0

    cost_rows = "".join(
        (
            f'<tr><td class="model-name">{_e(proj)}</td>'
            f'<td class="num">${cost:,.2f}</td>'
            f'<td><div class="voyage-bar-outer">'
            f'<div class="voyage-bar-fill" style="width:{int(100 * cost / max_cost)}%">'
            f"</div></div></td></tr>"
        )
        for proj, cost in sorted(by_proj_cost.items(), key=lambda kv: -kv[1])
    )

    ev_rows = "".join(
        (
            f"<tr><td class='model-name'>{_e(e.project)}</td>"
            f"<td class='num'>{'—' if e.human_minutes is None else f'{e.human_minutes // 60}h{e.human_minutes % 60:02d}m'}</td>"
            f"<td class='num'>${e.ai_cost_usd:,.2f}</td>"
            f"<td class='num'>{e.sessions}</td>"
            f"<td class='num'>▲{e.shipped} ◐{e.in_flight} ✗{e.abandoned} ·{e.no_pr}</td>"
            f"<td><span class='pill'>{_e(e.confidence)}</span></td></tr>"
        )
        for e in evidence
    )

    leaks = leakage(Path.home() / ".halyard" / "unattributed.log")
    if leaks:
        leak_rows = "".join(
            (
                f"<tr><td class='model-name'>{_e(r.remote)}</td>"
                f"<td class='num'>{r.sessions}</td>"
                f"<td class='num'>${r.cost_usd:,.2f}</td>"
                f"<td><code>{_e(r.fix_command)}</code></td></tr>"
            )
            for r in leaks
        )
        leak_html = (
            "<h3 class='mini-head'>Leakage — adrift value, one command from recovered</h3>"
            + _stbl("leakage", "t,n,n,x", "usage-models-rows")
            + "<thead><tr>"
            "<th>Remote</th><th class='num'>Sessions</th><th class='num'>Cost</th>"
            "<th>Fix (proposed — not run)</th></tr></thead>"
            f"<tbody>{leak_rows}</tbody></table>"
        )
    else:
        leak_html = "<p class='mini-empty'>No adrift sessions — full attribution.</p>"

    return f"""
      <article class="panel span-12" data-panel="moat">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Moat · what no single-tool dashboard can show</p>
            <h2>Project Evidence</h2>
          </div>
        </div>
        <h3 class="mini-head">Billable evidence · per client project</h3>
        {_stbl("billable-evidence", "t,x,n,n,x,x", "usage-models-rows")}<thead><tr>
          <th>Project</th><th class="num">Human</th><th class="num">AI&nbsp;cost</th>
          <th class="num">Sessions</th><th class="num">▲ship ◐open ✗closed ·none</th>
          <th>Attribution</th></tr></thead>
          <tbody>{ev_rows}</tbody></table>
        <h3 class="mini-head">Cost by client</h3>
        <table class="usage-models-rows"><tbody>{cost_rows}</tbody></table>
        {leak_html}
      </article>"""


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
        from halyard.attribution import format_attribution_mix

        attr_col = (
            f'<div class="voyage-col">'
            f'<span class="voyage-label">Attribution</span>'
            f'<span class="voyage-value" style="font-size:0.8rem">'
            f"{_e(format_attribution_mix(watch))}</span>"
            f'<span class="voyage-sub">timer &gt; mapped &gt; toml &gt; auto</span></div>'
            if total
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
          {attr_col}
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
      <article class="panel span-12" data-panel="voyage">
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
    wake_month_raw: str | None = None,
) -> str:
    report = state.report
    human_time = state.human_time
    latest = state.latest_session
    health_level = _overall_health(state)
    usage = build_usage_analytics(state.all_sessions, range_key=usage_range, now=state.generated_at)

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

    collision_count = len(state.collisions)
    collisions_pill = (
        _panel_status_pill(
            f"{collision_count} branch{'es' if collision_count != 1 else ''}", "warning"
        )
        if collision_count
        else _panel_status_pill("no overlap", "healthy")
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

    wake_period = _resolve_wake_period(wake_month_raw, now)
    wake_month_param = wake_period.strftime("%Y-%m")
    is_current_wake = (wake_period.year, wake_period.month) == (now.year, now.month)
    wake_sessions = (
        report.sessions
        if is_current_wake
        else [
            s
            for s in state.all_sessions
            if s.start.year == wake_period.year and s.start.month == wake_period.month
        ]
    )
    trail_month_sessions = [
        s
        for s in wake_sessions
        if s.start.date().year == wake_period.year and s.start.date().month == wake_period.month
    ]
    trail_active_days = len({s.start.date() for s in trail_month_sessions})
    trail_pill = _panel_status_pill(
        f"{trail_active_days} active day{'s' if trail_active_days != 1 else ''}",
        "muted" if trail_active_days else "warning",
    )

    # v5.18/B22: clamp the prev-month target at the bottom of the calendar.
    # _shift_month(datetime(1, 1, 1), -1) would build year 0 and raise
    # ValueError ("year 0 is out of range"), which previously took down the
    # whole render with an unhandled 500. Don't emit a prev link below the
    # earliest representable month.
    if (wake_period.year, wake_period.month) <= (datetime.min.year, 1):
        wake_prev_href = ""
    else:
        prev_param = _shift_month(wake_period, -1).strftime("%Y-%m")
        wake_prev_href = _dash_href(
            usage_range=usage_range, usage_tab=usage_tab, wake_month=prev_param
        )
    if is_current_wake:
        wake_next_href = ""
    else:
        next_period = _shift_month(wake_period, 1)
        next_param: str | None = next_period.strftime("%Y-%m")
        if (next_period.year, next_period.month) == (now.year, now.month):
            # Don't carry the param when next click lands on "current"; keeps URLs clean.
            next_param = None
        wake_next_href = _dash_href(
            usage_range=usage_range, usage_tab=usage_tab, wake_month=next_param
        )

    context = {
        "css": _load_css(),
        "overview_panels": _overview_panels(state, usage),
        "title": (
            _e(f"All Projects · {state.aggregate_count}")
            if state.aggregate_count
            else _e(state.project_dir.name)
        ),
        "health_level": health_level,
        "health_pill_title": _e(_health_pill_title(state.health)),
        "health_level_title": _e(health_level.title()),
        "health_popup": _health_popup(state.health),
        "timer_metric": _timer_metric(state.active_timer, state.timer_collision),
        "metric_human": _metric(
            "Human Time",
            format_minutes(human_time.today_minutes or human_time.presence_minutes),
            "today"
            if human_time.today_minutes > 0
            else ("today · auto-detected" if human_time.presence_minutes > 0 else "today"),
            "normal",
            "human-time",
        ),
        "metric_sessions": _metric(
            "AI Sessions",
            str(len(report.sessions)),
            report.period_label,
            "normal",
            "ai-sessions",
        ),
        "metric_cost": _metric(
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
            "ai-cost",
        ),
        "voyage_panel": _voyage_panel(state),
        "captains_panel": _captains_quarters_panel(state.project_dir, report.sessions),
        "friends_panel": _friends_panel(state.project_dir, report.sessions),
        "moat_panel": _moat_panel(state),
        "usage_h2": "Models" if usage_tab == "models" else "Overview",
        "range_control": _range_control(
            usage_range, usage_tab, wake_month=None if is_current_wake else wake_month_param
        ),
        "tab_control": _tab_control(
            usage_tab, usage_range, wake_month=None if is_current_wake else wake_month_param
        ),
        "active_days": _e(usage.summary.active_days),
        "usage_body": (
            _usage_panel(usage) if usage_tab == "overview" else _usage_models_panel(usage)
        ),
        "leverage_panel": _leverage_panel(state.all_sessions, state.generated_at),
        "morse_wake": _morse("WAKE"),
        "wake_month": _e(wake_period.strftime("%B %Y")),
        # Hrefs are not pre-escaped — Jinja autoescape encodes them once; an
        # extra _e() round produces `&amp;amp;` in the rendered output.
        "wake_prev_href": wake_prev_href,
        "wake_next_href": wake_next_href,
        "trail_pill": trail_pill,
        "trail_heatmap": _trail_heatmap_html(wake_sessions, wake_period),
        "tools_pill": tools_pill,
        "tool_table": _tool_table(report.by_tool_usage),
        "morse_log": _morse("LOG"),
        "sessions_pill": sessions_pill,
        "sessions_table": _sessions_table(report.sessions),
        "health_rows": "".join(
            _health_row(check.label, check.status, check.detail) for check in state.health
        ),
        "adrift_attention": _e("on" if report.unattributed_count else "off"),
        "unattr_pill": unattr_pill,
        "unattributed_table": _unattributed_table(report.unattributed_sessions),
        "collisions_attention": _e("on" if state.collisions else "off"),
        "collisions_pill": collisions_pill,
        "collisions_panel": _collisions_panel(state.collisions),
        "morse_time": _morse("TIME"),
        "time_pill": time_pill,
        "time_table": _time_table(human_time.by_project),
        "projects_pill": projects_pill,
        "bucket_table": _bucket_table(report.by_project, "Project"),
        "models_pill": models_pill,
        "model_table": _model_table(report.by_model),
        "surface_panel": (_surface_panel(report.by_tool_surface) if report.by_tool_surface else ""),
        "budget_pill": budget_pill,
        "budget_panel": _budget_panel(budgets),
        "period_label": _e(report.period_label),
        "costs_trust_pill": costs_trust_pill,
        "costs_panel": _costs_panel(ledger, report.by_project, report.sessions),
        "latest_label": _latest_label(latest),
        "generated": _e(state.generated_at.strftime("%Y-%m-%d %H:%M:%S")),
        "scripts": "".join(
            (
                _scroll_preserve_script(),
                _layout_script(),
                _health_popup_script(),
                _celebration_script(),
                _easter_egg_script(),
                _table_sort_script(),
                _tabs_script(),
                _refresh_script(),
            )
        ),
    }
    return _dashboard_template().render(**context)


def _refresh_script() -> str:
    """Partial in-place refresh (v5.6) — replaces the old full-page
    ``<meta refresh>``.

    A 10s timer plus Hub SSE events fetch the page and swap only the
    ``#metrics`` and ``#grid`` regions' contents, then re-run the table-sort
    and layout re-apply hooks so column sort, saved panel order, and collapse
    state survive the swap. No navigation, so scroll and focus are preserved.
    Fail-safe: any error leaves the server-rendered dashboard intact, and with
    JS disabled the page still renders fully on load (it just doesn't
    auto-update).
    """
    import json
    from urllib.parse import urlencode

    from halyard.hub_client import hub_url
    from halyard.service import _load_or_create_token

    # v5.19/B4: the hub's /v1/events now requires auth, but EventSource cannot
    # set request headers — pass the token as a query param. The dashboard page
    # is itself auth-gated (B3), so only the legitimate user receives this URL.
    _qs = urlencode({"token": _load_or_create_token()})
    events_url = json.dumps(f"{hub_url()}/v1/events?{_qs}")
    return """<script>
(function(){
  try {
    var REGIONS = ['metrics', 'grid'];
    var pending = false;
    function reinit() {
      if (window.HalyardBootTables) window.HalyardBootTables();
      if (window.HalyardApplyLayout) window.HalyardApplyLayout();
      if (window.HalyardApplyTabs) window.HalyardApplyTabs();
    }
    function refresh() {
      if (pending) return;
      pending = true;
      fetch(window.location.href, {
        cache: 'no-store',
        credentials: 'same-origin',
        headers: {'X-Halyard-Fragment': '1'}
      }).then(function(resp) {
        if (!resp.ok) throw new Error('dashboard refresh failed');
        return resp.text();
      }).then(function(html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var swapped = false;
        REGIONS.forEach(function(id) {
          var cur = document.getElementById(id);
          var next = doc.getElementById(id);
          if (cur && next) { cur.innerHTML = next.innerHTML; swapped = true; }
        });
        if (swapped) reinit();
      }).catch(function(err) {
        if (window.console) console.debug('Halyard refresh skipped:', err);
      }).finally(function() {
        pending = false;
      });
    }
    // Periodic refresh replaces the old full-page <meta refresh>.
    setInterval(refresh, 10000);
    // Instant refresh on Hub events.
    try {
      var wanted = {
        session_ingested: 1, collision_detected: 1,
        timer_started: 1, timer_stopped: 1, timer_updated: 1
      };
      var source = new EventSource(__HUB_EVENTS_URL__);
      source.onmessage = function(event) {
        var msg = JSON.parse(event.data);
        if (wanted[msg.type]) refresh();
      };
      source.onerror = function() { source.close(); };
    } catch (e) {}
  } catch (e) {}
})();
</script>""".replace("__HUB_EVENTS_URL__", events_url)


def _tabs_script() -> str:
    """v5.7: client-side tab filter. Every panel stays in the DOM; only the
    active tab's panels show (the 'all' tab shows everything). The panel->tab
    mapping lives here so no per-panel markup change is needed; Overview panels
    carry their own data-tab. Active tab persists in localStorage and is
    re-applied after a partial refresh via window.HalyardApplyTabs."""
    return """<script>
(function(){
  var KEY='halyard-tab-v1';
  var TAB_OF={
    voyage:'voyage','captains-quarters':'voyage',friends:'voyage',wake:'voyage',
    moat:'money',projects:'money',budget:'money',costs:'money',
    sessions:'sessions',adrift:'sessions',collisions:'sessions',tools:'sessions',
    timeclock:'sessions',surface:'sessions',
    usage:'health',health:'health',models:'health',leverage:'health'
  };
  function active(){ return localStorage.getItem(KEY) || 'overview'; }
  function tabOf(p){ return p.getAttribute('data-tab') || TAB_OF[p.getAttribute('data-panel')] || 'all'; }
  function apply(){
    var a=active();
    document.querySelectorAll('.tabbar .tab').forEach(function(t){
      t.classList.toggle('active', t.getAttribute('data-tab')===a);
    });
    document.querySelectorAll('#grid > [data-panel]').forEach(function(p){
      p.classList.toggle('tab-hidden', a!=='all' && tabOf(p)!==a);
    });
  }
  window.HalyardApplyTabs=apply;
  document.addEventListener('click',function(e){
    var b=e.target.closest('.tabbar .tab'); if(!b)return;
    e.preventDefault();
    localStorage.setItem(KEY, b.getAttribute('data-tab'));
    apply();
  });
  try { apply(); } catch(e) {}
})();
</script>"""


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
      <article class="panel span-12" data-panel="captains-quarters">
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
      <article class="panel span-12" data-panel="friends">
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


def _failing_checks(health: object) -> list[object]:
    checks = health if isinstance(health, list) else []
    return [c for c in checks if getattr(c, "status", "") in ("warning", "error")]


def _health_pill_title(health: object) -> str:
    failing = _failing_checks(health)
    if not failing:
        return "All systems healthy"
    n = len(failing)
    noun = "check needs" if n == 1 else "checks need"
    return f"{n} {noun} attention — click for detail"


def _health_popup(health: object) -> str:
    failing = _failing_checks(health)
    if not failing:
        body = '<p class="health-popup-ok">✓ All systems healthy.</p>'
    else:
        rows = []
        for c in failing:
            status = _e(getattr(c, "status", ""))
            label = _e(getattr(c, "label", ""))
            detail = _e(getattr(c, "detail", ""))
            rows.append(
                f'<div class="health-popup-row">'
                f'<span class="dot dot-{status}"></span>'
                f"<div><strong>{label}</strong>"
                f'<p class="health-popup-detail">{detail}</p></div></div>'
            )
        rows.append(
            '<p class="health-popup-fix">For full diagnostics and how to '
            "fix each item, run <code>halyard doctor</code> in your terminal.</p>"
        )
        body = "".join(rows)
    return f"""
    <div id="health-popup" class="health-popup" hidden role="dialog" aria-label="System health">
      <div class="health-popup-backdrop" data-health-close></div>
      <div class="health-popup-card">
        <div class="health-popup-head">
          <strong>System Health</strong>
          <button type="button" class="health-popup-x" data-health-close
            aria-label="Close">✕</button>
        </div>
        <div class="health-popup-body">{body}</div>
      </div>
    </div>"""


def _health_popup_script() -> str:
    return """<script>
(function(){
  try {
    var pill = document.getElementById('health-pill');
    var pop = document.getElementById('health-popup');
    if (!pill || !pop) return;
    function open(){ pop.hidden = false; pop.classList.add('open'); }
    function close(){ pop.hidden = true; pop.classList.remove('open'); }
    pill.addEventListener('click', function(){
      if (pop.hidden) { open(); } else { close(); }
    });
    pop.addEventListener('click', function(ev){
      if (ev.target && ev.target.hasAttribute('data-health-close')) close();
    });
    document.addEventListener('keydown', function(ev){
      if (ev.key === 'Escape' && !pop.hidden) close();
    });
  } catch (e) {
    if (window.console) console.warn('Halyard health popup failed:', e);
  }
})();
</script>"""


def _metric(label: str, value: str, detail: str, tone: str, panel_id: str) -> str:
    return f"""
      <article class="metric metric-{tone}" data-panel="{panel_id}" data-hub-fragment="{panel_id}">
        <span>{_e(label)}</span>
        <strong>{_e(value)}</strong>
        <small>{_e(detail)}</small>
      </article>
    """


def _timer_metric(active_timer: object, collision: object = None) -> str:
    from halyard.reports import ActiveTimer, TimerCollision

    timer = active_timer if isinstance(active_timer, ActiveTimer) else None
    coll = collision if isinstance(collision, TimerCollision) else None
    collision_html = ""
    if coll:
        m = coll.seconds_ago // 60
        time_str = f"{m}m ago" if m > 0 else "just now"
        collision_html = f"""
            <div class="collision-alert">
                <span>⚠️ Collision</span>
                <small>Branch '{_e(coll.branch)}' busy ({_e(coll.tool)}) {time_str}</small>
            </div>
            """

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
      <article class="metric metric-focus" data-panel="timer" data-hub-fragment="timer">
        <span>Active Project</span>
        <strong>{value}</strong>
        <small>{detail}</small>
        {collision_html}
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
        branch_tag = (
            f"<br><small class='muted'>{_e(session.branch)}</small>" if session.branch else ""
        )
        rows.append(
            [
                {"html": _e(session.end.strftime("%H:%M"))},
                {"html": f"<span class='tool-icon tool-{_e(css_key)}'>{emoji}</span>"},
                {"html": f"{_e(session.project or '(unattributed)')}{branch_tag}"},
                {"html": _e(session.model)},
                {"cls": "num", "html": _e(dur)},
                {
                    "cls": "num",
                    "sortval": session.input_tokens + session.output_tokens,
                    "html": f"{session.input_tokens:,} / {session.output_tokens:,}",
                },
                {"cls": "num", "html": f"${session.cost_usd:.4f}"},
                {"cls": "num", "sev": _session_sev(session), "html": health},
            ]
        )
    if not rows:
        return '<p class="empty">No AI sessions captured this period.<br>Start Claude Code, Cursor, or Gemini CLI in this directory.</p>'
    return str(
        _panel_macros().data_table(
            "recent-sessions",
            "m,x,x,x,x,n,n,s",
            ["Time", "Tool", "Project", "Model", "Dur", "In / Out", "Cost", "Health"],
            rows,
        )
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


def _session_sev(session: AiSession) -> int:
    """Severity rank for sorting the Health column (v2.73): 0 ok,
    1 warn, 2 error — never the glyph text."""
    if (
        (session.tool_errors or 0) > 0
        or session.test_status == "fail"
        or session.build_status == "fail"
    ):
        return 2
    if not session.tokens_available or session.interaction_data_available is False:
        return 1
    return 0


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


def _dash_href(
    *,
    usage_range: UsageRangeOpt,
    usage_tab: UsageTabOpt,
    wake_month: str | None = None,
) -> str:
    """Build a ``?range=…&tab=…[&month=YYYY-MM]`` href that preserves panel state."""
    from urllib.parse import urlencode

    params: list[tuple[str, str]] = [("range", usage_range), ("tab", usage_tab)]
    if wake_month:
        params.append(("month", wake_month))
    return "?" + urlencode(params)


def _range_control(
    current: UsageRangeOpt, tab: UsageTabOpt, *, wake_month: str | None = None
) -> str:
    """Render a three-button segmented control for the Usage range window."""
    opts: list[tuple[UsageRangeOpt, str]] = [("7d", "7d"), ("30d", "30d"), ("all", "All")]
    parts = []
    for key, label in opts:
        cls = "pill pill-segment"
        if key == current:
            cls += " pill-active"
        href = _dash_href(usage_range=key, usage_tab=tab, wake_month=wake_month)
        parts.append(f"<a class='{cls}' href='{href}'>{_e(label)}</a>")
    return "<div class='segment-group' role='group' aria-label='Range'>" + "".join(parts) + "</div>"


def _tab_control(
    current: UsageTabOpt, usage_range: UsageRangeOpt, *, wake_month: str | None = None
) -> str:
    """Render an Overview/Models segmented control."""
    opts: list[tuple[UsageTabOpt, str]] = [("overview", "Overview"), ("models", "Models")]
    parts = []
    for key, label in opts:
        cls = "pill pill-segment"
        if key == current:
            cls += " pill-active"
        href = _dash_href(usage_range=usage_range, usage_tab=key, wake_month=wake_month)
        parts.append(f"<a class='{cls}' href='{href}'>{_e(label)}</a>")
    return "<div class='segment-group' role='group' aria-label='Tab'>" + "".join(parts) + "</div>"


def _resolve_wake_period(raw: str | None, now: datetime) -> datetime:
    """Parse ``YYYY-MM``; fall back to ``now``'s month on bad / future input."""
    if not raw:
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    try:
        year_s, month_s = raw.split("-", 1)
        year = int(year_s)
        month = int(month_s)
        if not (1 <= month <= 12):
            raise ValueError
        candidate = datetime(year, month, 1)
    except (ValueError, TypeError):
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    current = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if candidate > current:
        return current
    return candidate


def _shift_month(period: datetime, delta: int) -> datetime:
    """Return ``period`` shifted by ``delta`` months (+1 / -1)."""
    total = period.year * 12 + (period.month - 1) + delta
    return datetime(total // 12, (total % 12) + 1, 1)


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
    """Render an SVG stacked bar chart: x = day, y = in+out tokens, stack = model.

    v2.64: uses the *real* per-day per-model input/output split now
    retained in ``DailyUsageBucket.model_io`` (multi-model aware) — no
    longer the window-wide proportional approximation. Each segment is
    that model's actual in+out for that day and the tooltip states the
    true number.
    """
    days = usage.daily

    def _day_io(d: DailyUsageBucket) -> int:
        return sum(i + o for i, o in d.model_io.values())

    max_tokens = max((_day_io(d) for d in days), default=0)
    if max_tokens <= 0:
        return "<p class='mini-empty'>No token data.</p>"

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
    for frac, label in [
        (0, "0"),
        (0.5, compact_number(int(max_tokens * 0.5))),
        (1.0, compact_number(max_tokens)),
    ]:
        y = chart_h - frac * chart_h + 8
        y_lines.append(
            f"<line x1='{pad_left}' y1='{y}' x2='{pad_left + chart_w}' y2='{y}' "
            f"stroke='rgba(255,255,255,0.06)' stroke-width='1'/>"
            f"<text x='{pad_left - 6}' y='{y + 3}' fill='rgba(255,255,255,0.5)' "
            f"font-size='10' text-anchor='end'>{_e(label)}</text>"
        )

    for i, day in enumerate(days):
        x = pad_left + i * bar_w
        day_io = _day_io(day)
        if day_io <= 0:
            continue
        # Stack segments per model using REAL per-day per-model in+out.
        # Rank order follows by_model so colours are stable across days.
        running_top = 0.0
        bar_total_h = (day_io / max_tokens) * chart_h
        ranked = [m.model for m in usage.by_model if m.model in day.model_io]
        ranked += [m for m in day.model_io if m not in ranked]
        for model in ranked:
            m_in, m_out = day.model_io[model]
            seg_val = m_in + m_out
            if seg_val <= 0:
                continue
            seg_h = (seg_val / day_io) * bar_total_h
            color = _color_for_model(model, model_index.get(model))
            y = chart_h - bar_total_h + running_top + 8
            bars.append(
                f"<rect x='{x}' y='{y}' width='{max(1, bar_w - 1)}' height='{seg_h:.2f}' "
                f"fill='{color}' opacity='0.9'>"
                f"<title>{_e(day.day.isoformat())} · {_e(model)} · "
                f"{compact_number(seg_val)} tok "
                f"(in {compact_number(m_in)} · out {compact_number(m_out)})</title>"
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
        share = round(m.token_share * 100)
        items.append(
            f"<span class='legend-item'><span class='legend-swatch' "
            f"style='background:{color}'></span>{_e(m.model)} "
            f"<small>in {_e(compact_number(m.input_tokens))} · "
            f"out {_e(compact_number(m.output_tokens))} · {share}%</small></span>"
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
        _stbl("usage-models", "t,n,n,n,n", "usage-models-rows")
        + "<thead><tr><th>Model</th><th class='num'>Sessions</th>"
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
    summary = leverage.summarize(sessions, now)
    total = summary.total
    if total == 0:
        return (
            "<div class='leverage-empty'>"
            "<p class='mini-empty'>No sessions in the last 30 days.</p>"
            "</div>"
        )

    merged = summary.merged
    open_ = summary.open_
    closed = summary.closed
    no_pr = summary.none
    unsynced = summary.unsynced

    leverage_pct = summary.pct
    fill_class = (
        "leverage-high"
        if leverage_pct >= 50
        else ("leverage-mid" if leverage_pct >= 20 else "leverage-low")
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

    # v3.1: one-line review-friction summary, only when data exists
    # (R6 — absent friction must render exactly as v3.0, no empty slot).
    friction = ""
    parts = []
    if summary.median_time_to_merge_s is not None:
        parts.append(
            f"median time-to-merge {leverage.humanize_seconds(summary.median_time_to_merge_s)}"
        )
    if summary.median_review_comments is not None:
        parts.append(f"median {summary.median_review_comments} review comments")
    if parts:
        friction = f"<p class='leverage-friction'>{_e(' · '.join(parts))}</p>"

    # v3.2: one-line struggle summary, only when tool-call data exists.
    # Rejections rendered via the shared R3 phrase — never a bare 0.
    struggle_html = ""
    st = leverage.summarize_struggle(sessions, now)
    if st.tool_error_total is not None:
        seg = f"{st.tool_error_total} tool errors"
        if st.tool_error_rate is not None:
            seg += f" ({st.tool_error_rate:.0%})"
        seg += " · " + leverage.render_rejection_phrase(st)
        struggle_html = f"<p class='leverage-struggle'>{_e(seg)}</p>"

    # v3.4: MCP capability line, only when ≥1 session has usage data.
    mcp_html = ""
    mcp = leverage.summarize_mcp(sessions, now)
    if mcp is not None:
        mcp_html = f"<p class='leverage-mcp'>{_e(leverage.render_mcp_phrase(mcp))}</p>"

    return (
        "<div class='leverage-grid'>"
        f"<div class='leverage-headline'>"
        f"<div class='leverage-pct {fill_class}'>{leverage_pct}%</div>"
        f"<div class='leverage-caption'>"
        f"<strong>{merged}</strong> of <strong>{total}</strong> sessions landed in merged PRs"
        "</div>"
        f"{friction}"
        f"{struggle_html}"
        f"{mcp_html}"
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

    msg_detail = (
        f"{summary.message_data_missing_sessions} missing"
        if summary.message_data_missing_sessions
        else "user + assistant"
    )
    stats = [
        ("Sessions", f"{summary.sessions:,}", "captured"),
        ("Messages", compact_number(summary.total_messages), msg_detail),
        ("Tokens", compact_number(summary.total_tokens), "in + out + cache"),
        ("Active days", f"{summary.active_days}", "in range"),
        ("Current streak", f"{summary.current_streak_days}d", "consecutive"),
        ("Longest streak", f"{summary.longest_streak_days}d", "in range"),
        ("Peak hour", peak, "session starts"),
        ("Favorite model", favorite, "by token volume"),
        ("Cost", f"${summary.total_cost_usd:.2f}", "captured · moat"),
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
        f"{_usage_flavour_line(usage)}"
        "</div>"
    )


def _usage_flavour_line(usage: UsageAnalytics) -> str:
    """A single, deliberately non-authoritative fun comparison.

    Dashboard-only (this function is never called from report/invoice
    renderers — those are the trust-bearing surfaces). Clearly labelled
    so it can never be mistaken for a billable figure.
    """
    total = usage.summary.total_tokens
    if total <= 0:
        return ""
    # ~750 words/page, ~1.3 tokens/word ≈ 1,000 tokens/page; a novel ≈ 100k tokens.
    novels = total / 100_000
    if novels >= 0.1:
        approx = f"≈ {novels:.1f} novels' worth of text"
    else:
        approx = f"≈ {int(total / 1000):,} pages' worth of text"
    return (
        "<p class='usage-flavour'><small>"
        f"for fun · not billable — {_e(approx)} flowed through your tools"
        "</small></p>"
    )


def _activity_heatmap(usage: UsageAnalytics) -> str:
    # Range-aware: usage.daily is already bounded to the selected
    # 7d/30d/all window by build_usage_analytics — render all of it
    # (contribution-graph style) rather than a hardcoded 30.
    days = usage.daily
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
    legend = (
        "<div class='usage-heatmap-legend'><small>less</small>"
        + "".join(f"<span class='usage-cell usage-l{lvl}'></span>" for lvl in range(5))
        + "<small>more</small></div>"
    )
    return "<div class='usage-heatmap'>" + "".join(cells) + "</div>" + legend


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


def _bar_cell(pct: int, label: str) -> str:
    """Pre-rendered share-bar cell body shared by the model/tool tables."""
    return (
        "<div class='bar-cell'>"
        f"<div class='bar-wrap'><div class='bar' style='width:{pct}%'></div></div>"
        f"<span>{_e(label)}</span></div>"
    )


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
            [
                {"html": _e(bucket.label)},
                {"cls": "num", "html": str(bucket.sessions)},
                {"cls": "num", "html": f"${bucket.cost_usd:.2f}"},
                {"html": _bar_cell(pct, pct_label)},
            ]
        )
    return str(
        _panel_macros().data_table(
            "models", "t,n,n,n", ["Model", "Sessions", "Cost", "Share"], rows
        )
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
        # A "$0.00" cell reads as free work. Tools that report no spend at
        # all get an explicit n/a instead (see ToolUsageBucket.spend_tracked).
        cost_html = (
            f"${bucket.cost_usd:.2f}"
            if bucket.spend_tracked
            else '<span class="muted" title="Tool reports no tokens or cost; '
            'time is captured, spend is not tracked.">n/a</span>'
        )
        rows.append(
            [
                {"html": _e(bucket.tool)},
                {"cls": "num", "html": str(bucket.sessions)},
                {"cls": "num", "html": _e(tok_label)},
                {"cls": "num", "html": cost_html},
                {"html": _bar_cell(pct, pct_label)},
            ]
        )
    return str(
        _panel_macros().data_table(
            "tools",
            "t,n,n,n,n",
            ["Tool", "Sessions", "Tokens", "Cost", "Share"],
            rows,
        )
    )


def _surface_panel(buckets: Iterable[ToolUsageBucket]) -> str:
    return (
        '<article class="panel span-4" data-panel="surface">'
        '<div class="panel-head">'
        "<div>"
        '<p class="eyebrow">Capture</p>'
        "<h2>Surfaces</h2>"
        "</div>"
        "</div>"
        f"{_tool_table(buckets)}"
        "</article>"
    )


def _collisions_panel(collisions: Iterable[object]) -> str:
    """v5.0: per-branch duplicate-effort overlaps with a magnitude bar."""
    from halyard.reports import BranchCollision

    items = [c for c in collisions if isinstance(c, BranchCollision)]
    if not items:
        return '<p class="empty">No overlapping AI effort detected.</p>'

    now = datetime.now()
    max_count = max(c.count for c in items)
    rows = []
    for c in items:
        pct = round(100 * c.count / max_count) if max_count else 0
        mins = int((now - c.latest_end).total_seconds() // 60)
        when = f"{mins}m ago" if mins > 0 else "just now"
        proj = f"{_e(c.project)} · " if c.project else ""
        branch_cell = (
            f"{proj}<strong>{_e(c.branch)}</strong>"
            f"<div class='bar-wrap'><div class='bar bar-collision' "
            f"style='width:{pct}%'></div></div>"
        )
        rows.append(
            [
                {"html": branch_cell},
                {"cls": "num", "html": str(c.count)},
                {"html": _e(", ".join(c.tools))},
                {"cls": "num", "html": _e(when)},
            ]
        )
    return str(
        _panel_macros().data_table(
            "collisions", "t,n,t,n", ["Branch", "Overlaps", "Tools", "Last"], rows
        )
    )


def _bucket_table(buckets: Iterable[CostBucket], label: str) -> str:
    rows = []
    for bucket in buckets:
        rows.append(
            [
                {"html": _e(bucket.label)},
                {"cls": "num", "html": str(bucket.sessions)},
                {"cls": "num", "html": f"${bucket.cost_usd:.2f}"},
            ]
        )
    if not rows:
        return f'<p class="empty">No {label.lower()} data yet.</p>'
    return str(
        _panel_macros().data_table(f"bucket-{label}", "t,n,n", [label, "Sessions", "Cost"], rows)
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
                _stbl("ledger", "t,n,n,n,n,t")
                + "<thead><tr><th>Project</th><th>Sessions</th><th>Direct API</th>"
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
        _stbl("ledger-full", "t,n,n,n,n,t")
        + "<thead><tr><th>Project</th><th>Sessions</th><th>Direct API</th>"
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
            [
                {
                    "sortval": int(session.end.timestamp()),
                    "html": _e(session.end.strftime("%Y-%m-%d %H:%M")),
                },
                {"html": _e(session.tool)},
                {"html": _e(session.model)},
                {"cls": "num", "html": f"{session.input_tokens:,} / {session.output_tokens:,}"},
                {"cls": "num", "html": f"${session.cost_usd:.4f}"},
            ]
        )
    if not rows:
        return '<p class="empty">All hands accounted for. Manifest clean.</p>'
    return str(
        _panel_macros().data_table(
            "sessions-adrift",
            "n,t,x,x,n",
            ["Time", "Tool", "Model", "In / Out", "Cost"],
            rows,
        )
    )


def _time_table(buckets: Iterable[TimeBucket]) -> str:
    rows = []
    for bucket in buckets:
        rows.append(
            [
                {"html": _e(bucket.label)},
                {
                    "cls": "num",
                    "sortval": bucket.minutes,
                    "html": _e(format_minutes(bucket.minutes)),
                },
            ]
        )
    if not rows:
        return '<p class="empty">No human time recorded this month.<br>Run <code>halyard start &lt;project&gt;</code> to begin tracking.</p>'
    return str(_panel_macros().data_table("timeclock", "t,n", ["Project", "Time"], rows))


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


# --------------------------------------------------------------------------- #
# v5.7: inline-SVG chart helpers (offline-first; no JS charting dependency)
# --------------------------------------------------------------------------- #
_CHART_PALETTE = (
    "#4fd1c5",
    "#63b3ed",
    "#b794f4",
    "#f6ad55",
    "#fc8181",
    "#68d391",
    "#76e4f7",
    "#f687b3",
    "#a0aec0",
)


def _svg_donut(
    segments: list[tuple[str, float, str]],
    *,
    size: int = 180,
    thick: int = 30,
    center_top: str = "",
    center_sub: str = "",
) -> str:
    """A donut chart as inline SVG. ``segments`` = (label, value, color)."""
    r = (size - thick) / 2
    cx = cy = size / 2
    circ = 2 * math.pi * r
    total = sum(v for _, v, _ in segments) or 1.0
    arcs = []
    offset = 0.0
    for _label, value, color in segments:
        dash = (value / total) * circ
        arcs.append(
            f"<circle cx='{cx}' cy='{cy}' r='{r:.1f}' fill='none' "
            f"stroke='{_e(color)}' stroke-width='{thick}' "
            f"stroke-dasharray='{dash:.2f} {circ - dash:.2f}' "
            f"stroke-dashoffset='{-offset:.2f}' transform='rotate(-90 {cx} {cy})' />"
        )
        offset += dash
    return (
        f"<svg viewBox='0 0 {size} {size}' width='{size}' height='{size}' "
        f"class='svg-donut' role='img'>{''.join(arcs)}"
        f"<text x='{cx}' y='{cy - 2}' text-anchor='middle' class='donut-top'>{_e(center_top)}</text>"
        f"<text x='{cx}' y='{cy + 16}' text-anchor='middle' class='donut-sub'>{_e(center_sub)}</text>"
        "</svg>"
    )


def _svg_area(
    values: list[float],
    *,
    w: int = 600,
    h: int = 160,
    color: str = "#4fd1c5",
    fill: str = "rgba(79,209,197,.16)",
) -> str:
    """An area+line trend chart as inline SVG."""
    if not values:
        return "<p class='empty'>no data</p>"
    n = len(values)
    mx = max(values) or 1.0
    pad = 6
    iw, ih = w - pad * 2, h - pad * 2
    pts: list[tuple[float, float]] = []
    for i, v in enumerate(values):
        x = pad + (iw * (i / (n - 1)) if n > 1 else iw / 2)
        y = pad + ih - (v / mx) * ih
        pts.append((x, y))
    line = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    area = (
        f"M{pts[0][0]:.1f} {h - pad:.1f} L"
        + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        + f" L{pts[-1][0]:.1f} {h - pad:.1f} Z"
    )
    return (
        f"<svg viewBox='0 0 {w} {h}' width='100%' height='{h}' "
        f"preserveAspectRatio='none' class='svg-area'>"
        f"<path d='{area}' fill='{fill}'/>"
        f"<path d='{line}' fill='none' stroke='{_e(color)}' stroke-width='2'/></svg>"
    )


def _svg_stacked_bar(parts: list[tuple[str, int, str]]) -> str:
    """A single part-to-whole horizontal bar + legend as inline SVG/HTML."""
    total = sum(v for _, v, _ in parts) or 1
    segs = "".join(
        f"<span class='sb-seg' title='{_e(lbl)}: {v}' "
        f"style='width:{100 * v / total:.1f}%;background:{_e(c)}'></span>"
        for lbl, v, c in parts
        if v
    )
    keys = "".join(
        f"<span class='sb-key'><span class='dot' style='background:{_e(c)}'></span>"
        f"{_e(lbl)} {v}</span>"
        for lbl, v, c in parts
    )
    return f"<div class='sbar'>{segs}</div><div class='sb-legend'>{keys}</div>"


def _chart_legend(segments: list[tuple[str, float, str]], fmt: object) -> str:
    rows = "".join(
        f"<li><span class='dot' style='background:{_e(c)}'></span>"
        f"<span class='lg-label'>{_e(lbl)}</span>"
        f"<span class='lg-val'>{_e(fmt(v))}</span></li>"  # type: ignore[operator]
        for lbl, v, c in segments
    )
    return f"<ul class='chart-legend'>{rows}</ul>"


def _chart_hbars(rows: list[tuple[str, float]], fmt: object, color: str = "#b794f4") -> str:
    mx = max((v for _, v in rows), default=0.0) or 1.0
    out = "".join(
        f"<div class='cbar'><span class='cb-label'>{_e(label)}</span>"
        f"<span class='cb-track'><span class='cb-fill' "
        f"style='width:{int(100 * value / mx)}%;background:{_e(color)}'></span></span>"
        f"<span class='cb-val'>{_e(fmt(value))}</span></div>"  # type: ignore[operator]
        for label, value in rows
    )
    return out or "<p class='empty'>no data</p>"


def _ov_usd(v: float) -> str:
    return f"${v:,.0f}" if v >= 100 else f"${v:.2f}"


def _overview_panels(state: DashboardState, usage: UsageAnalytics) -> str:
    """v5.7: the Overview tab — hero charts built from existing data."""
    s = usage.summary
    pal = _CHART_PALETTE

    cost_segs = [
        (b.model, b.cost_usd, pal[i % len(pal)])
        for i, b in enumerate(sorted(usage.by_model, key=lambda b: -b.cost_usd)[:6])
    ]
    tok_segs = [
        (b.model, float(b.tokens), pal[i % len(pal)])
        for i, b in enumerate(sorted(usage.by_model, key=lambda b: -b.tokens)[:6])
    ]

    by_proj: dict[str, float] = {}
    # v5.9: count outcomes per unique PR (not per session) so one merged PR with
    # many sessions counts once; sessions with no PR are counted individually.
    pr_state_by_ref: dict[str, str] = {}
    sessions_without_pr = 0
    for sess in state.all_sessions:
        if sess.project:
            # slugs are already canonical (parse_sessions applies the v5.8 alias map)
            by_proj[sess.project] = by_proj.get(sess.project, 0.0) + sess.cost_usd
        if sess.pr_ref:
            pr_state_by_ref[sess.pr_ref] = (sess.pr_state or "").lower()
        else:
            sessions_without_pr += 1
    outcomes = {"shipped": 0, "open": 0, "closed": 0, "none": sessions_without_pr}
    for st in pr_state_by_ref.values():
        if st == "merged":
            outcomes["shipped"] += 1
        elif st == "open":
            outcomes["open"] += 1
        elif st == "closed":
            outcomes["closed"] += 1
    top_projects = sorted(by_proj.items(), key=lambda kv: -kv[1])[:6]
    daily_tokens = [float(d.tokens) for d in usage.daily[-30:]]

    peak = "—" if s.peak_hour is None else _hour_label(s.peak_hour)
    kpi_body = (
        "<div class='kpi-strip'>"
        f"<span><b>{_ov_usd(s.total_cost_usd)}</b> cost</span>"
        f"<span><b>{s.sessions:,}</b> sessions</span>"
        f"<span><b>{_e(compact_number(s.total_tokens))}</b> tokens</span>"
        f"<span><b>{s.active_days}</b> active days</span>"
        f"<span><b>{_e(peak)}</b> peak hr</span>"
        "</div>"
    )
    cost_body = (
        "<div class='donut-wrap'>"
        + _svg_donut(cost_segs, center_top=_ov_usd(s.total_cost_usd), center_sub="total")
        + _chart_legend(cost_segs, _ov_usd)
        + "</div>"
    )
    mix_body = (
        "<div class='donut-wrap'>"
        + _svg_donut(tok_segs, size=150, thick=24)
        + _chart_legend(tok_segs, compact_number)
        + "</div>"
    )
    outcome_parts = [
        ("shipped", outcomes["shipped"], "#68d391"),
        ("open", outcomes["open"], "#63b3ed"),
        ("closed", outcomes["closed"], "#fc8181"),
        ("no PR", outcomes["none"], "#4a5568"),
    ]

    return (
        _panel_article(
            "ov-kpis", "Overview", "At a glance", kpi_body, span="span-12", cls="panel-compact"
        )
        + _panel_article("ov-cost", "Overview", "Where the money went", cost_body, span="span-6")
        + _panel_article("ov-models", "Overview", "Model mix · tokens", mix_body, span="span-6")
        + _panel_article(
            "ov-trend",
            "Overview",
            f"Tokens over time · {len(daily_tokens)}d",
            _svg_area(daily_tokens, h=170),
            span="span-12",
        )
        + _panel_article("ov-activity", "Overview", "Activity", _activity_heatmap(usage))
        + _panel_article(
            "ov-projects",
            "Overview",
            "Top projects by cost",
            _chart_hbars(top_projects, _ov_usd),
        )
        + _panel_article("ov-outcomes", "Overview", "Outcomes", _svg_stacked_bar(outcome_parts))
    )


def _panel_article(
    panel_id: str,
    eyebrow: str,
    title: str,
    body: str,
    *,
    span: str = "span-4",
    tab: str = "overview",
    cls: str = "",
) -> str:
    classes = f"panel {span}{(' ' + cls) if cls else ''}"
    return (
        f'<article class="{classes}" data-panel="{_e(panel_id)}" data-tab="{_e(tab)}">'
        '<div class="panel-head"><div>'
        f'<p class="eyebrow">{_e(eyebrow)}</p><h2>{_e(title)}</h2></div></div>'
        f"{body}</article>"
    )


def _stbl(key: str, cols: str, cls: str = "") -> str:
    """Open tag for a client-sortable table (v2.73).

    ``cols`` is one code per column, in order:
    ``t`` text · ``n`` numeric · ``m`` time(HH:MM) · ``s`` severity
    (cell carries ``data-sev``) · ``x`` not sortable. The sorter reads
    these; the no-JS render is unchanged (additive attributes only).
    ``key`` is a stable slug so saved sort survives layout changes.
    """
    cls_attr = f" class='{_e(cls)}'" if cls else ""
    return f"<table{cls_attr} data-sortable data-sort-key='{_e(key)}' data-cols='{_e(cols)}'>"


def _table_sort_script() -> str:
    """Client-side column sort for ``table[data-sortable]`` (v2.73).

    Progressive enhancement: the server already emits correctly
    fixed-sorted rows; this only reorders an already-correct table and
    persists the choice in sessionStorage so it survives the 10s
    ``<meta refresh>`` (a naive sort would reset every 10s — that
    persistence is the load-bearing requirement, not the click).
    asc → desc → clear(restore server order). Numeric parsing handles
    ``$ , % k M`` and ``HH:MM``; blanks always sort last; severity uses
    each cell's ``data-sev``; any cell may override its sort key with
    ``data-sort-val``. Stable. Wrapped so any failure leaves the
    native (server-sorted) table intact.
    """
    return """<script>
(function(){
  try {
    var num = function(s){
      if(s==null) return NaN;
      s = String(s).trim();
      if(s===''||s==='—'||s==='-'||s==='n/a') return NaN;
      var m = s.replace(/[$,%\\s]/g,'');
      var mult = 1;
      if(/[kK]$/.test(m)){ mult=1e3; m=m.slice(0,-1); }
      else if(/[mM]$/.test(m)){ mult=1e6; m=m.slice(0,-1); }
      else if(/[bB]$/.test(m)){ mult=1e9; m=m.slice(0,-1); }
      var v = parseFloat(m);
      return isNaN(v) ? NaN : v*mult;
    };
    var timeval = function(s){
      s = String(s||'').trim();
      var m = s.match(/(\\d{1,2}):(\\d{2})/);
      return m ? (parseInt(m[1],10)*60+parseInt(m[2],10)) : NaN;
    };
    var keyOf = function(td, kind){
      if(td && td.dataset && td.dataset.sortVal!=null && td.dataset.sortVal!=='')
        return parseFloat(td.dataset.sortVal);
      if(kind==='s') return td ? parseFloat(td.dataset.sev||'99') : 99;
      var txt = td ? td.textContent : '';
      if(kind==='n') return num(txt);
      if(kind==='m') return timeval(txt);
      return String(txt||'').trim().toLowerCase();
    };
    var cmp = function(a,b,kind){
      if(kind==='t'){
        if(a<b) return -1; if(a>b) return 1; return 0;
      }
      var an=(typeof a==='number'&&isNaN(a)), bn=(typeof b==='number'&&isNaN(b));
      if(an&&bn) return 0; if(an) return 1; if(bn) return -1;  // blanks last
      return a<b?-1:(a>b?1:0);
    };
    var apply = function(tbl, col, dir){
      var cols=(tbl.getAttribute('data-cols')||'').split(',');
      var kind=cols[col]; if(!kind||kind==='x') return;
      var tb=tbl.tBodies[0]; if(!tb) return;
      var rows=[].slice.call(tb.rows);
      var dec=rows.map(function(r,i){
        return {r:r,i:i,k:keyOf(r.cells[col],kind)};
      });
      dec.sort(function(x,y){
        var c=cmp(x.k,y.k,kind); return (c!==0?(dir<0?-c:c):x.i-y.i);
      });
      dec.forEach(function(d){ tb.appendChild(d.r); });
      marks(tbl,col,dir);
    };
    var marks=function(tbl,col,dir){
      var ths=tbl.tHead?tbl.tHead.rows[0].cells:[];
      for(var j=0;j<ths.length;j++){
        var th=ths[j], ind=th.querySelector('.sort-ind');
        if(!ind) continue;  // not a sortable header
        if(j===col){
          th.setAttribute('aria-sort', dir<0?'descending':'ascending');
          ind.textContent = dir<0?'▼':'▲';
        } else {
          th.setAttribute('aria-sort','none');
          ind.textContent = '⇅';
        }
      }
    };
    var origOrder = function(tbl){
      var tb=tbl.tBodies[0]; if(!tb||tbl._orig) return;
      tbl._orig=[].slice.call(tb.rows);
    };
    var restore = function(tbl){
      var tb=tbl.tBodies[0]; if(!tb||!tbl._orig) return;
      tbl._orig.forEach(function(r){ tb.appendChild(r); });
      marks(tbl,-1,1);  // clear: all headers back to neutral
    };
    var save=function(k,st){ try{ sessionStorage.setItem('halyard.sort.'+k,st);}catch(e){} };
    var load=function(k){ try{ return sessionStorage.getItem('halyard.sort.'+k);}catch(e){ return null; } };
    var init=function(tbl){
      var key=tbl.getAttribute('data-sort-key'); if(!key) return;
      var cols=(tbl.getAttribute('data-cols')||'').split(',');
      origOrder(tbl);
      var ths=tbl.tHead?tbl.tHead.rows[0].cells:[];
      for(var j=0;j<ths.length;j++){
        (function(c){
          if(!cols[c]||cols[c]==='x') return;
          var th=ths[c];
          th.setAttribute('aria-sort','none');
          th.classList.add('h-sortable');
          th.setAttribute('role','button');
          th.setAttribute('tabindex','0');
          if(!th.querySelector('.sort-ind')){
            var sp=document.createElement('span');
            sp.className='sort-ind';
            sp.setAttribute('aria-hidden','true');
            sp.textContent='⇅';
            th.appendChild(sp);
          }
          var go=function(){
            var cur=load(key)||'';
            var p=cur.split(':'), pc=parseInt(p[0],10), pd=parseInt(p[1],10);
            var dir;
            if(pc===c){ dir = pd>0 ? -1 : (pd<0 ? 0 : 1); }
            else { dir=1; }
            if(dir===0){ restore(tbl); save(key,''); }
            else { apply(tbl,c,dir); save(key, c+':'+dir); }
          };
          th.addEventListener('click',go);
          th.addEventListener('keydown',function(e){
            if(e.key==='Enter'||e.key===' '){ e.preventDefault(); go(); }
          });
        })(j);
      }
      var st=load(key);
      if(st){
        var p=st.split(':'), pc=parseInt(p[0],10), pd=parseInt(p[1],10);
        if(!isNaN(pc)&&!isNaN(pd)&&pd!==0) apply(tbl,pc,pd);
      }
    };
    var boot=function(){
      var tbls=document.querySelectorAll('table[data-sortable]');
      for(var i=0;i<tbls.length;i++) init(tbls[i]);
    };
    window.HalyardBootTables = boot;
    if(document.readyState!=='loading') boot();
    else document.addEventListener('DOMContentLoaded', boot);
  } catch(e){}
})();
</script>"""


def _panel_status_pill(text: str, state: str) -> str:
    return f"<span class='pill pill-{_e(state)}'>{_e(text)}</span>"


def _scroll_preserve_script() -> str:
    """Keep the scroll position across reloads.

    The dashboard is server-rendered: the 7d/30d/All and Overview/Models
    controls are plain links, and a `<meta http-equiv="refresh">` hard-
    reloads every 10s. Both reset scroll to the top, which feels broken
    when you're reading a panel mid-page. Persist scrollY to
    sessionStorage and restore it on load (manual restoration so the
    browser's own guess doesn't fight it). Wrapped so any failure just
    leaves native behaviour intact.
    """
    return """<script>
(function(){
  try {
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
    var KEY = 'halyard-scroll-v1';
    var restore = function(){
      var y = parseInt(sessionStorage.getItem(KEY) || '', 10);
      if (!isNaN(y)) window.scrollTo(0, y);
    };
    if (document.readyState !== 'loading') restore();
    else document.addEventListener('DOMContentLoaded', restore);
    window.addEventListener('load', restore);
    var save = function(){
      try { sessionStorage.setItem(KEY, String(window.scrollY)); } catch(e){}
    };
    window.addEventListener('scroll', save, { passive: true });
    window.addEventListener('beforeunload', save);
    document.addEventListener('visibilitychange', function(){
      if (document.visibilityState === 'hidden') save();
    });
  } catch(e){}
})();
</script>"""


def _layout_script() -> str:
    """Client-side panel reorder/collapse, persisted in localStorage.

    Server always emits the default order; this restores the user's saved
    layout on every load (including the 10s auto-refresh). Wrapped so any
    failure leaves the already-rendered dashboard fully visible.
    """
    return """<script>
(function(){
  try {
    var ORDER_KEY = 'halyard-layout-order-v1';
    var COLL_KEY  = 'halyard-layout-collapsed-v1';

    function readJSON(k, fallback){
      try { var v = JSON.parse(localStorage.getItem(k)); return v || fallback; }
      catch(e){ return fallback; }
    }
    function containerKey(parent){
      if (!parent) return null;
      if (parent.classList.contains('grid')) return 'grid';
      if (parent.classList.contains('metrics')) return 'metrics';
      return null;
    }

    var collapsed = readJSON(COLL_KEY, []);
    var collapsedSet = {};
    collapsed.forEach(function(id){ collapsedSet[id] = true; });

    var REM_KEY = 'halyard-removed-v1';
    var removedSet = {};
    readJSON(REM_KEY, []).forEach(function(id){ removedSet[id] = true; });
    function persistRemoved(){ localStorage.setItem(REM_KEY, JSON.stringify(Object.keys(removedSet))); }

    function persistOrder(){
      var out = {};
      ['grid','metrics'].forEach(function(ck){
        var parent = document.querySelector('.' + ck);
        if (!parent) return;
        out[ck] = Array.prototype.slice
          .call(parent.querySelectorAll(':scope > [data-panel]'))
          .map(function(el){ return el.getAttribute('data-panel'); });
      });
      localStorage.setItem(ORDER_KEY, JSON.stringify(out));
    }
    function persistCollapsed(){
      localStorage.setItem(COLL_KEY, JSON.stringify(Object.keys(collapsedSet)));
    }

    function restoreOrder(){
      var saved = readJSON(ORDER_KEY, {});
      ['grid','metrics'].forEach(function(ck){
        var parent = document.querySelector('.' + ck);
        if (!parent || !saved[ck]) return;
        var byId = {};
        Array.prototype.slice
          .call(parent.querySelectorAll(':scope > [data-panel]'))
          .forEach(function(el){ byId[el.getAttribute('data-panel')] = el; });
        // Saved ids first (in saved order), then any new/unknown panels
        // keep their default relative position.
        saved[ck].forEach(function(id){
          if (byId[id]) { parent.appendChild(byId[id]); delete byId[id]; }
        });
        Object.keys(byId).forEach(function(id){ parent.appendChild(byId[id]); });
      });
    }

    function setCollapsed(el, on){
      el.classList.toggle('is-collapsed', on);
      var t = el.querySelector(':scope > .panel-head .lay-toggle')
           || el.querySelector(':scope > .lay-controls .lay-toggle');
      if (t) { t.textContent = on ? '▸' : '▾'; t.title = on ? 'Expand' : 'Collapse'; }
    }

    var dragId = null;
    function addControls(el){
      // Idempotent: a panel re-inserted by a partial refresh already has its
      // controls + listeners, so don't double-wire it.
      if (el.querySelector(':scope > .panel-head .lay-controls')
       || el.querySelector(':scope > .lay-controls')) return;
      var id = el.getAttribute('data-panel');
      var host = el.querySelector(':scope > .panel-head');
      var controls = document.createElement('div');
      controls.className = 'lay-controls';
      var handle = document.createElement('button');
      handle.className = 'lay-handle'; handle.type = 'button';
      handle.textContent = '⠿'; handle.title = 'Drag to reorder';
      handle.setAttribute('aria-label', 'Drag to reorder panel');
      var toggle = document.createElement('button');
      toggle.className = 'lay-toggle'; toggle.type = 'button';
      toggle.textContent = '▾'; toggle.title = 'Collapse';
      toggle.setAttribute('aria-label', 'Collapse or expand panel');
      var remove = document.createElement('button');
      remove.className = 'lay-remove'; remove.type = 'button';
      remove.textContent = '✕'; remove.title = 'Hide panel';
      remove.setAttribute('aria-label', 'Hide panel');
      controls.appendChild(handle); controls.appendChild(toggle); controls.appendChild(remove);
      if (host) { host.appendChild(controls); } else { el.appendChild(controls); }

      remove.addEventListener('click', function(ev){
        ev.stopPropagation();
        removedSet[id] = true; el.classList.add('is-removed');
        persistRemoved(); renderPanelsMenu();
      });

      toggle.addEventListener('click', function(ev){
        ev.stopPropagation();
        var on = !el.classList.contains('is-collapsed');
        if (on) { collapsedSet[id] = true; } else { delete collapsedSet[id]; }
        setCollapsed(el, on);
        persistCollapsed();
        if (typeof refreshAllBtn === 'function') refreshAllBtn();
      });

      handle.addEventListener('mousedown', function(){ el.setAttribute('draggable','true'); });
      handle.addEventListener('mouseup', function(){ el.removeAttribute('draggable'); });
      el.addEventListener('dragstart', function(ev){
        dragId = id; el.classList.add('lay-dragging');
        try { ev.dataTransfer.effectAllowed = 'move'; ev.dataTransfer.setData('text/plain', id); }
        catch(e){}
      });
      el.addEventListener('dragend', function(){
        dragId = null; el.removeAttribute('draggable');
        el.classList.remove('lay-dragging');
        document.querySelectorAll('.lay-over').forEach(function(n){
          n.classList.remove('lay-over');
        });
      });
      el.addEventListener('dragover', function(ev){
        if (dragId === null || dragId === id) return;
        var src = document.querySelector('[data-panel="' + dragId + '"]');
        if (!src || src.parentElement !== el.parentElement) return;  // same container only
        ev.preventDefault();
        el.classList.add('lay-over');
      });
      el.addEventListener('dragleave', function(){ el.classList.remove('lay-over'); });
      el.addEventListener('drop', function(ev){
        el.classList.remove('lay-over');
        if (dragId === null || dragId === id) return;
        var src = document.querySelector('[data-panel="' + dragId + '"]');
        if (!src || src.parentElement !== el.parentElement) return;
        ev.preventDefault();
        var parent = el.parentElement;
        var rect = el.getBoundingClientRect();
        var after = (ev.clientY - rect.top) > rect.height / 2;
        parent.insertBefore(src, after ? el.nextSibling : el);
        persistOrder();
      });
    }

    function applyLayout(){
      restoreOrder();
      Array.prototype.slice.call(document.querySelectorAll('[data-panel]'))
        .forEach(function(el){
          if (!containerKey(el.parentElement)) return;
          addControls(el);
          if (collapsedSet[el.getAttribute('data-panel')]) setCollapsed(el, true);
          if (removedSet[el.getAttribute('data-panel')]) el.classList.add('is-removed');
        });
    }
    // Exposed so a partial refresh can re-apply order + collapse + hidden to swapped panels.
    window.HalyardApplyLayout = applyLayout;
    applyLayout();

    // "panels" menu — switch hidden panels back on.
    var panelsBtn = document.getElementById('panels-btn');
    var panelsMenu = document.getElementById('panels-menu');
    function renderPanelsMenu(){
      if (!panelsMenu) return;
      var items = '';
      Array.prototype.slice.call(document.querySelectorAll('[data-panel]'))
        .filter(function(el){ return containerKey(el.parentElement); })
        .forEach(function(el){
          var id = el.getAttribute('data-panel');
          var h = el.querySelector(':scope > .panel-head h2') || el.querySelector('h2');
          var label = h ? h.textContent : id;
          items += '<label><input type="checkbox" data-pid="' + id + '" ' +
                   (removedSet[id] ? '' : 'checked') + '> ' + label + '</label>';
        });
      panelsMenu.innerHTML = items;
    }
    if (panelsBtn && panelsMenu) {
      panelsBtn.addEventListener('click', function(){
        panelsMenu.classList.toggle('open'); renderPanelsMenu();
      });
      panelsMenu.addEventListener('change', function(ev){
        var cb = ev.target; if (!cb.getAttribute('data-pid')) return;
        var id = cb.getAttribute('data-pid');
        var el = document.querySelector('[data-panel="' + id + '"]');
        if (cb.checked) { delete removedSet[id]; if (el) el.classList.remove('is-removed'); }
        else { removedSet[id] = true; if (el) el.classList.add('is-removed'); }
        persistRemoved();
      });
    }

    function layoutBoxes(){
      return Array.prototype.slice.call(document.querySelectorAll('[data-panel]'))
        .filter(function(el){ return containerKey(el.parentElement); });
    }
    var allBtn = document.getElementById('layout-toggle-all');
    function refreshAllBtn(){
      if (!allBtn) return;
      var boxes = layoutBoxes();
      var anyOpen = boxes.some(function(el){ return !el.classList.contains('is-collapsed'); });
      // If anything is open the button collapses everything; else it expands.
      allBtn.textContent = anyOpen ? '▾ collapse all' : '▸ expand all';
    }
    if (allBtn) {
      allBtn.addEventListener('click', function(){
        var boxes = layoutBoxes();
        var on = boxes.some(function(el){ return !el.classList.contains('is-collapsed'); });
        boxes.forEach(function(el){
          var id = el.getAttribute('data-panel');
          if (on) { collapsedSet[id] = true; } else { delete collapsedSet[id]; }
          setCollapsed(el, on);
        });
        persistCollapsed();
        refreshAllBtn();
      });
      refreshAllBtn();
    }

    var resetBtn = document.getElementById('layout-reset');
    if (resetBtn) {
      resetBtn.addEventListener('click', function(){
        localStorage.removeItem(ORDER_KEY);
        localStorage.removeItem(COLL_KEY);
        localStorage.removeItem(REM_KEY);
        location.reload();
      });
    }
  } catch (e) {
    if (window.console) console.warn('Halyard layout script failed:', e);
  }
})();
</script>"""


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


@lru_cache(maxsize=1)
def _load_css() -> str:
    """Return the dashboard stylesheet, read once from the templates dir."""
    return (_TEMPLATE_DIR / "dashboard.css").read_text(encoding="utf-8")
