"""Onboarding diagnostics for local Halyard capture."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from halyard.ai_log import AI_LOG_FILENAME, AiSession, find_project_dir, parse_sessions
from halyard.hub import find_hub

ToolScope = Literal["claude", "cursor", "gemini", "all"]
CheckStatus = Literal["ok", "warning", "error", "skipped"]
ReportStatus = Literal["ok", "warning", "error"]


@dataclass(frozen=True)
class DoctorCheck:
    id: str
    label: str
    status: CheckStatus
    detail: str
    fix: str | None = None


@dataclass(frozen=True)
class DoctorReport:
    status: ReportStatus
    checks: list[DoctorCheck]

    def to_jsonable(self) -> dict[str, object]:
        return {"status": self.status, "checks": [asdict(check) for check in self.checks]}


def build_doctor_report(
    *,
    start: Path | None = None,
    tool: ToolScope = "all",
    first_capture: bool = False,
    now: datetime | None = None,
) -> DoctorReport:
    """Build a local diagnostics report without mutating user files."""
    current = start or Path.cwd()
    project_dir = find_project_dir(start=current)
    hub_dir = find_hub()
    checks: list[DoctorCheck] = []

    checks.extend(_platform_checks())
    checks.extend(_project_checks(project_dir, hub_dir))
    checks.extend(_hub_checks(project_dir, hub_dir))
    checks.extend(_hook_checks(tool, current))
    checks.extend(_collector_state_checks())
    if first_capture:
        checks.append(_first_capture_check(project_dir, hub_dir, now=now or datetime.now()))

    return DoctorReport(status=_report_status(checks), checks=checks)


def _shorten(text: str) -> str:
    """Replace the home directory prefix with ~ for compact display."""
    home = str(Path.home())
    return text.replace(home, "~") if home in text else text


def render_text(report: DoctorReport) -> str:
    lines = ["Halyard Doctor", "─" * 48]
    for check in report.checks:
        status = check.status.upper()
        lines.append(f"{status:<7} {check.label:<18} {_shorten(check.detail)}")
        if check.fix:
            lines.append(f"        fix: {check.fix}")
    lines.append("─" * 48)
    lines.append(f"status: {report.status}")
    return "\n".join(lines)


def render_json(report: DoctorReport) -> str:
    return json.dumps(report.to_jsonable(), indent=2) + "\n"


def has_errors(report: DoctorReport) -> bool:
    return any(check.status == "error" for check in report.checks)


def _platform_checks() -> list[DoctorCheck]:
    if sys.platform == "win32":
        return [
            DoctorCheck(
                id="platform",
                label="platform",
                status="warning",
                detail="Windows is not fully supported — file locking requires POSIX fcntl.",
                fix="Use WSL2 for full support. Concurrent writes are unsafe on Windows.",
            )
        ]
    return [
        DoctorCheck(id="platform", label="platform", status="ok", detail=f"POSIX ({sys.platform})")
    ]


def _project_checks(project_dir: Path | None, hub_dir: Path | None) -> list[DoctorCheck]:
    if project_dir is None:
        if hub_dir is not None:
            return [
                DoctorCheck(
                    id="project.found",
                    label="Project",
                    status="warning",
                    detail="not in a project; ambient capture will use hub",
                    fix=None,
                )
            ]
        return [
            DoctorCheck(
                id="project.found",
                label="Project",
                status="error",
                detail="no Halyard project found",
                fix="halyard init or halyard hub <path>",
            )
        ]

    checks = [
        DoctorCheck(
            id="project.found",
            label="Project",
            status="ok",
            detail=str(project_dir),
        )
    ]
    log_path = project_dir / AI_LOG_FILENAME
    if not log_path.exists():
        checks.append(
            DoctorCheck(
                id="project.log.exists",
                label="AI log",
                status="error",
                detail="missing",
                fix="halyard init",
            )
        )
    elif _is_writable(log_path):
        checks.append(
            DoctorCheck(
                id="project.log.writable",
                label="AI log",
                status="ok",
                detail="writable",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                id="project.log.writable",
                label="AI log",
                status="error",
                detail="not writable",
                fix="check file permissions",
            )
        )
    return checks


def _hub_checks(project_dir: Path | None, hub_dir: Path | None) -> list[DoctorCheck]:
    pointer = Path.home() / ".halyard" / "hub"
    if hub_dir is None:
        status: CheckStatus = "warning" if project_dir is not None else "error"
        return [
            DoctorCheck(
                id="hub.configured",
                label="Hub",
                status=status,
                detail="no hub configured",
                fix="halyard init --hub or halyard hub <path>",
            )
        ]

    log_path = hub_dir / AI_LOG_FILENAME
    if not (hub_dir / "halyard.toml").exists() or not log_path.exists():
        return [
            DoctorCheck(
                id="hub.valid",
                label="Hub",
                status="error",
                detail=f"{hub_dir} is missing halyard.toml or ai-sessions.log",
                fix="point hub at a valid Halyard project",
            )
        ]

    detail = str(hub_dir)
    if pointer.exists():
        detail = f"{hub_dir} ({pointer})"
    return [DoctorCheck(id="hub.valid", label="Hub", status="ok", detail=detail)]


def _hook_checks(tool: ToolScope, current: Path) -> list[DoctorCheck]:
    scopes = ("claude", "cursor", "gemini") if tool == "all" else (tool,)
    checks: list[DoctorCheck] = []
    for scope in scopes:
        required = tool != "all"
        if scope == "claude":
            checks.append(_claude_hook_check(current, required=required))
            dup = _claude_hook_duplicate_check(current)
            if dup is not None:
                checks.append(dup)
        elif scope == "cursor":
            checks.append(_cursor_hook_check(required=required))
        elif scope == "gemini":
            checks.append(_gemini_hook_check(required=required))
    return checks


def _claude_hook_check(current: Path, *, required: bool) -> DoctorCheck:
    paths = [current / ".claude" / "settings.json", Path.home() / ".claude" / "settings.json"]
    commands = _commands_from_claude_settings(paths)
    if _has_command(commands, "cc-session") and _has_command(commands, "cc-hook"):
        return DoctorCheck(
            id="hook.claude",
            label="Claude Code",
            status="ok",
            detail="hooks installed",
        )
    return DoctorCheck(
        id="hook.claude",
        label="Claude Code",
        status="error" if required else "warning",
        detail="hooks missing",
        fix="halyard install-hook",
    )


def _claude_hook_duplicate_check(current: Path) -> DoctorCheck | None:
    local_path = current / ".claude" / "settings.json"
    global_path = Path.home() / ".claude" / "settings.json"
    local_keys = {_cmd_key(c) for c in _commands_from_claude_settings([local_path])}
    global_keys = {_cmd_key(c) for c in _commands_from_claude_settings([global_path])}
    if local_keys & global_keys:
        return DoctorCheck(
            id="hook.claude.duplicate",
            label="Claude Code (duplicate hooks)",
            status="warning",
            detail="hooks in both local and global settings — sessions recorded twice",
            fix=f"remove hooks from {local_path} or {global_path}",
        )
    return None


def _cursor_hook_check(*, required: bool) -> DoctorCheck:
    path = Path.home() / ".cursor" / "hooks.json"
    commands = _commands_from_cursor_settings(path)
    if _has_command(commands, "cursor-session") and _has_command(commands, "cursor-hook"):
        return DoctorCheck(id="hook.cursor", label="Cursor", status="ok", detail="hooks installed")
    return DoctorCheck(
        id="hook.cursor",
        label="Cursor",
        status="error" if required else "warning",
        detail="hooks missing",
        fix="halyard install-cursor-hook",
    )


def _gemini_hook_check(*, required: bool) -> DoctorCheck:
    path = Path.home() / ".gemini" / "settings.json"
    commands = _commands_from_gemini_settings(path)
    if (
        _has_command(commands, "gc-session")
        and _has_command(commands, "gc-model")
        and _has_command(commands, "gc-hook")
    ):
        return DoctorCheck(
            id="hook.gemini",
            label="Gemini CLI",
            status="ok",
            detail="hooks installed",
        )
    return DoctorCheck(
        id="hook.gemini",
        label="Gemini CLI",
        status="error" if required else "warning",
        detail="hooks missing",
        fix="halyard install-gemini-hook",
    )


def _integrity_check(home_state: Path) -> DoctorCheck:
    """Report the active state-integrity mode and verify tracked files."""
    from halyard.state_integrity import current_mode, verify_all

    mode = current_mode()
    if mode == "off":
        return DoctorCheck(
            id="state.integrity",
            label="Integrity",
            status="skipped",
            detail="mode=off (opt-in via halyard.toml state_integrity)",
        )

    tracked = [home_state / "active", home_state / "hub"]
    ok, failure = verify_all([p for p in tracked if p.exists()])
    if ok:
        return DoctorCheck(
            id="state.integrity",
            label="Integrity",
            status="ok",
            detail=f"mode={mode} — all tracked sidecars verify",
        )
    return DoctorCheck(
        id="state.integrity",
        label="Integrity",
        status="warning",
        detail=f"mode={mode} — verification failed at {failure}",
        fix="inspect the tampered file or re-write via halyard CLI",
    )


def _collector_state_checks() -> list[DoctorCheck]:
    home_state = Path.home() / ".halyard"
    checks: list[DoctorCheck] = []

    active = home_state / "active"
    if active.exists():
        slug = _active_slug(active)
        checks.append(
            DoctorCheck(
                id="state.active",
                label="Active timer",
                status="ok",
                detail=slug or "active timer present",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                id="state.active",
                label="Active timer",
                status="skipped",
                detail="none",
            )
        )

    unattributed = home_state / "unattributed.log"
    unattributed_count = _count_session_lines(unattributed)
    if unattributed_count:
        groups = _group_unattributed_by_remote(unattributed)
        fix_lines = ["run 'halyard adopt' in each repo:"]
        for remote, count in sorted(groups.items(), key=lambda x: -x[1]):
            fix_lines.append(f"          {remote} ({count} session{'s' if count != 1 else ''})")
        checks.append(
            DoctorCheck(
                id="state.unattributed",
                label="Unattributed",
                status="warning",
                detail=f"{unattributed_count} session(s) across {len(groups)} source(s)",
                fix="\n".join(fix_lines),
            )
        )
    else:
        checks.append(
            DoctorCheck(
                id="state.unattributed",
                label="Unattributed",
                status="ok",
                detail="none",
            )
        )

    quarantine = home_state / "quarantine.log"
    if quarantine.exists():
        checks.append(
            DoctorCheck(
                id="state.quarantine",
                label="Quarantine",
                status="warning",
                detail=str(quarantine),
                fix="halyard check-log",
            )
        )
    else:
        checks.append(
            DoctorCheck(id="state.quarantine", label="Quarantine", status="ok", detail="none")
        )

    checks.append(_integrity_check(home_state))

    for name, filename in (("Gemini state", "gc-session"), ("Cursor state", "cursor-session")):
        path = home_state / filename
        checks.append(
            DoctorCheck(
                id=f"state.{filename}",
                label=name,
                status="ok" if path.exists() else "skipped",
                detail=_age_detail(path) if path.exists() else "none",
            )
        )

    return checks


def _first_capture_check(
    project_dir: Path | None,
    hub_dir: Path | None,
    *,
    now: datetime,
) -> DoctorCheck:
    cutoff = now - timedelta(minutes=30)
    destinations = [p for p in (project_dir, hub_dir) if p is not None]
    for destination in destinations:
        recent = _latest_recent_session(destination, cutoff)
        if recent is not None:
            return DoctorCheck(
                id="first_capture.recent",
                label="First capture",
                status="ok",
                detail=_session_detail(recent),
            )

    unattributed_recent = _latest_recent_session_file(
        Path.home() / ".halyard" / "unattributed.log", cutoff
    )
    if unattributed_recent is not None:
        return DoctorCheck(
            id="first_capture.unattributed",
            label="First capture",
            status="warning",
            detail=_session_detail(unattributed_recent),
            fix="halyard assign-unattributed",
        )

    quarantine = Path.home() / ".halyard" / "quarantine.log"
    if quarantine.exists():
        return DoctorCheck(
            id="first_capture.quarantine",
            label="First capture",
            status="warning",
            detail="quarantine file exists",
            fix="halyard check-log",
        )

    return DoctorCheck(
        id="first_capture.missing",
        label="First capture",
        status="error",
        detail="no session captured in the last 30 minutes",
        fix="check hooks, run an AI tool, then rerun halyard doctor --first-capture",
    )


def _latest_recent_session(project_dir: Path, cutoff: datetime) -> AiSession | None:
    sessions = [s for s in parse_sessions(project_dir) if s.end >= cutoff]
    return max(sessions, key=lambda s: s.end) if sessions else None


def _latest_recent_session_file(path: Path, cutoff: datetime) -> AiSession | None:
    if not path.exists():
        return None
    sessions: list[AiSession] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        session = AiSession.from_log_line(stripped)
        if session is not None and session.end >= cutoff:
            sessions.append(session)
    return max(sessions, key=lambda s: s.end) if sessions else None


def _session_detail(session: AiSession) -> str:
    project = session.project or "(unattributed)"
    return f"{session.tool} {session.model} {project} at {session.end:%Y-%m-%d %H:%M:%S}"


def _cmd_key(cmd: str) -> str:
    """Normalise a hook command to subcommand name for cross-path comparison."""
    parts = cmd.split()
    return f"{Path(parts[0]).name} {' '.join(parts[1:])}" if parts else cmd


def _commands_from_claude_settings(paths: list[Path]) -> list[str]:
    commands: list[str] = []
    for path in paths:
        data = _read_json(path)
        hooks = data.get("hooks") if isinstance(data, dict) else None
        if not isinstance(hooks, dict):
            continue
        for entries in hooks.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                for hook in entry.get("hooks", []):
                    if isinstance(hook, dict) and isinstance(hook.get("command"), str):
                        commands.append(hook["command"])
    return commands


def _commands_from_gemini_settings(path: Path) -> list[str]:
    commands: list[str] = []
    data = _read_json(path)
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        return commands
    for entries in hooks.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for hook in entry.get("hooks", []):
                if isinstance(hook, dict) and isinstance(hook.get("command"), str):
                    commands.append(hook["command"])
    return commands


def _commands_from_cursor_settings(path: Path) -> list[str]:
    commands: list[str] = []
    data = _read_json(path)
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        return commands
    for entries in hooks.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("command"), str):
                commands.append(entry["command"])
    return commands


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _has_command(commands: list[str], token: str) -> bool:
    return any(token in command for command in commands)


def _is_writable(path: Path) -> bool:
    try:
        with path.open("a"):
            return True
    except OSError:
        return False


def _count_session_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text().splitlines() if line.strip().startswith("s "))


def _active_slug(path: Path) -> str | None:
    try:
        for line in path.read_text().splitlines():
            if line.startswith("slug="):
                return line[5:]
    except OSError:
        return None
    return None


def _age_detail(path: Path) -> str:
    try:
        seconds = int(datetime.now().timestamp() - path.stat().st_mtime)
    except OSError:
        return str(path)
    return f"{path} ({seconds}s old)"


def _report_status(checks: list[DoctorCheck]) -> ReportStatus:
    statuses = {check.status for check in checks}
    if "error" in statuses:
        return "error"
    if "warning" in statuses:
        return "warning"
    return "ok"


def _group_unattributed_by_remote(log_path: Path) -> dict[str, int]:
    """Parse unattributed.log and return session counts grouped by remote."""
    groups: dict[str, int] = {}
    if not log_path.exists():
        return groups
    try:
        for raw_line in log_path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip().startswith("s "):
                continue
            session = AiSession.from_log_line(raw_line)
            if session is None:
                continue
            key = session.remote or "(no git remote)"
            groups[key] = groups.get(key, 0) + 1
    except OSError:
        pass
    return groups
