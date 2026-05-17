"""Reusable reporting and dashboard view models."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME, AiSession, parse_sessions
from halyard.pricing import pricing_table_age_days
from halyard.usage import ToolUsageBucket

_HALYARD_ACTIVE = Path.home() / ".halyard" / "active"


@dataclass(frozen=True)
class CostBucket:
    label: str
    cost_usd: float
    sessions: int


@dataclass(frozen=True)
class TimeBucket:
    label: str
    minutes: int


@dataclass(frozen=True)
class AiReport:
    sessions: list[AiSession]
    period_label: str
    total_cost: float
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_write_tokens: int
    by_project: list[CostBucket]
    by_model: list[CostBucket]
    by_tool: list[CostBucket]
    by_tool_usage: list[ToolUsageBucket]
    unattributed_count: int
    unattributed_sessions: list[AiSession]
    total_tool_calls: int = 0
    total_tool_errors: int = 0


@dataclass(frozen=True)
class ActiveTimer:
    slug: str
    timeclock: Path | None
    started: str | None
    elapsed_minutes: int = 0

    @property
    def elapsed_label(self) -> str:
        return format_minutes(self.elapsed_minutes)


@dataclass(frozen=True)
class HumanTimeReport:
    today_minutes: int
    month_minutes: int
    by_project: list[TimeBucket]
    presence_minutes: int = 0
    presence_label: str = "manual"


@dataclass(frozen=True)
class HealthCheck:
    label: str
    status: str
    detail: str


@dataclass(frozen=True)
class DashboardState:
    project_dir: Path
    report: AiReport
    human_time: HumanTimeReport
    active_timer: ActiveTimer | None
    health: list[HealthCheck]
    latest_session: AiSession | None
    all_sessions: list[AiSession] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    # >0 when this state aggregates multiple project logs (number of
    # source dirs); 0 for a single-project view.
    aggregate_count: int = 0


def build_ai_report(
    project_dir: Path,
    *,
    all_time: bool = False,
    now: datetime | None = None,
    sessions: list[AiSession] | None = None,
) -> AiReport:
    """Build the AI usage summary shared by CLI and dashboard.

    When *sessions* is given, it is used as-is and the project
    directory is NOT read (enables cross-project aggregation). When
    omitted, behaviour is unchanged: parse ``project_dir``.
    """
    clock = now or datetime.now()
    if sessions is None:
        sessions = parse_sessions(project_dir)
    period_label = "All time"

    if not all_time:
        period_label = clock.strftime("%B %Y")
        sessions = [
            session
            for session in sessions
            if session.start.year == clock.year and session.start.month == clock.month
        ]

    return summarize_ai_sessions(sessions, period_label=period_label)


def check_pricing_staleness() -> tuple[int | None, bool]:
    """Return (age_days, is_stale). Stale means missing or >= 30 days old."""
    age = pricing_table_age_days()
    return age, (age is None or age >= 30)


def build_filtered_ai_report(
    project_dir: Path,
    *,
    project: str | None = None,
    client: str | None = None,
    all_time: bool = False,
    now: datetime | None = None,
) -> AiReport:
    """Build an AI report with optional project or client filters."""
    clock = now or datetime.now()
    report = build_ai_report(project_dir, all_time=all_time, now=clock)

    sessions = filter_ai_sessions(report.sessions, project=project, client=client)
    period_label = "All time" if all_time else clock.strftime("%B %Y")

    return summarize_ai_sessions(sessions, period_label=period_label)


def filter_ai_sessions(
    sessions: list[AiSession],
    *,
    project: str | None = None,
    client: str | None = None,
) -> list[AiSession]:
    """Filter AI sessions by project slug or client slug."""
    if project:
        return [s for s in sessions if s.project == project]
    if client:
        return [s for s in sessions if (s.project or "").startswith(f"{client}:")]
    return sessions


def summarize_ai_sessions(sessions: list[AiSession], *, period_label: str) -> AiReport:
    """Aggregate parsed AI sessions into project/model/tool buckets."""
    total_cost = sum(session.cost_usd for session in sessions)
    total_input = sum(session.input_tokens for session in sessions)
    total_output = sum(session.output_tokens for session in sessions)
    total_cache_read = sum(session.cache_read or 0 for session in sessions)
    total_cache_write = sum(session.cache_write or 0 for session in sessions)
    unattributed = [session for session in sessions if not session.project]
    total_tool_calls = sum(s.tool_calls for s in sessions if s.tool_calls is not None)
    total_tool_errors = sum(s.tool_errors for s in sessions if s.tool_errors is not None)

    return AiReport(
        sessions=sessions,
        period_label=period_label,
        total_cost=total_cost,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cache_read_tokens=total_cache_read,
        total_cache_write_tokens=total_cache_write,
        by_project=_bucket_costs(
            (session.project or "(unattributed)", session.cost_usd) for session in sessions
        ),
        by_model=_bucket_costs((session.model, session.cost_usd) for session in sessions),
        by_tool=_bucket_costs((session.tool, session.cost_usd) for session in sessions),
        by_tool_usage=_tool_buckets_for_report(sessions),
        unattributed_count=len(unattributed),
        unattributed_sessions=unattributed,
        total_tool_calls=total_tool_calls,
        total_tool_errors=total_tool_errors,
    )


def read_active_timer(active_path: Path | None = None) -> ActiveTimer | None:
    """Read the current active timer state, if any."""
    if active_path is None:
        active_path = _HALYARD_ACTIVE
    if not active_path.exists():
        return None

    from halyard.state_integrity import (
        IntegrityError,
        current_mode,
        detect_sidecar_mode,
        read_trusted_state,
    )

    # The active-timer file is global; its governing project (and thus
    # integrity mode) is the project that owns the referenced timeclock.
    # Derive that mode, but never let a (tamperable) in-file path
    # downgrade verification below an existing sidecar — sidecar
    # presence proves integrity was enabled.
    raw_first = active_path.read_text()
    tc = next(
        (ln.split("=", 1)[1] for ln in raw_first.splitlines() if ln.startswith("timeclock=")),
        None,
    )
    project_dir = Path(tc).parent if tc else None
    mode = current_mode(project_dir)
    sidecar_mode = detect_sidecar_mode(active_path)
    if sidecar_mode is not None and mode == "off":
        mode = sidecar_mode

    try:
        verified = read_trusted_state(active_path, mode=mode)
    except IntegrityError:
        # Fail closed: a tampered active-timer file is not trusted.
        return None
    if verified is None:
        return None

    data = dict(line.split("=", 1) for line in verified.splitlines() if "=" in line)
    slug = data.get("slug")
    if not slug:
        return None

    timeclock = Path(data["timeclock"]) if data.get("timeclock") else None
    started = data.get("started")
    elapsed = _elapsed_minutes(started, datetime.now()) if started else 0
    return ActiveTimer(slug=slug, timeclock=timeclock, started=started, elapsed_minutes=elapsed)


def get_active_project(project_dir: Path) -> str | None:
    """Return active project only when the active timer belongs to project_dir."""
    active = read_active_timer()
    if active is None or active.timeclock is None:
        return None
    try:
        active.timeclock.resolve().relative_to(project_dir.resolve())
    except ValueError:
        return None
    return active.slug


def build_human_time_report(project_dir: Path, *, now: datetime | None = None) -> HumanTimeReport:
    """Summarize hledger-compatible timeclock entries."""
    clock = now or datetime.now()
    entries = parse_timeclock(project_dir / "time.timeclock", now=clock)
    today = clock.date()
    month_minutes = 0
    today_minutes = 0
    totals: dict[str, int] = {}

    for start, end, account in entries:
        minutes = max(0, int((end - start).total_seconds() // 60))
        if start.year == clock.year and start.month == clock.month:
            month_minutes += minutes
            totals[account] = totals.get(account, 0) + minutes
        if start.date() == today:
            today_minutes += minutes

    return HumanTimeReport(
        today_minutes=today_minutes,
        month_minutes=month_minutes,
        by_project=[
            TimeBucket(label=label, minutes=minutes)
            for label, minutes in sorted(totals.items(), key=lambda item: -item[1])
        ],
    )


def parse_timeclock(
    path: Path, *, now: datetime | None = None
) -> list[tuple[datetime, datetime, str]]:
    """Parse `i`/`o` timeclock pairs. An open entry is measured through now."""
    if not path.exists():
        return []

    clock = now or datetime.now()
    entries: list[tuple[datetime, datetime, str]] = []
    open_entry: tuple[datetime, str] | None = None

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        marker = parts[0]
        timestamp = _parse_timeclock_timestamp(parts[1], parts[2])
        if timestamp is None:
            continue
        if marker == "i" and len(parts) >= 4:
            open_entry = (timestamp, parts[3])
        elif marker == "o" and open_entry is not None:
            start, account = open_entry
            entries.append((start, timestamp, account))
            open_entry = None

    if open_entry is not None:
        start, account = open_entry
        entries.append((start, clock, account))

    return entries


def timeclock_anomalies(path: Path) -> tuple[int, int]:
    """Count structural inconsistencies in a timeclock file.

    Returns ``(dropped_opens, orphan_closes)``:
    - ``dropped_opens``: an ``i`` seen while an entry is already open —
      the prior open is silently overwritten (lost billable time).
    - ``orphan_closes``: an ``o`` with no matching open ``i`` — ignored.

    hledger timeclock is strictly sequential; concurrent/overlapping
    entries are malformed input. We do not try to reconstruct them
    (ambiguous) — we surface the inconsistency so silent under-billing
    becomes a visible, actionable warning instead.
    """
    if not path.exists():
        return (0, 0)
    dropped_opens = 0
    orphan_closes = 0
    is_open = False
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return (0, 0)
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        marker = parts[0]
        if marker == "i" and len(parts) >= 4:
            if is_open:
                dropped_opens += 1
            is_open = True
        elif marker == "o":
            if is_open:
                is_open = False
            else:
                orphan_closes += 1
    return (dropped_opens, orphan_closes)


def _compute_presence_today(sessions: list[AiSession], now: datetime) -> tuple[int, str]:
    """Return (presence_minutes, label) from today's AI session windows, merged at 30-min gap."""
    today = now.date()
    windows = [(s.start, s.end) for s in sessions if s.start.date() == today and s.end > s.start]
    if not windows:
        return 0, "auto-detected"
    windows.sort(key=lambda w: w[0])
    merged: list[tuple[datetime, datetime]] = [windows[0]]
    for start, end in windows[1:]:
        last_start, last_end = merged[-1]
        if (start - last_end).total_seconds() / 60 <= 30:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    total_minutes = int(sum((e - s).total_seconds() / 60 for s, e in merged))
    return total_minutes, "auto-detected"


