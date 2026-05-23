"""Onboarding diagnostics for local Halyard capture."""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from halyard.ai_log import AI_LOG_FILENAME, AiSession, find_project_dir, parse_sessions
from halyard.hub import find_hub

ToolScope = Literal["claude", "cursor", "gemini", "windsurf", "copilot", "all"]
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
    if tool in ("all", "copilot"):
        copilot_otel = _copilot_otel_check()
        if copilot_otel is not None:
            checks.append(copilot_otel)
    checks.extend(_unwired_tool_checks(tool, current))
    checks.extend(_collector_drift_checks(project_dir, hub_dir))
    checks.extend(_capture_coverage_checks(project_dir, hub_dir, now=now))
    checks.extend(_attribution_quality_checks(project_dir, hub_dir))
    checks.extend(_collector_state_checks(project_dir, hub_dir))
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
    scopes = ("claude", "cursor", "gemini", "windsurf") if tool == "all" else (tool,)
    checks: list[DoctorCheck] = []
    for scope in scopes:
        if scope == "copilot":
            continue
        required = tool != "all"
        if scope == "claude":
            checks.append(_claude_hook_check(current, required=required))
            dup = _claude_hook_duplicate_check(current)
            if dup is not None:
                checks.append(dup)
        elif scope == "cursor":
            checks.append(_cursor_hook_check(required=required))
        elif scope == "gemini":
            gem = _gemini_hook_check(required=required)
            checks.append(gem)
            if gem.status == "ok":
                tel = _gemini_telemetry_check()
                if tel is not None:
                    checks.append(tel)
        elif scope == "windsurf":
            checks.append(_windsurf_hook_check(required=required))
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


def _gemini_telemetry_check() -> DoctorCheck | None:
    """Nudge (warn-only) when the Gemini hook is on but the opt-in OTLP
    outfile is off, so api/tool time can't be captured (v2.67). Never
    an error — the doctor exit code must not change.
    """
    path = Path.home() / ".gemini" / "settings.json"
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    tel = data.get("telemetry") if isinstance(data, dict) else None
    outfile = tel.get("outfile") if isinstance(tel, dict) else None
    if isinstance(tel, dict) and tel.get("enabled") is not False and outfile:
        return DoctorCheck(
            id="telemetry.gemini",
            label="Gemini telemetry",
            status="ok",
            detail="OTLP outfile configured",
        )
    return DoctorCheck(
        id="telemetry.gemini",
        label="Gemini telemetry",
        status="warning",
        detail="off — api/tool time not captured",
        fix="halyard install-gemini-telemetry",
    )


def _copilot_otel_check() -> DoctorCheck | None:
    """Nudge (warn-only) when VS Code Copilot history is on disk but the
    durable OTel capture path is not configured (v3.12). Never an error —
    the doctor exit code must not change. Returns None when no Copilot
    history exists (nothing to nudge about).
    """
    from halyard.collectors.copilot import copilot_history_present
    from halyard.collectors.vscode_otel import otel_capture_enabled

    if not copilot_history_present():
        return None
    if otel_capture_enabled():
        return DoctorCheck(
            id="telemetry.copilot",
            label="Copilot OTel",
            status="ok",
            detail="OTel capture configured",
        )
    return DoctorCheck(
        id="telemetry.copilot",
        label="Copilot OTel",
        status="warning",
        detail="off — Copilot sessions rely on the brittle file importer",
        fix="halyard install-vscode-otel",
    )


def _windsurf_hook_check(*, required: bool) -> DoctorCheck:
    path = Path.home() / ".codeium" / "windsurf" / "hooks.json"
    commands = _commands_from_windsurf_settings(path)
    if _has_command(commands, "windsurf-session-start") and _has_command(
        commands, "windsurf-session-stop"
    ):
        return DoctorCheck(
            id="hook.windsurf", label="Windsurf", status="ok", detail="hooks installed"
        )
    return DoctorCheck(
        id="hook.windsurf",
        label="Windsurf",
        status="error" if required else "warning",
        detail="hooks missing",
        fix="halyard install-hook-windsurf",
    )


