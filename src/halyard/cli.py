"""Halyard CLI entry point."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

_HALYARD_ACTIVE = Path.home() / ".halyard" / "active"


def _halyard_exe() -> str:
    """Return the absolute path to the running halyard executable.

    Prefers the resolved sys.argv[0] so that hooks embed the exact binary that
    ran `install-*-hook`, rather than relying on PATH being set up correctly
    in the hook execution environment (e.g. Gemini CLI, Cursor, Claude Code).
    """
    candidate = Path(sys.argv[0]).resolve()
    if candidate.name in ("halyard", "halyard.exe") and candidate.exists():
        return str(candidate)
    found = shutil.which("halyard")
    if found:
        return str(Path(found).resolve())
    return "halyard"  # fallback: trust PATH at hook-run time


# ---------------------------------------------------------------------------
# Helpers — time tracking
# ---------------------------------------------------------------------------


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_active() -> dict[str, str]:
    return dict(
        line.split("=", 1) for line in _HALYARD_ACTIVE.read_text().splitlines() if "=" in line
    )


# ---------------------------------------------------------------------------
# Default file contents written by `halyard init`
# ---------------------------------------------------------------------------

_HALYARD_TOML_TEMPLATE = """\
[business]
name = "{business_name}"
currency = "USD"
default_due_days = 30

[invoicing]
counter = 0
prefix = "{{year}}-{{month:02d}}-{{client_slug}}"
"""

_CLIENTS_TOML = """\
# Add your clients here — one [[client]] block per client.
#
# [[client]]
# slug = "acme"            # required; lowercase letters, digits, hyphens
# name = "Acme Corp"       # required; display name on invoices
# hourly_rate = 150        # required; numeric, in the project currency
# email = "ap@acme.com"    # optional
# address = \"\"\"           # optional; multi-line OK
# 123 Main St
# Anytown, ST 12345
# \"\"\"
"""

_PROJECTS_TOML = """\
# Add your projects here — one [[project]] block per project.
#
# [[project]]
# slug = "auth-migration"   # required; scoped under the client
# client_slug = "acme"      # required; must match a slug in clients.toml
# name = "Auth migration"   # required; display name on invoices
# hourly_rate = 175         # optional; overrides the client rate for this project
"""

_TIMECLOCK = """\
; Halyard timeclock — hledger-compatible
; i YYYY-MM-DD HH:MM:SS client:project  optional comment
; o YYYY-MM-DD HH:MM:SS
"""

_AI_SESSIONS_LOG = """\
; Halyard AI session log — spec: https://halyard.dev/spec/ai-sessions/v1
; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd> [key=value ...]
"""

_AI_PLANS_TOML = """\
# AI Plans — configure how Halyard tracks AI subscription and seat costs.
# Uncomment and fill in the blocks below for your active plans.
#
# [[plan]]
# slug = "claude-max"            # unique name for this plan
# tool = "claude-code"           # tool slug: claude-code, cursor, copilot, ...
# billing = "seat"               # seat | api | credits
# monthly_usd = 200              # cost per month in USD
# allocation = "active_minutes"  # active_minutes | session_count | manual
# starts_on = "2026-01-01"       # ISO date when plan began
#
# [[plan]]
# slug = "cursor-pro"
# tool = "cursor"
# billing = "credits"
# monthly_usd = 20
# included_credits = 500
# credit_to_usd = 0.04           # USD per credit (monthly_usd / included_credits)
# allocation = "credits"
# starts_on = "2026-01-01"
#
# [[plan]]
# slug = "anthropic-api"
# tool = "claude-api"
# billing = "api"
# allocation = "direct"          # uses cost_usd captured in ai-sessions.log
"""

_GITIGNORE = """\
# Halyard
.halyard-cache/
.DS_Store