def build_dashboard_state(project_dir: Path) -> DashboardState:
    """Build all data needed for the local Glass Cockpit."""
    from contextlib import suppress

    with suppress(Exception):
        from halyard.collectors.codex_app import import_codex_sessions

        import_codex_sessions()

    all_sessions = parse_sessions(project_dir)
    report = build_ai_report(project_dir, all_time=False)
    active_timer = read_active_timer()
    raw_human = build_human_time_report(project_dir)
    now = datetime.now()
    presence_minutes, presence_label = _compute_presence_today(all_sessions, now)
    human_time = HumanTimeReport(
        today_minutes=raw_human.today_minutes,
        month_minutes=raw_human.month_minutes,
        by_project=raw_human.by_project,
        presence_minutes=presence_minutes,
        presence_label=presence_label,
    )
    latest_session = max(report.sessions, key=lambda session: session.end, default=None)

    return DashboardState(
        project_dir=project_dir,
        report=report,
        human_time=human_time,
        active_timer=active_timer,
        latest_session=latest_session,
        all_sessions=all_sessions,
        health=build_health_checks(project_dir, report=report, active_timer=active_timer),
    )


def aggregate_session_dirs() -> list[Path]:
    """Return every real session source: registered projects + hub.

    `read_registry()` already filters to existing dirs with
    halyard.toml, so dead/temp registry entries are excluded. Only dirs
    that actually have an ai-sessions.log are kept; de-duped by resolved
    path, stable order (registry first, then hub).
    """
    from halyard.hub import find_hub
    from halyard.registry import read_registry

    seen: set[str] = set()
    dirs: list[Path] = []
    candidates = list(read_registry())
    hub = find_hub()
    if hub is not None:
        candidates.append(hub)
    for d in candidates:
        key = str(d.resolve())
        if key in seen:
            continue
        if (d / AI_LOG_FILENAME).exists():
            seen.add(key)
            dirs.append(d)
    return dirs