# client -> mcpServers config file, relative to ~ (recomputed per call
# so a relocated home in tests is honoured, matching the hook checks).
_MCP_CONFIG_REL: dict[str, tuple[str, ...]] = {
    "claude": (".claude.json",),
    "cursor": (".cursor", "mcp.json"),
    "gemini": (".gemini", "settings.json"),
    "windsurf": (".codeium", "windsurf", "mcp_config.json"),
}


def _mcp_registered(client: str) -> bool:
    """True if the Halyard MCP server is registered in *client*'s config.

    Basename-matches the server command so a moved venv still counts as
    wired (mirrors the hook installers' path-agnostic matching).
    """
    path = Path.home().joinpath(*_MCP_CONFIG_REL[client])
    data = _read_json(path)
    if not isinstance(data, dict):
        return False
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return False
    entry = servers.get("halyard")
    if not isinstance(entry, dict):
        return False
    command = entry.get("command")
    if not isinstance(command, str) or not command:
        return False
    return Path(command).name in ("halyard", "halyard.exe")


def _unwired_tool_checks(tool: ToolScope, current: Path) -> list[DoctorCheck]:
    """Warn about supported AI tools that are installed but not wired.

    A live-hook tool counts as wired if it has Halyard hooks OR the
    Halyard MCP server for its scope; the nudge fires only when a
    detected tool has zero Halyard integration. Codex (import model)
    warns when on-disk history exists but nothing has been imported.
    Always `warning`, never `error`, so the doctor exit code is
    unaffected.
    """
    scopes = ("claude", "cursor", "gemini", "windsurf") if tool == "all" else (tool,)
    hook_status: dict[str, Callable[[], CheckStatus]] = {
        "claude": lambda: _claude_hook_check(current, required=False).status,
        "cursor": lambda: _cursor_hook_check(required=False).status,
        "gemini": lambda: _gemini_hook_check(required=False).status,
        "windsurf": lambda: _windsurf_hook_check(required=False).status,
        "copilot": lambda: "skipped",  # Copilot has no hooks
    }
    labels = {
        "claude": "Claude Code",
        "cursor": "Cursor",
        "gemini": "Gemini CLI",
        "windsurf": "Windsurf",
        "copilot": "GitHub Copilot",
    }
    install_hook = {
        "claude": "halyard install-hook-claude",
        "cursor": "halyard install-hook-cursor",
        "gemini": "halyard install-hook-gemini",
        "windsurf": "halyard install-hook-windsurf",
    }

    checks: list[DoctorCheck] = []
    for scope in scopes:
        if scope == "copilot":
            continue
        on_path = shutil.which(scope) is not None
        has_hook = hook_status[scope]() == "ok"
        has_mcp = _mcp_registered(scope)
        if on_path and not has_hook and not has_mcp:
            checks.append(
                DoctorCheck(
                    id=f"unwired.{scope}",
                    label=f"{labels[scope]} (unwired)",
                    status="warning",
                    detail="installed but no Halyard hooks or MCP server",
                    fix=f"halyard setup  (or {install_hook[scope]})",
                )
            )

    if tool in ("all", "copilot"):
        from halyard.collectors.copilot import copilot_history_present, copilot_imported_any

        if copilot_history_present() and not copilot_imported_any():
            checks.append(
                DoctorCheck(
                    id="unwired.copilot",
                    label="Copilot (unwired)",
                    status="warning",
                    detail="GitHub Copilot history on disk but none imported",
                    fix="halyard import-copilot",
                )
            )

    if tool == "all":
        from halyard.collectors.codex_app import codex_history_present, codex_imported_any

        if codex_history_present() and not codex_imported_any():
            checks.append(
                DoctorCheck(
                    id="unwired.codex",
                    label="Codex (unwired)",
                    status="warning",
                    detail="Codex Desktop history on disk but none imported",
                    fix="halyard import-codex",
                )
            )

    return checks