# Uncomment the line below to keep generated PDFs out of version control.
# invoices/*.pdf
"""

# Claude Code hook config injected by `halyard install-hook`
_CC_HOOKS: dict[str, list[dict[str, Any]]] = {
    "UserPromptSubmit": [
        {"matcher": "", "hooks": [{"type": "command", "command": "halyard cc-session"}]}
    ],
    "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "halyard cc-hook"}]}],
}

# Gemini CLI hook config injected by `halyard install-gemini-hook`
_GC_HOOKS: dict[str, str] = {
    "SessionStart": "halyard gc-session",
    "AfterModel": "halyard gc-model",
    "AfterAgent": "halyard gc-hook",
}

# Cursor hook config injected by `halyard install-cursor-hook`
_CURSOR_HOOKS: dict[str, str] = {
    "beforeSubmitPrompt": "halyard cursor-session",
    "stop": "halyard cursor-hook",
}


def _detect_business_name() -> str:
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        name = result.stdout.strip()
        if name:
            return f"{name} Consulting"
    except Exception:
        pass
    return "Your Name Consulting"


def _ensure_gitignore(path: Path) -> None:
    """Create or append the Halyard .gitignore block without removing user rules."""
    if not path.exists():
        path.write_text(_GITIGNORE)
        return

    existing = path.read_text()
    existing_lines = set(existing.splitlines())
    missing_lines = [
        line for line in _GITIGNORE.splitlines() if line and line not in existing_lines
    ]

    if not missing_lines:
        return

    separator = "\n" if existing.endswith("\n") else "\n\n"
    path.write_text(existing + separator + "\n".join(missing_lines) + "\n")


def _active_project_for(project_dir: Path) -> str | None:
    """Return active project only when the active timer belongs to project_dir."""
    from halyard.reports import read_active_timer

    active = read_active_timer()
    if active is None or active.timeclock is None:
        return None
    try:
        active.timeclock.resolve().relative_to(project_dir.resolve())
    except ValueError:
        return None
    return active.slug


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="halyard",
    help="AI work intelligence infrastructure. Plain text. Owned by you.",
    no_args_is_help=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()


@app.callback(invoke_without_command=True)
def default(ctx: typer.Context) -> None:
    """Drop into the interactive Claude REPL when invoked with no subcommand."""
    if ctx.invoked_subcommand is None:
        console.print(
            "[bold cyan]Halyard[/] — interactive REPL not yet implemented "
            "(see openspec/changes/v0-time-and-invoice/tasks.md task 5.4)."
        )
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------


@app.command()
def init(
    hub: bool = typer.Option(
        False, "--hub", help="Also designate this directory as the global hub for all tools."
    ),
) -> None:
    """Scaffold a new Halyard project in the current directory."""
    from halyard.hub import set_hub

    cwd = Path.cwd()
    config_file = cwd / "halyard.toml"

    if config_file.exists():
        console.print(
            "[bold red]Error:[/] [bold]halyard.toml[/] already exists here.\n"
            "Remove or move it before re-initializing."
        )
        raise typer.Exit(code=1)

    halyard_toml = _HALYARD_TOML_TEMPLATE.format(business_name=_detect_business_name())
    config_file.write_text(halyard_toml)
    (cwd / "clients.toml").write_text(_CLIENTS_TOML)
    (cwd / "projects.toml").write_text(_PROJECTS_TOML)
    (cwd / "time.timeclock").write_text(_TIMECLOCK)
    (cwd / "ai-sessions.log").write_text(_AI_SESSIONS_LOG)
    (cwd / "ai-plans.toml").write_text(_AI_PLANS_TOML)
    (cwd / "invoices").mkdir(exist_ok=True)
    _ensure_gitignore(cwd / ".gitignore")

    if hub:
        set_hub(cwd)

    console.print("[bold green]Halyard project initialized.[/]\n")
    if hub:
        console.print("[bold cyan]Hub set.[/] Sessions from all tools will land here by default.")
        console.print()
    console.print("Next steps:")
    console.print("  1. Edit [bold]halyard.toml[/] — confirm your business name and currency.")
    console.print("  2. Edit [bold]clients.toml[/] — add your first client with an hourly rate.")
    console.print(
        "  3. Run [bold]halyard install-hook[/] — auto-capture AI sessions from Claude Code."
    )
    console.print("\nTrack time: halyard in/out   |   View AI spend: halyard report")


@app.command()
def hub(
    set_path: str | None = typer.Argument(
        None, metavar="PATH", help="Set hub to this directory (must contain halyard.toml)."
    ),
) -> None:
    """Show or set the global hub directory for cross-project session capture."""
    from halyard.hub import find_hub, set_hub

    if set_path is not None:
        target = Path(set_path).resolve()
        if not (target / "halyard.toml").exists():
            console.print(
                f"[bold red]Error:[/] {target} has no halyard.toml —"
                " run [bold]halyard init[/] there first."
            )
            raise typer.Exit(code=1)
        set_hub(target)
        console.print(f"[bold green]Hub set[/] → [bold]{target}[/]")
        return

    hub_dir = find_hub()
    if hub_dir is None:
        console.print(
            "[yellow]No hub configured.[/]\n"
            "Sessions outside any halyard.toml directory are currently dropped.\n\n"
            "To fix: [bold]halyard init --hub[/] in a central directory, or\n"
            "        [bold]halyard hub <path>[/] to point at an existing project."
        )
    else:
        log_path = hub_dir / "ai-sessions.log"
        lines = (
            sum(1 for ln in log_path.read_text().splitlines() if ln.startswith("s "))
            if log_path.exists()
            else 0
        )
        console.print(f"[bold cyan]Hub[/] → [bold]{hub_dir}[/]  ({lines} sessions)")


@app.command(name="link-repo")
def link_repo(
    project: str = typer.Argument(..., help="Project slug (client:project) to map this repo to."),
    remote: str | None = typer.Option(
        None, "--remote", help="Remote URL/pattern to map. Defaults to current repo's origin."
    ),
) -> None:
    """Map the current git repo's remote to a project slug for automatic attribution."""
    from halyard.git_context import current_remote, register_repo

    if remote is None:
        remote = current_remote()
        if remote is None:
            console.print(
                "[bold red]Error:[/] Not in a git repo with an origin remote.\n"
                "Pass --remote explicitly or run from inside a git repository."
            )
            raise typer.Exit(code=1)

    register_repo(remote, project)
    console.print(f"[bold green]Linked[/] [dim]{remote}[/] → [bold]{project}[/]")
    console.print("Future sessions from this repo will be attributed automatically.")


