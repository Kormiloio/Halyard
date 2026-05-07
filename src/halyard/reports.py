"""Reusable reporting and dashboard view models."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME, AiSession, parse_sessions

_HALYARD_ACTIVE = Path.home() / ".halyard" / "active"


@dataclass(frozen=True)
class CostBucket:
    label: str
    cost_usd: float
    sessions: int


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
    unattributed_count: int


@dataclass(frozen=True)
class ActiveTimer:
    slug: str
    timeclock: Path | None
    started: str | None


@dataclass(frozen=True)
class HealthCheck:
    label: str
    status: str
    detail: str


@dataclass(frozen=True)
class DashboardState:
    project_dir: Path
    report: AiReport
    active_timer: ActiveTimer | None
    health: list[HealthCheck]
    latest_session: AiSession | None
    generated_at: datetime = field(default_factory=datetime.now)


def build_ai_report(
    project_dir: Path,
    *,
    all_time: bool = False,
    now: datetime | None = None,
) -> AiReport:
    """Build the AI usage summary shared by CLI and dashboard."""
    clock = now or datetime.now()
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


def summarize_ai_sessions(sessions: list[AiSession], *, period_label: str) -> AiReport:
    """Aggregate parsed AI sessions into project/model/tool buckets."""
    total_cost = sum(session.cost_usd for session in sessions)
    total_input = sum(session.input_tokens for session in sessions)
    total_output = sum(session.output_tokens for session in sessions)
    total_cache_read = sum(session.cache_read or 0 for session in sessions)
    total_cache_write = sum(session.cache_write or 0 for session in sessions)

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
        unattributed_count=sum(1 for session in sessions if not session.project),
    )


def read_active_timer(active_path: Path = _HALYARD_ACTIVE) -> ActiveTimer | None:
    """Read the current active timer state, if any."""
    if not active_path.exists():
        return None

    data = dict(line.split("=", 1) for line in active_path.read_text().splitlines() if "=" in line)
    slug = data.get("slug")
    if not slug:
        return None

    timeclock = Path(data["timeclock"]) if data.get("timeclock") else None
    return ActiveTimer(slug=slug, timeclock=timeclock, started=data.get("started"))


def build_dashboard_state(project_dir: Path) -> DashboardState:
    """Build all data needed for the local Glass Cockpit."""
    report = build_ai_report(project_dir, all_time=False)
    active_timer = read_active_timer()
    latest_session = max(report.sessions, key=lambda session: session.end, default=None)

    return DashboardState(
        project_dir=project_dir,
        report=report,
        active_timer=active_timer,
        latest_session=latest_session,
        health=build_health_checks(project_dir, report=report, active_timer=active_timer),
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
        _file_check("Timeclock", project_dir / "time.timeclock"),
        _hook_check(project_dir),
    ]

    if active_timer:
        checks.append(HealthCheck("Active timer", "healthy", active_timer.slug))
    else:
        checks.append(HealthCheck("Active timer", "neutral", "No active timer"))

    report = report or build_ai_report(project_dir)
    if report.unattributed_count:
        checks.append(
            HealthCheck(
                "Attribution",
                "warning",
                f"{report.unattributed_count} session(s) need a project",
            )
        )
    else:
        checks.append(HealthCheck("Attribution", "healthy", "All captured sessions attributed"))

    return checks


def _bucket_costs(items: Iterable[tuple[str, float]]) -> list[CostBucket]:
    totals: dict[str, list[float]] = {}
    for label, cost in items:
        totals.setdefault(label, []).append(cost)

    return [
        CostBucket(label=label, cost_usd=sum(costs), sessions=len(costs))
        for label, costs in sorted(totals.items(), key=lambda item: -sum(item[1]))
    ]


def _file_check(label: str, path: Path) -> HealthCheck:
    if not path.exists():
        return HealthCheck(label, "error", f"Missing {path.name}")
    if not os.access(path, os.W_OK):
        return HealthCheck(label, "error", f"{path.name} is not writable")
    return HealthCheck(label, "healthy", f"{path.name} ready")


def _hook_check(project_dir: Path) -> HealthCheck:
    for path in [
        project_dir / ".claude" / "settings.json",
        Path.home() / ".claude" / "settings.json",
    ]:
        if _settings_has_halyard_hooks(path):
            return HealthCheck("Claude Code hook", "healthy", f"Installed in {path}")
    return HealthCheck("Claude Code hook", "warning", "Run halyard install-hook")


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
    return "halyard cc-session" in commands and "halyard cc-hook" in commands