# Recent-run length and minimum-history gate for the drift canary.
_DRIFT_WINDOW = 5
_UNREAL_MODELS = {"", "default"}


def _model_unreal(model: str) -> bool:
    """True if a session's model is a placeholder, not a real model.

    Mirrors collectors._model_is_real (replicated so doctor stays
    import-light, matching how it already inlines such predicates).
    """
    return (not model) or model in _UNREAL_MODELS or model.endswith("-unknown")


# Recent/prior window for the attribution-quality canary, and the
# adrift-share rise (percentage points) that trips it.
_ATTR_WINDOW = 20
_ATTR_ADRIFT_MARGIN = 0.20


def _link_repo_command(remote: str) -> str:
    """Single source of the adrift remediation command (shared w/ moat)."""
    from halyard.moat import link_repo_command

    return link_repo_command(remote)


def _sessions_for(project_dir: Path | None, hub_dir: Path | None) -> list[AiSession]:
    sessions: list[AiSession] = []
    seen: set[Path] = set()
    for d in (project_dir, hub_dir):
        if d is None:
            continue
        rd = d.resolve()
        if rd in seen:
            continue
        seen.add(rd)
        sessions.extend(parse_sessions(d))
    return sessions


def _attribution_quality_checks(
    project_dir: Path | None, hub_dir: Path | None
) -> list[DoctorCheck]:
    """Warn when project attribution *regresses* (detection only).

    Two signals, both `warning` (never `error` — attribution gaps
    don't break Halyard, they erode the moat):

    - adrift-rate regression: the recent window is markedly more
      unattributed than the prior window (a config/mapping broke);
    - per-remote regression: a remote that had attributed sessions in
      the prior window now produces only unattributed ones (moved
      project / repos.toml drift / deleted halyard.toml).
    """
    sessions = _sessions_for(project_dir, hub_dir)
    if len(sessions) < 2 * _ATTR_WINDOW:
        return []
    ordered = sorted(sessions, key=lambda s: s.start)
    prior = ordered[-2 * _ATTR_WINDOW : -_ATTR_WINDOW]
    recent = ordered[-_ATTR_WINDOW:]

    checks: list[DoctorCheck] = []

    def adrift_share(rows: list[AiSession]) -> float:
        return sum(1 for s in rows if not s.project) / len(rows) if rows else 0.0

    prior_share = adrift_share(prior)
    recent_share = adrift_share(recent)
    if recent_share - prior_share > _ATTR_ADRIFT_MARGIN:
        checks.append(
            DoctorCheck(
                id="attr.adrift_regression",
                label="Attribution (adrift rising)",
                status="warning",
                detail=(
                    f"unattributed share rose {prior_share:.0%} → {recent_share:.0%} "
                    f"over the last {_ATTR_WINDOW} sessions"
                ),
                fix=(
                    "a project mapping likely broke — `halyard doctor` lists "
                    "unattributed remotes; re-run `halyard link-repo`/`halyard adopt`"
                ),
            )
        )

    def attributed_remotes(rows: list[AiSession]) -> set[str]:
        return {s.remote for s in rows if s.remote and s.project}

    def remotes_now_all_adrift(rows: list[AiSession]) -> set[str]:
        by_remote: dict[str, list[AiSession]] = {}
        for s in rows:
            if s.remote:
                by_remote.setdefault(s.remote, []).append(s)
        return {r for r, rs in by_remote.items() if all(not s.project for s in rs)}

    regressed = attributed_remotes(prior) & remotes_now_all_adrift(recent)
    for remote in sorted(regressed):
        checks.append(
            DoctorCheck(
                id=f"attr.remote.{remote}",
                label="Attribution (remote regressed)",
                status="warning",
                detail=(
                    f"{remote} attributed cleanly before but its recent sessions "
                    "are all unattributed"
                ),
                fix=_link_repo_command(remote),
            )
        )
    return checks