# ---------------------------------------------------------------------------
# Time tracking (task 3.1)
# ---------------------------------------------------------------------------


@app.command()
def log(
    message: str = typer.Argument(..., help="Natural-language description of work."),
) -> None:
    """Log time from a free-form description (calls Claude to extract the entry)."""
    raise NotImplementedError("v0 task 3.2")


@app.command()
def start(
    slug: str = typer.Argument(..., help="client/project slug, e.g. acme/auth-migration"),
) -> None:
    """Start the active timer."""
    if _HALYARD_ACTIVE.exists():
        active = _parse_active()
        console.print(
            f"[bold red]Error:[/] Timer already running for [bold]{active.get('slug', '?')}[/].\n"
            "Run [bold]halyard stop[/] first."
        )
        raise typer.Exit(code=1)

    timeclock = Path.cwd() / "time.timeclock"
    if not timeclock.exists():
        console.print(
            "[bold red]Error:[/] No [bold]time.timeclock[/] in the current directory.\n"
            "Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    if "/" not in slug or slug.startswith("/") or slug.endswith("/"):
        console.print(
            "[bold red]Error:[/] Slug must be [bold]client/project[/], "
            "e.g. [bold]acme/auth-migration[/]."
        )
        raise typer.Exit(code=1)

    account = slug.replace("/", ":", 1)
    ts = _now_str()

    with timeclock.open("a") as f:
        f.write(f"i {ts} {account}\n")

    _HALYARD_ACTIVE.parent.mkdir(parents=True, exist_ok=True)
    _HALYARD_ACTIVE.write_text(f"timeclock={timeclock}\nslug={account}\nstarted={ts}\n")

    console.print(f"[bold green]Started[/] [bold]{account}[/] at {ts}.")


@app.command()
def stop() -> None:
    """Stop the active timer."""
    if not _HALYARD_ACTIVE.exists():
        console.print(
            "[bold red]Error:[/] No active timer. Run "
            "[bold]halyard start <client/project>[/] first."
        )
        raise typer.Exit(code=1)

    active = _parse_active()
    timeclock = Path(active["timeclock"])
    slug = active["slug"]
    started = active["started"]
    ts = _now_str()

    with timeclock.open("a") as f:
        f.write(f"o {ts}\n")

    _HALYARD_ACTIVE.unlink()

    from halyard.reports import _elapsed_minutes, format_minutes

    elapsed = format_minutes(_elapsed_minutes(started, datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")))
    console.print(f"[bold green]Stopped[/] [bold]{slug}[/]. Elapsed: {elapsed}.")


@app.command()
def status() -> None:
    """Show the active timer, or report that none is running."""
    from halyard.reports import _elapsed_minutes, format_minutes

    if not _HALYARD_ACTIVE.exists():
        console.print(
            "[yellow]No active timer.[/] Start one with [bold]halyard start <project>[/]."
        )
        return

    active = _parse_active()
    slug = active.get("slug", "(unknown)")
    started = active.get("started", "")
    elapsed = format_minutes(_elapsed_minutes(started, datetime.now())) if started else "?"
    console.print(f"[bold cyan]{slug}[/]  {elapsed} elapsed  (started {started})")


# ---------------------------------------------------------------------------
# Invoicing
# ---------------------------------------------------------------------------


@app.command()
def invoice(
    client: str = typer.Argument(..., help="Client slug to invoice."),
    month: str | None = typer.Option(None, "--month", help="last | this | YYYY-MM"),
    from_: str | None = typer.Option(None, "--from", help="ISO date (inclusive lower bound)"),
    to: str | None = typer.Option(None, "--to", help="ISO date (inclusive upper bound)"),
) -> None:
    """Generate an invoice from logged time entries."""
    raise NotImplementedError("v0 task 4.2")


# ---------------------------------------------------------------------------
# AI session collectors (task v1 2.1-2.3)
# ---------------------------------------------------------------------------


@app.command(name="cc-session", hidden=True)
def cc_session() -> None:
    """Record Claude Code session start (called by UserPromptSubmit hook)."""
    from halyard.collectors.claude_code import record_session_start

    raise typer.Exit(code=record_session_start())


@app.command(name="cc-hook", hidden=True)
def cc_hook() -> None:
    """Process Claude Code Stop hook payload (called by Stop hook)."""
    from halyard.collectors.claude_code import handle_stop_hook

    raise typer.Exit(code=handle_stop_hook())


# ---------------------------------------------------------------------------
# Gemini CLI hooks
# ---------------------------------------------------------------------------


@app.command(name="gc-session", hidden=True)
def gc_session() -> None:
    """Record Gemini CLI session start (called by SessionStart hook)."""
    from halyard.collectors.gemini_cli import record_session_start

    raise typer.Exit(code=record_session_start())


@app.command(name="gc-model", hidden=True)
def gc_model() -> None:
    """Accumulate Gemini CLI token counts (called by AfterModel hook)."""
    from halyard.collectors.gemini_cli import record_model_usage

    raise typer.Exit(code=record_model_usage())


@app.command(name="gc-hook", hidden=True)
def gc_hook() -> None:
    """Finalise Gemini CLI session record (called by AfterAgent hook)."""
    from halyard.collectors.gemini_cli import handle_agent_stop

    raise typer.Exit(code=handle_agent_stop())


# ---------------------------------------------------------------------------
# Cursor hooks
# ---------------------------------------------------------------------------


@app.command(name="cursor-session", hidden=True)
def cursor_session() -> None:
    """Record Cursor session start (called by beforeSubmitPrompt hook)."""
    from halyard.collectors.cursor import record_session_start

    raise typer.Exit(code=record_session_start())


@app.command(name="cursor-hook", hidden=True)
def cursor_hook() -> None:
    """Process Cursor stop hook payload (called by stop hook)."""
    from halyard.collectors.cursor import handle_stop_hook

    raise typer.Exit(code=handle_stop_hook())


@app.command(name="install-hook")
def install_hook(
    global_: bool = typer.Option(
        False,
        "--global",
        help="Install into ~/.claude/settings.json instead of .claude/settings.json.",
    ),
) -> None:
    """Install Claude Code hooks to auto-capture AI sessions."""
    if global_:
        settings_path = Path.home() / ".claude" / "settings.json"
    else:
        settings_path = Path.cwd() / ".claude" / "settings.json"

    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, ValueError):
            existing = {}

    hooks = existing.setdefault("hooks", {})
    added: list[str] = []
    exe = _halyard_exe()

    for event, entries in _CC_HOOKS.items():
        # Substitute the resolved executable path into a deep copy of the config
        resolved = json.loads(json.dumps(entries).replace("halyard ", f"{exe} ", 1))
        current = hooks.setdefault(event, [])
        command = resolved[0]["hooks"][0]["command"]
        already = any(
            h.get("command") == command for entry in current for h in entry.get("hooks", [])
        )
        if not already:
            current.extend(resolved)
            added.append(event)

    settings_path.write_text(json.dumps(existing, indent=2) + "\n")

    if added:
        console.print(f"[bold green]Hooks installed[/] in [bold]{settings_path}[/]")
        for event in added:
            console.print(f"  {event}")
    else:
        console.print(
            f"[yellow]Hooks already present[/] in [bold]{settings_path}[/] — nothing changed."
        )


@app.command(name="install-gemini-hook")
def install_gemini_hook() -> None:
    """Install Gemini CLI hooks to auto-capture AI sessions."""
    settings_path = Path.home() / ".gemini" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, ValueError):
            existing = {}

    hooks = existing.setdefault("hooks", {})
    added: list[str] = []
    exe = _halyard_exe()

    for event, template in _GC_HOOKS.items():
        command = template.replace("halyard ", f"{exe} ", 1)
        current = hooks.setdefault(event, [])
        already = any(
            h.get("command") == command for entry in current for h in entry.get("hooks", [])
        )
        if not already:
            current.append(
                {
                    "matcher": "*",
                    "hooks": [{"name": "halyard", "type": "command", "command": command}],
                }
            )
            added.append(event)

    settings_path.write_text(json.dumps(existing, indent=2) + "\n")

    if added:
        console.print(f"[bold green]Hooks installed[/] in [bold]{settings_path}[/]")
        for event in added:
            console.print(f"  {event}")
    else:
        console.print(
            f"[yellow]Hooks already present[/] in [bold]{settings_path}[/] — nothing changed."
        )


@app.command(name="install-cursor-hook")
def install_cursor_hook() -> None:
    """Install Cursor hooks to auto-capture AI sessions."""
    settings_path = Path.home() / ".cursor" / "hooks.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, ValueError):
            existing = {}

    existing.setdefault("version", 1)
    hooks = existing.setdefault("hooks", {})
    added: list[str] = []
    exe = _halyard_exe()

    for event, template in _CURSOR_HOOKS.items():
        command = template.replace("halyard ", f"{exe} ", 1)
        current = hooks.setdefault(event, [])
        already = any(entry.get("command") == command for entry in current)
        if not already:
            current.append({"command": command})
            added.append(event)

    settings_path.write_text(json.dumps(existing, indent=2) + "\n")

    if added:
        console.print(f"[bold green]Hooks installed[/] in [bold]{settings_path}[/]")
        for event in added:
            console.print(f"  {event}")
    else:
        console.print(
            f"[yellow]Hooks already present[/] in [bold]{settings_path}[/] — nothing changed."
        )


@app.command(name="record-session")
def record_session(
    project: str | None = typer.Option(
        None,
        "--project",
        help="Project slug as client:project. Defaults to the active timer project.",
    ),
    tool: str = typer.Option("manual", "--tool", help="AI tool slug (e.g. claude-code, cursor)."),
    model: str = typer.Option("unspecified", "--model", help="Model label."),
    input_tokens: int = typer.Option(0, "--input-tokens", help="Input token count."),
    output_tokens: int = typer.Option(0, "--output-tokens", help="Output token count."),
    cost: float | None = typer.Option(None, "--cost", help="Explicit USD cost."),
    minutes: int = typer.Option(1, "--minutes", help="Session duration in minutes."),
    note: str | None = typer.Option(None, "--note", help="Short note, spaces are allowed."),
) -> None:
    """Append a manual/Codex AI session record to ai-sessions.log."""
    from halyard.ai_log import AiSession, append_session, find_project_dir
    from halyard.pricing import calculate_cost

    project_dir = find_project_dir()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    attributed_project = project or _active_project_for(project_dir)
    end = datetime.now()
    start_time = end - timedelta(minutes=max(0, minutes))
    session_cost = (
        cost
        if cost is not None
        else calculate_cost(model, input_tokens=input_tokens, output_tokens=output_tokens)
    )

    session = AiSession(
        start=start_time,
        end=end,
        tool=tool,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=session_cost,
        project=attributed_project,
        tokens_available=input_tokens > 0 or output_tokens > 0,
        source="manual",
        note=note,
    )
    append_session(project_dir, session)

    console.print(
        f"[bold green]Recorded[/] {tool} session"
        f" ({input_tokens:,} in / {output_tokens:,} out, ${session_cost:.4f})."
    )


@app.command(name="sample-session")
def sample_session(
    project: str | None = typer.Option(
        None,
        "--project",
        help="Project slug as client:project. Defaults to the active timer project.",
    ),
) -> None:
    """Append a realistic sample AI session for dashboard demos."""
    record_session(
        project=project,
        tool="claude-code",
        model="claude-sonnet-4-6",
        input_tokens=18_000,
        output_tokens=3_200,
        cost=None,
        minutes=6,
        note="dashboard sample",
    )


@app.command(name="assign-unattributed")
def assign_unattributed(
    project: str | None = typer.Option(
        None,
        "--project",
        help="Project slug as client:project. Defaults to the active timer project.",
    ),
) -> None:
    """Assign unattributed AI sessions to a project."""
    from halyard.ai_log import assign_unattributed_sessions, find_project_dir

    project_dir = find_project_dir()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    target_project = project or _active_project_for(project_dir)
    if not target_project:
        console.print(
            "[bold red]Error:[/] No project provided and no active timer. "
            "Use [bold]--project client:project[/]."
        )
        raise typer.Exit(code=1)

    changed = assign_unattributed_sessions(project_dir, target_project)
    if changed:
        console.print(
            f"[bold green]Assigned[/] {changed} unattributed session(s) to "
            f"[bold]{target_project}[/]."
        )
    else:
        console.print("[yellow]No unattributed sessions found.[/]")


# ---------------------------------------------------------------------------
# Codex importer
# ---------------------------------------------------------------------------


@app.command(name="import-codex")
def import_codex(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be imported without writing anything."
    ),
    all_projects: bool = typer.Option(
        False,
        "--all",
        help="Import sessions for all Halyard projects, not just the current one.",
    ),
) -> None:
    """Import Codex Desktop session history into ai-sessions.log."""
    from halyard.ai_log import find_project_dir
    from halyard.collectors.codex_app import import_codex_sessions

    project_dir = find_project_dir()
    if project_dir is None and not all_projects:
        console.print(
            "[bold red]Error:[/] No Halyard project found. "
            "Run [bold]halyard init[/] first or use [bold]--all[/]."
        )
        raise typer.Exit(code=1)

    sessions = import_codex_sessions(
        project_dir=project_dir,
        dry_run=dry_run,
        all_projects=all_projects,
    )

    if not sessions:
        console.print("[yellow]No new Codex sessions to import.[/]")
        return

    label = "[dim](dry run)[/dim] " if dry_run else ""
    console.print(f"{label}[bold green]Imported[/] {len(sessions)} Codex session(s).")
    for s in sessions:
        proj = s.project or "(unattributed)"
        console.print(
            f"  {s.start:%Y-%m-%d %H:%M} → {s.end:%H:%M}  "
            f"[cyan]{s.model}[/]  in={s.input_tokens} out={s.output_tokens}  "
            f"[dim]{proj}[/dim]"
        )