def _dedup_sessions(sessions: list[AiSession]) -> list[AiSession]:
    """De-dup sessions that appear in more than one source log."""
    seen: set[tuple[object, ...]] = set()
    out: list[AiSession] = []
    for s in sessions:
        key = (
            s.start,
            s.end,
            s.tool,
            s.model,
            s.input_tokens,
            s.output_tokens,
            s.project,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def build_aggregate_dashboard_state() -> DashboardState:
    """Dashboard state over the union of all real project logs + hub.

    Session-derived panels reflect total real work. The inherently
    per-project bits (timeclock, plans, budget, file-health) are scoped
    to a `primary` dir: the current project if inside one, else the
    hub, else the first source.
    """
    from contextlib import suppress

    from halyard.ai_log import find_project_dir
    from halyard.hub import find_hub

    with suppress(Exception):
        from halyard.collectors.codex_app import import_codex_sessions

        import_codex_sessions()

    dirs = aggregate_session_dirs()
    merged: list[AiSession] = []
    for d in dirs:
        merged.extend(parse_sessions(d))
    all_sessions = _dedup_sessions(merged)

    primary = find_project_dir() or find_hub() or (dirs[0] if dirs else Path.cwd())

    report = build_ai_report(primary, all_time=False, sessions=all_sessions)
    active_timer = read_active_timer()
    raw_human = build_human_time_report(primary)
    now = datetime.now()
    presence_minutes, presence_label = _compute_presence_today(all_sessions, now)
    human_time = HumanTimeReport(
        today_minutes=raw_human.today_minutes,
        month_minutes=raw_human.month_minutes,
        by_project=raw_human.by_project,
        presence_minutes=presence_minutes,
        presence_label=presence_label,
    )
    latest_session = max(report.sessions, key=lambda s: s.end, default=None)

    return DashboardState(
        project_dir=primary,
        report=report,
        human_time=human_time,
        active_timer=active_timer,
        latest_session=latest_session,
        all_sessions=all_sessions,
        health=build_health_checks(primary, report=report, active_timer=active_timer),
        aggregate_count=len(dirs),
    )


def build_health_checks(
    project_dir: Path,
    *,
    report: AiReport | None = None,
    active_timer: ActiveTimer | None = None,
) -> list[HealthCheck]:
    """Return user-facing collector and file health states."""
    ai_log = project_dir / AI_LOG_FILENAME
    checks = [
        HealthCheck("Project", "healthy", f"Found {project_dir.name}"),
        _file_check("AI session log", ai_log),
        _timeclock_check(project_dir / "time.timeclock"),
        _hook_check(project_dir),
        _cursor_hook_check(),
        _gemini_hook_check(),
    ]

    if active_timer:
        checks.append(HealthCheck("Active timer", "healthy", f"making way · {active_timer.slug}"))
    else:
        checks.append(HealthCheck("Active timer", "neutral", "⚓  at anchor"))

    report = report or build_ai_report(project_dir)
    if report.unattributed_count:
        checks.append(
            HealthCheck(
                "Attribution",
                "warning",
                f"· · · — — — · · ·  {report.unattributed_count} session(s) adrift",
            )
        )
    else:
        checks.append(HealthCheck("Attribution", "healthy", "Q · manifest clean"))

    return checks


def _bucket_costs(items: Iterable[tuple[str, float]]) -> list[CostBucket]:
    totals: dict[str, list[float]] = {}
    for label, cost in items:
        totals.setdefault(label, []).append(cost)

    return [
        CostBucket(label=label, cost_usd=sum(costs), sessions=len(costs))
        for label, costs in sorted(totals.items(), key=lambda item: -sum(item[1]))
    ]


def _tool_buckets_for_report(sessions: list[AiSession]) -> list[ToolUsageBucket]:
    totals: dict[str, dict[str, float | int]] = {}
    for session in sessions:
        row = totals.setdefault(session.tool, {"sessions": 0, "tokens": 0, "cost": 0.0})
        row["sessions"] = int(row["sessions"]) + 1
        tok = (
            session.input_tokens
            + session.output_tokens
            + (session.cache_read or 0)
            + (session.cache_write or 0)
            if session.tokens_available
            else 0
        )
        row["tokens"] = int(row["tokens"]) + tok
        row["cost"] = float(row["cost"]) + session.cost_usd
    total_sessions = sum(int(r["sessions"]) for r in totals.values())
    share = (lambda n: n / total_sessions) if total_sessions > 0 else (lambda _: 0.0)
    return sorted(
        [
            ToolUsageBucket(
                tool=tool,
                sessions=int(row["sessions"]),
                tokens=int(row["tokens"]),
                cost_usd=float(row["cost"]),
                session_share=share(int(row["sessions"])),
            )
            for tool, row in totals.items()
        ],
        key=lambda b: (-b.sessions, b.tool),
    )


def _file_check(label: str, path: Path) -> HealthCheck:
    if not path.exists():
        return HealthCheck(label, "error", f"Missing {path.name}")
    if not os.access(path, os.W_OK):
        return HealthCheck(label, "error", f"{path.name} is not writable")
    return HealthCheck(label, "healthy", f"{path.name} ready")


def _timeclock_check(path: Path) -> HealthCheck:
    if not path.exists():
        return HealthCheck("Timeclock", "neutral", "not started — run halyard start")
    if not os.access(path, os.W_OK):
        return HealthCheck("Timeclock", "error", "time.timeclock is not writable")
    dropped, orphans = timeclock_anomalies(path)
    if dropped or orphans:
        bits = []
        if dropped:
            bits.append(f"{dropped} unclosed clock-in(s) overwritten")
        if orphans:
            bits.append(f"{orphans} clock-out(s) with no clock-in")
        return HealthCheck(
            "Timeclock",
            "warning",
            f"structural issue: {'; '.join(bits)} — time may be undercounted. "
            "Fix the i/o pairs in time.timeclock.",
        )
    return HealthCheck("Timeclock", "healthy", "time.timeclock ready")


def _hook_check(project_dir: Path) -> HealthCheck:
    for path in [
        project_dir / ".claude" / "settings.json",
        Path.home() / ".claude" / "settings.json",
    ]:
        if _settings_has_halyard_hooks(path):
            return HealthCheck("Claude Code hook", "healthy", f"Installed in {path}")
    return HealthCheck("Claude Code hook", "warning", "Y · run halyard install-hook")


def _cursor_hook_check() -> HealthCheck:
    path = Path.home() / ".cursor" / "hooks.json"
    if not path.exists():
        return HealthCheck(
            "Cursor hook", "neutral", "N · not installed — run halyard install-cursor-hook"
        )
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, ValueError):
        return HealthCheck("Cursor hook", "error", "hooks.json is malformed")
    hooks: dict[str, object] = data.get("hooks", {})
    commands = [
        entry.get("command", "")
        for entries in hooks.values()
        if isinstance(entries, list)
        for entry in entries
        if isinstance(entry, dict)
    ]
    if any("halyard cursor-session" in c for c in commands) and any(
        "halyard cursor-hook" in c for c in commands
    ):
        return HealthCheck("Cursor hook", "healthy", f"Installed in {path}")
    return HealthCheck("Cursor hook", "warning", "Y · run halyard install-cursor-hook")