def _collector_drift_checks(project_dir: Path | None, hub_dir: Path | None) -> list[DoctorCheck]:
    """Warn when a tool's recent capture regressed to unreal models.

    Detection only: an upstream tool format change makes a collector
    record sessions without a real model. Per tool, if the most recent
    _DRIFT_WINDOW sessions are *all* unreal-model while an older session
    for the same tool had a real model (a healthy baseline → this is a
    regression, not a never-worked tool), emit a warning. Never error —
    capture still works, enrichment degraded.
    """
    sessions: list[AiSession] = []
    seen: set[Path] = set()
    for d in (project_dir, hub_dir):
        if d is None:
            continue
        rd = d.resolve()
        if rd in seen:
            continue
        seen.add(rd)
        sessions.extend(parse_sessions(d))

    by_tool: dict[str, list[AiSession]] = {}
    for s in sessions:
        by_tool.setdefault(s.tool, []).append(s)

    checks: list[DoctorCheck] = []
    for tool, tool_sessions in sorted(by_tool.items()):
        if len(tool_sessions) < _DRIFT_WINDOW:
            continue
        ordered = sorted(tool_sessions, key=lambda s: s.start)
        recent = ordered[-_DRIFT_WINDOW:]
        older = ordered[:-_DRIFT_WINDOW]
        recent_all_unreal = all(_model_unreal(s.model) for s in recent)
        had_healthy_baseline = any(not _model_unreal(s.model) for s in older)
        if recent_all_unreal and had_healthy_baseline:
            checks.append(
                DoctorCheck(
                    id=f"drift.{tool}",
                    label=f"{tool} (collector drift)",
                    status="warning",
                    detail=(
                        f"last {_DRIFT_WINDOW} {tool} sessions have no real model "
                        "(was capturing it before) — upstream format may have changed"
                    ),
                    fix=(
                        f"check the {tool} hook/output and the tool's version; "
                        "`halyard doctor --tool <claude|cursor|gemini>` for hook health"
                    ),
                )
            )
    return checks


# Capture-coverage canary. The 2026-05 Gemini outage went unnoticed for 16
# days because doctor only checked "hooks installed", and the drift canary
# (which keys on recent rows) can't see a tool that produces *no* rows. This
# canary compares each live-capture tool's newest on-disk session file against
# its last captured row: if the tool keeps writing sessions while the ledger
# stalls, capture silently broke. Grace days absorb normal lag (an in-flight
# turn, an idle gap) without false positives.
_COVERAGE_LAG_DAYS = 2

# Cursor and Windsurf keep chat/agent state in SQLite/leveldb stores, not
# enumerable per-session files (v3.15). Parsing those would re-introduce the
# fragile vendor-format scraping v3.12 escaped, so the canary uses only their
# storage *mtime* — a coarser "the app was active" signal that can move for
# incidental reasons (opening a workspace, indexing). These tools therefore get
# a wider grace and a best-effort, honestly-qualified warning.
_COVERAGE_LAG_DAYS_COARSE = 4

_COVERAGE_FIX = {
    "claude-code": (
        "recent turns may be unrecorded — check the Stop hook "
        "(`halyard doctor --tool claude`) and upgrade the installed halyard binary"
    ),
    "gemini-cli": (
        "recover with `halyard import-gemini`, then check the AfterAgent hook "
        "(`halyard doctor --tool gemini`)"
    ),
    "github-copilot": (
        "run `halyard import-copilot` — if it still misses sessions the VS Code "
        "storage format may have changed (see collectors/copilot.py)"
    ),
    "codex": "run `halyard import-codex` (or enable the scheduled importer)",
    "cursor": (
        "if you used Cursor's AI features recently the hook may not be firing — "
        "reinstall with `halyard install-hook-cursor`; ignore if you only browsed code"
    ),
    "windsurf": (
        "if you used Windsurf's Cascade recently the hook may not be firing — "
        "reinstall with `halyard install-hook-windsurf`; ignore if you only browsed code"
    ),
}