# ---------------------------------------------------------------------------
# Gemini history importer (v2.3)
# ---------------------------------------------------------------------------


@app.command(name="import-gemini")
def import_gemini(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be imported without writing anything."
    ),
    all_projects: bool = typer.Option(
        False,
        "--all",
        help="Import sessions for all Gemini project slugs, not just the current one.",
    ),
) -> None:
    """Import Gemini CLI session history into ai-sessions.log."""
    from halyard.ai_log import (
        AI_LOG_FILENAME,
        AiSession,
        append_session,
        find_project_dir,
        parse_sessions,
    )
    from halyard.collectors.gemini_history import (
        find_all_session_files,
        parse_session_file,
        project_dir_for_slug,
    )
    from halyard.hub import find_hub

    # Collect candidate session files
    if all_projects:
        session_files = find_all_session_files()
    else:
        cwd = Path.cwd()
        project_dir = find_project_dir(start=cwd)
        # Derive the Gemini slug from the project dir by scanning .project_root files
        from halyard.collectors.gemini_history import _GEMINI_HISTORY, _GEMINI_TMP

        session_files = []
        if project_dir:
            # Find slugs whose .project_root matches this dir
            for slug_dir in _GEMINI_HISTORY.glob("*"):
                pr = slug_dir / ".project_root"
                if pr.exists():
                    try:
                        if Path(pr.read_text().strip()).resolve() == project_dir.resolve():
                            session_files.extend(
                                (_GEMINI_TMP / slug_dir.name / "chats").glob("session-*.json")
                            )
                    except Exception:
                        pass
        if not session_files:
            # Fallback: all files
            session_files = find_all_session_files()

    if not session_files:
        console.print("[yellow]No Gemini session files found.[/]")
        return

    # Build set of already-imported session IDs across all known logs
    imported_ids: set[str] = set()
    hub = find_hub()
    for candidate_dir in filter(None, [find_project_dir(), hub]):
        log_path = candidate_dir / AI_LOG_FILENAME
        if log_path.exists():
            for s in parse_sessions(candidate_dir):
                if s.job_id and s.job_id.startswith("gemini:"):
                    imported_ids.add(s.job_id[len("gemini:"):])

    imported: list[AiSession] = []
    skipped = 0

    for path in sorted(session_files):
        summary = parse_session_file(path)
        if summary is None:
            continue
        if summary.session_id in imported_ids:
            skipped += 1
            continue

        # Determine target log directory
        slug = path.parent.parent.name  # ~/gemini/tmp/{slug}/chats/session-*.json
        pd = project_dir_for_slug(slug)
        target_dir = pd if pd and (pd / "halyard.toml").exists() else hub

        if target_dir is None:
            console.print(
                f"  [dim]skip {summary.session_id[:8]} — no project dir or hub[/dim]"
            )
            continue

        tags: list[str] = []
        if summary.total_tool_calls:
            tags.append(f"tools:{summary.total_tool_calls}")
        if summary.total_tool_errors:
            tags.append(f"tool_errors:{summary.total_tool_errors}")

        session = AiSession(
            start=summary.start,
            end=summary.end,
            tool="gemini-cli",
            model=summary.dominant_model or "gemini-unknown",
            input_tokens=summary.total_input,
            output_tokens=summary.total_output,
            cost_usd=summary.cost_usd,
            cache_read=summary.total_cache or None,
            tokens_available=summary.total_input > 0 or summary.total_output > 0,
            billing="api",
            source="import",
            job_id=f"gemini:{summary.session_id}",
            tags=tags,
        )
        imported.append(session)

        proj = slug
        label = "[dim](dry run)[/dim] " if dry_run else ""
        console.print(
            f"  {label}{session.start:%Y-%m-%d %H:%M}  "
            f"[cyan]{session.model}[/]  "
            f"in={session.input_tokens:,} out={session.output_tokens:,}  "
            f"${session.cost_usd:.4f}  [dim]{proj}[/dim]"
        )

        if not dry_run:
            append_session(target_dir, session)
            imported_ids.add(summary.session_id)

    if not imported:
        console.print("[yellow]No new Gemini sessions to import.[/]")
        return

    label = "[dim](dry run)[/dim] " if dry_run else ""
    console.print(
        f"\n{label}[bold green]{'Would import' if dry_run else 'Imported'}[/] "
        f"{len(imported)} Gemini session(s). "
        f"({skipped} already imported, skipped.)"
    )