def _gemini_hook_check() -> HealthCheck:
    path = Path.home() / ".gemini" / "settings.json"
    if not path.exists():
        return HealthCheck(
            "Gemini CLI hook", "neutral", "N · not installed — run halyard install-gemini-hook"
        )
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, ValueError):
        return HealthCheck("Gemini CLI hook", "error", "settings.json is malformed")
    hooks: dict[str, object] = data.get("hooks", {})
    commands = [
        h.get("command", "")
        for entries in hooks.values()
        if isinstance(entries, list)
        for entry in entries
        if isinstance(entry, dict)
        for h in entry.get("hooks", [])
        if isinstance(h, dict)
    ]
    required = {"halyard gc-session", "halyard gc-model", "halyard gc-hook"}
    if all(any(r in c for c in commands) for r in required):
        return HealthCheck("Gemini CLI hook", "healthy", f"Installed in {path}")
    return HealthCheck("Gemini CLI hook", "warning", "Y · run halyard install-gemini-hook")


def _settings_has_halyard_hooks(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, ValueError):
        return False

    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return False

    commands = [
        hook.get("command")
        for entries in hooks.values()
        if isinstance(entries, list)
        for entry in entries
        if isinstance(entry, dict)
        for hook in entry.get("hooks", [])
        if isinstance(hook, dict)
    ]
    # Normalize "/path/to/halyard cc-hook" → "halyard cc-hook"
    normalized = {
        " ".join([Path(parts[0]).name, *parts[1:]]) for c in commands if c and (parts := c.split())
    }
    return "halyard cc-session" in normalized and "halyard cc-hook" in normalized


def format_minutes(minutes: int) -> str:
    """Format minutes as a compact duration."""
    hours, mins = divmod(max(0, minutes), 60)
    if hours:
        return f"{hours}h {mins:02d}m"
    return f"{mins}m"


def _elapsed_minutes(started: str, now: datetime) -> int:
    try:
        start = datetime.strptime(started, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return 0
    return max(0, int((now - start).total_seconds() // 60))


def _parse_timeclock_timestamp(day: str, time: str) -> datetime | None:
    try:
        return datetime.strptime(f"{day} {time}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