# Live-capture tools read an on-disk source continuously; importer tools only
# land in the ledger when an importer runs. Both are probed the same way — disk
# newer than the last captured row by > grace means capture is lagging — but a
# broken importer is the failure this caught for Copilot (format drift made
# every session silently skip).
_COVERAGE_TOOLS = ("claude-code", "gemini-cli", "github-copilot", "codex")
# Hook-only tools with no enumerable session files — probed via coarse storage
# mtime with a wider grace (v3.15). See `_COVERAGE_LAG_DAYS_COARSE`.
_COVERAGE_TOOLS_COARSE = ("cursor", "windsurf")


def _newest_disk_activity(tool: str) -> datetime | None:
    """Newest mtime among a tool's on-disk session files.

    Returns None for an un-probed tool or when no files exist.
    """
    paths: list[Path] = []
    try:
        if tool == "claude-code":
            root = Path.home() / ".claude" / "projects"
            if root.exists():
                paths = list(root.glob("*/*.jsonl"))
        elif tool == "gemini-cli":
            from halyard.collectors.gemini_history import find_all_session_files

            paths = find_all_session_files()
        elif tool == "github-copilot":
            from halyard.collectors.copilot import _VSCODE_STORAGE_DIR

            if _VSCODE_STORAGE_DIR.exists():
                paths = list(_VSCODE_STORAGE_DIR.glob("*/chatSessions/*.jsonl"))
        elif tool == "codex":
            from halyard.collectors.codex_app import _CODEX_SESSIONS_DIR

            if _CODEX_SESSIONS_DIR.exists():
                paths = list(_CODEX_SESSIONS_DIR.rglob("rollout-*.jsonl"))
        elif tool == "cursor":
            # Coarse signal (v3.15): mtime of Cursor's chat/composer SQLite
            # stores. Never read their contents — a schema change must not break
            # this; an mtime shift is exactly the activity signal we want.
            cursor_user = Path.home() / "Library" / "Application Support" / "Cursor" / "User"
            if cursor_user.exists():
                paths = [cursor_user / "globalStorage" / "state.vscdb"]
                paths.extend(cursor_user.glob("workspaceStorage/*/state.vscdb"))
        elif tool == "windsurf":
            cascade = Path.home() / ".codeium" / "windsurf" / "cascade"
            if cascade.exists():
                paths = [p for p in cascade.rglob("*") if p.is_file()]
        else:
            return None
    except OSError:
        return None
    newest: float | None = None
    for p in paths:
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if newest is None or m > newest:
            newest = m
    return datetime.fromtimestamp(newest) if newest is not None else None


def _capture_coverage_checks(
    project_dir: Path | None, hub_dir: Path | None, *, now: datetime | None = None
) -> list[DoctorCheck]:
    """Warn when a live-capture tool's ledger lags fresh on-disk activity.

    For each probed tool with a capture baseline (≥1 recorded row — so a
    never-used tool can't false-positive), if its on-disk session files are
    more than ``_COVERAGE_LAG_DAYS`` newer than the last captured row, capture
    is likely broken. Detection only; ``warning``, never ``error`` (the
    exit-code contract is preserved).
    """
    del now  # reserved for symmetry with other check builders; disk drives timing
    sessions = _sessions_for(project_dir, hub_dir)
    last_end: dict[str, datetime] = {}
    for s in sessions:
        cur = last_end.get(s.tool)
        if cur is None or s.end > cur:
            last_end[s.tool] = s.end

    checks: list[DoctorCheck] = []
    for tools, grace, coarse in (
        (_COVERAGE_TOOLS, _COVERAGE_LAG_DAYS, False),
        (_COVERAGE_TOOLS_COARSE, _COVERAGE_LAG_DAYS_COARSE, True),
    ):
        for tool in tools:
            captured = last_end.get(tool)
            if captured is None:
                continue  # no baseline — never captured, not a regression
            disk = _newest_disk_activity(tool)
            if disk is None:
                continue
            lag_days = (disk - captured).total_seconds() / 86400
            if lag_days <= grace:
                continue
            if coarse:
                # Coarse storage-mtime signal: name the uncertainty honestly.
                detail = (
                    f"last captured {captured:%Y-%m-%d %H:%M}, but {tool} storage was "
                    f"modified as recently as {disk:%Y-%m-%d %H:%M} (~{lag_days:.0f}d) — "
                    f"if you used its AI features the hook may not be firing "
                    f"(best-effort signal; ignore if you only browsed code)"
                )
            else:
                detail = (
                    f"last captured {captured:%Y-%m-%d %H:%M}, but {tool} session "
                    f"files are as recent as {disk:%Y-%m-%d %H:%M} "
                    f"(~{lag_days:.0f}d uncaptured) — collector may be broken"
                )
            checks.append(
                DoctorCheck(
                    id=f"coverage.{tool}",
                    label=f"{tool} (capture lagging)",
                    status="warning",
                    detail=detail,
                    fix=_COVERAGE_FIX.get(tool),
                )
            )
    return checks