# ---------------------------------------------------------------------------
# Reporting (task v1 3.1)
# ---------------------------------------------------------------------------


@app.command()
def report(
    all_time: bool = typer.Option(False, "--all", help="Show all time instead of current month."),
    project: str | None = typer.Option(
        None, "--project", help="Filter to a project slug (client:project)."
    ),
    client: str | None = typer.Option(
        None, "--client", help="Filter to all projects for a client."
    ),
    month: str | None = typer.Option(
        None, "--month", help="Billing month as YYYY-MM. Defaults to current month."
    ),
    ledger: bool = typer.Option(
        False, "--ledger", help="Include allocated seat/credits costs from ai-plans.toml."
    ),
) -> None:
    """Show AI usage, cost, and human time summary."""
    from datetime import datetime

    from halyard.ai_log import find_project_dir
    from halyard.pricing import pricing_table_age_days
    from halyard.reports import build_ai_report, build_human_time_report, format_minutes

    project_dir = find_project_dir()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    # Staleness warning for pricing table
    age = pricing_table_age_days()
    if age is None or age >= 30:
        if age is None:
            console.print(
                "[yellow]⚠  No local pricing table found.[/] "
                "Run [bold]halyard update-pricing[/] to fetch current model prices."
            )
        else:
            console.print(
                f"[yellow]⚠  Pricing table last updated {age} days ago.[/] "
                "Run [bold]halyard update-pricing[/] to refresh."
            )

    # Resolve billing period
    now = datetime.now()
    if month:
        try:
            period = datetime.strptime(month, "%Y-%m")
        except ValueError:
            console.print("[bold red]Error:[/] --month must be YYYY-MM (e.g. 2026-05).")
            raise typer.Exit(code=1) from None
    else:
        period = now

    report_data = build_ai_report(project_dir, all_time=all_time, now=period)
    human = build_human_time_report(project_dir, now=period)

    # Apply project / client filters
    filter_slug = project
    filter_client = client
    if filter_slug:
        report_data_sessions = [s for s in report_data.sessions if s.project == filter_slug]
    elif filter_client:
        report_data_sessions = [
            s for s in report_data.sessions if (s.project or "").startswith(f"{filter_client}:")
        ]
    else:
        report_data_sessions = report_data.sessions

    period_label = "All time" if all_time else period.strftime("%B %Y")
    filter_label = f" — {filter_slug or filter_client}" if (filter_slug or filter_client) else ""
    console.print(f"\n[bold]Report — {period_label}{filter_label}[/]")
    console.print("─" * 48)

    if human.month_minutes:
        console.print(
            f"  Human time [bold cyan]{format_minutes(human.month_minutes)}[/]  this month"
            f"  (today: {format_minutes(human.today_minutes)})"
        )

    if not report_data_sessions:
        console.print(f"  [yellow]No AI sessions recorded for {period_label}.[/]")
        console.print(
            "\n  Run [bold]halyard install-hook[/] to start capturing sessions automatically."
        )
        console.print("─" * 48 + "\n")
        raise typer.Exit(code=0)

    total_cost = sum(s.cost_usd for s in report_data_sessions)
    total_input = sum(s.input_tokens for s in report_data_sessions)
    total_output = sum(s.output_tokens for s in report_data_sessions)
    console.print(f"  AI sessions  [bold]{len(report_data_sessions)}[/]")
    console.print(f"  AI cost      [bold green]${total_cost:.2f}[/]")
    if total_input:
        console.print(f"  Tokens       in {total_input:,}  out {total_output:,}")

    if not filter_slug and report_data.by_project:
        console.print("\n[bold]By project[/]")
        for bucket in report_data.by_project:
            console.print(
                f"  {bucket.label:<32} [green]${bucket.cost_usd:.2f}[/]  {bucket.sessions} sessions"
            )

    if report_data.by_model:
        console.print("\n[bold]By model[/]")
        for bucket in report_data.by_model:
            console.print(
                f"  {bucket.label:<32} [green]${bucket.cost_usd:.2f}[/]  {bucket.sessions} sessions"
            )

    if human.by_project:
        console.print("\n[bold]Human time by project[/]")
        for time_bucket in human.by_project:
            mins = format_minutes(time_bucket.minutes)
            console.print(f"  {time_bucket.label:<32} [cyan]{mins}[/]")

    if ledger:
        from halyard.ai_plans import read_ai_plans
        from halyard.ledger import build_ledger
        from halyard.reports import parse_timeclock

        plans = read_ai_plans(project_dir)
        if plans:
            tc_entries = parse_timeclock(project_dir / "time.timeclock")
            summary = build_ledger(
                report_data.sessions, plans, tc_entries, year=period.year, month=period.month
            )
            console.print(f"\n[bold]AI Work Ledger — {summary.period_label}[/]")
            console.print(
                f"  Direct API  [green]${summary.total_direct_usd:.2f}[/]  "
                f"Allocated  [yellow]${summary.total_allocated_usd:.2f}[/]  "
                f"Total  [bold green]${summary.total_usd:.2f}[/]"
            )
            for entry in summary.entries:
                trust_color = "yellow" if entry.trust in ("allocated", "mixed") else "green"
                inferred_note = " [dim](inferred)[/]" if entry.has_inferred_attribution else ""
                console.print(
                    f"  {entry.project:<32} "
                    f"[{trust_color}]${entry.total_usd:.2f}[/]  "
                    f"{entry.sessions} sessions  "
                    f"[dim]{entry.trust}[/]{inferred_note}"
                )
        else:
            console.print(
                "\n[dim]No ai-plans.toml configured. Add plans to see seat/credits allocation.[/]"
            )

    console.print("─" * 48 + "\n")