def _integrity_check(
    home_state: Path, project_dir: Path | None, hub_dir: Path | None
) -> DoctorCheck:
    """Report the active state-integrity mode and verify tracked files."""
    from halyard.state_integrity import (
        IntegrityError,
        current_mode,
        detect_sidecar_mode,
        read_trusted_state,
    )

    mode = current_mode(project_dir or hub_dir)
    tracked = [home_state / "active", home_state / "hub"]
    for path in tracked:
        sidecar_mode = detect_sidecar_mode(path)
        if sidecar_mode == "hmac" or (sidecar_mode == "hash" and mode == "off"):
            mode = sidecar_mode

    if mode == "off":
        return DoctorCheck(
            id="state.integrity",
            label="Integrity",
            status="skipped",
            detail="mode=off (opt-in via halyard.toml state_integrity)",
        )

    for path in tracked:
        if not path.exists():
            continue
        try:
            read_trusted_state(path, mode=mode)
        except (IntegrityError, OSError):
            return DoctorCheck(
                id="state.integrity",
                label="Integrity",
                status="warning",
                detail=f"mode={mode} — verification failed at {path}",
                fix="inspect the tampered file or re-write via halyard CLI",
            )

    if mode == "hash":
        return DoctorCheck(
            id="state.integrity",
            label="Integrity",
            status="ok",
            detail="mode=hash — corruption detection only, NOT "
            'tamper-resistant; set state_integrity="hmac" for '
            "authenticated integrity",
        )
    return DoctorCheck(
        id="state.integrity",
        label="Integrity",
        status="ok",
        detail=f"mode={mode} — all tracked sidecars verify",
    )


def _collector_state_checks(project_dir: Path | None, hub_dir: Path | None) -> list[DoctorCheck]:
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
        fix_lines = ["map each remote (edit the slug, then run):"]
        for remote, count in sorted(groups.items(), key=lambda x: -x[1]):
            n = f"{count} session{'s' if count != 1 else ''}"
            fix_lines.append(f"          {_link_repo_command(remote)}  # {n}")
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

    checks.append(_integrity_check(home_state, project_dir, hub_dir))

    # Single-file state collectors
    for name, filename in (
        ("Gemini state", "gc-session"),
        ("Cursor state", "cursor-session"),
    ):
        path = home_state / filename
        checks.append(
            DoctorCheck(
                id=f"state.{filename}",
                label=name,
                status="ok" if path.exists() else "skipped",
                detail=_age_detail(path) if path.exists() else "none",
            )
        )

    # Directory-based state collectors
    ws_dir = home_state / "ws-sessions"
    ws_count = len(list(ws_dir.glob("*.json"))) if ws_dir.exists() else 0
    checks.append(
        DoctorCheck(
            id="state.windsurf",
            label="Windsurf state",
            status="ok" if ws_count else "skipped",
            detail=f"{ws_count} active trajectory/ies" if ws_count else "none",
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


def _commands_from_windsurf_settings(path: Path) -> list[str]:
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