@app.command()
def dashboard(
    port: int = typer.Option(0, "--port", help="Local port. 0 picks an available port."),
    open_: bool = typer.Option(False, "--open", help="Open the dashboard in a browser."),
) -> None:
    """Start the local Halyard Glass Cockpit dashboard."""
    from halyard.ai_log import find_project_dir
    from halyard.dashboard import run_dashboard

    project_dir = find_project_dir()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    run_dashboard(project_dir, port=port, open_browser=open_)


# ---------------------------------------------------------------------------
# Pricing sync (v2.1)
# ---------------------------------------------------------------------------


@app.command(name="update-pricing")
def update_pricing_cmd() -> None:
    """Fetch the latest model pricing table from GitHub and save locally."""
    from halyard.pricing import PricingFetchError, update_pricing

    console.print("Fetching pricing table from github.com/Kormiloio/Halyard...")
    try:
        new_count, updated_count = update_pricing()
    except PricingFetchError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        console.print("[dim]Bundled pricing table is still active.[/]")
        raise typer.Exit(code=1) from None

    parts = []
    if new_count:
        parts.append(f"{new_count} model{'s' if new_count != 1 else ''} added")
    if updated_count:
        parts.append(f"{updated_count} price{'s' if updated_count != 1 else ''} changed")
    summary = ", ".join(parts) if parts else "no changes"
    console.print(f"Updated: {summary}.")
    console.print("Pricing table saved to [bold]~/.halyard/pricing.toml[/].")


# ---------------------------------------------------------------------------
# Budget limits (v2.2)
# ---------------------------------------------------------------------------


@app.command()
def budget() -> None:
    """Show current AI spend vs. configured budget limits for all projects."""
    from datetime import datetime

    from halyard.budget import budget_status, load_budgets

    budgets = load_budgets()
    if not budgets:
        console.print(
            "[yellow]No budgets configured.[/] "
            "Create [bold]~/.halyard/budgets.toml[/] to set limits:\n"
        )
        console.print('  [dim][["acme:auth-migration"]][/dim]')
        console.print("  [dim]daily_usd   = 50.00[/dim]")
        console.print("  [dim]monthly_usd = 500.00[/dim]")
        console.print("\nOr use [bold]halyard set-budget <project> --daily N --monthly N[/].")
        return

    now = datetime.now()
    statuses = budget_status(now=now)

    console.print(f"\n[bold]Budget status — {now:%B %Y}[/]")
    console.print("─" * 52)
    for s in statuses:
        console.print(f"  [bold cyan]{s.slug}[/]")
        # Today
        if s.today_limit is not None:
            over = s.today_spend > s.today_limit
            mark = "  [bold yellow]⚠ over[/]" if over else "  [green]✓[/]"
            pct = f" {s.today_spend / s.today_limit * 100:.0f}% used" if not over else ""
            console.print(
                f"    Today      ${s.today_spend:.2f} / ${s.today_limit:.2f}{mark}{pct}"
            )
        else:
            console.print(f"    Today      ${s.today_spend:.2f}  [dim](no limit)[/dim]")
        # This month
        if s.month_limit is not None:
            over = s.month_spend > s.month_limit
            mark = "  [bold yellow]⚠ over[/]" if over else "  [green]✓[/]"
            pct = f" {s.month_spend / s.month_limit * 100:.0f}% used" if not over else ""
            console.print(
                f"    This month ${s.month_spend:.2f} / ${s.month_limit:.2f}{mark}{pct}"
            )
        else:
            console.print(f"    This month ${s.month_spend:.2f}  [dim](no limit)[/dim]")
        console.print()
    console.print("─" * 52)


@app.command(name="set-budget")
def set_budget_cmd(
    slug: str = typer.Argument(..., help="Project slug (e.g. acme:auth-migration)."),
    daily: float | None = typer.Option(None, "--daily", help="Daily spend limit in USD."),
    monthly: float | None = typer.Option(None, "--monthly", help="Monthly spend limit in USD."),
) -> None:
    """Add or update a budget limit for a project."""
    from halyard.budget import set_budget

    if daily is None and monthly is None:
        console.print("[bold red]Error:[/] Provide at least one of --daily or --monthly.")
        raise typer.Exit(code=1)

    result = set_budget(slug, daily_usd=daily, monthly_usd=monthly)

    parts = []
    if result.daily_usd is not None:
        parts.append(f"daily ${result.daily_usd:.2f}")
    if result.monthly_usd is not None:
        parts.append(f"monthly ${result.monthly_usd:.2f}")
    console.print(f"Budget set for [bold cyan]{slug}[/]: {' '.join(parts)}")


if __name__ == "__main__":
    app()
