"""Halyard CLI entry point."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

_HALYARD_ACTIVE = Path.home() / ".halyard" / "active"

# ---------------------------------------------------------------------------
# Helpers — time tracking
# ---------------------------------------------------------------------------


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_active() -> dict[str, str]:
    return dict(line.split("=", 1) for line in _HALYARD_ACTIVE.read_text().splitlines() if "=" in line)


def _elapsed_str(started: str, stopped: str) -> str:
    delta = datetime.strptime(stopped, "%Y-%m-%d %H:%M:%S") - datetime.strptime(started, "%Y-%m-%d %H:%M:%S")
    total_mins = int(delta.total_seconds() // 60)
    h, m = divmod(total_mins, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


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

_GITIGNORE = """\
# Halyard
.halyard-cache/
.DS_Store

# Uncomment the line below to keep generated PDFs out of version control.
# invoices/*.pdf
"""

# Claude Code hook config injected by `halyard install-hook`
_CC_HOOKS = {
    "UserPromptSubmit": [
        {"matcher": "", "hooks": [{"type": "command", "command": "halyard cc-session"}]}
    ],
    "Stop": [
        {"matcher": "", "hooks": [{"type": "command", "command": "halyard cc-hook"}]}
    ],
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
def init() -> None:
    """Scaffold a new Halyard project in the current directory."""
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
    (cwd / "invoices").mkdir(exist_ok=True)
    (cwd / ".gitignore").write_text(_GITIGNORE)

    console.print("[bold green]Halyard project initialized.[/]\n")
    console.print("Next steps:")
    console.print("  1. Edit [bold]halyard.toml[/] — confirm your business name and currency.")
    console.print("  2. Edit [bold]clients.toml[/] — add your first client with an hourly rate.")
    console.print("  3. Run [bold]halyard install-hook[/] — auto-capture AI sessions from Claude Code.")
    console.print("\nTrack time: halyard start/stop   |   View AI spend: halyard report")


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
        console.print("[bold red]Error:[/] Slug must be [bold]client/project[/], e.g. [bold]acme/auth-migration[/].")
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
            "[bold red]Error:[/] No active timer. Run [bold]halyard start <client/project>[/] first."
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

    console.print(f"[bold green]Stopped[/] [bold]{slug}[/]. Elapsed: {_elapsed_str(started, ts)}.")


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
# AI session collectors (task v1 2.1–2.3)
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


@app.command(name="install-hook")
def install_hook(
    global_: bool = typer.Option(False, "--global", help="Install into ~/.claude/settings.json instead of .claude/settings.json."),
) -> None:
    """Install Claude Code hooks to auto-capture AI sessions."""
    if global_:
        settings_path = Path.home() / ".claude" / "settings.json"
    else:
        settings_path = Path.cwd() / ".claude" / "settings.json"

    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}  # type: ignore[type-arg]
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, ValueError):
            existing = {}

    hooks = existing.setdefault("hooks", {})
    added: list[str] = []

    for event, entries in _CC_HOOKS.items():
        current = hooks.setdefault(event, [])
        command = entries[0]["hooks"][0]["command"]
        already = any(
            h.get("command") == command
            for entry in current
            for h in entry.get("hooks", [])
        )
        if not already:
            current.extend(entries)
            added.append(event)

    settings_path.write_text(json.dumps(existing, indent=2) + "\n")

    if added:
        console.print(f"[bold green]Hooks installed[/] in [bold]{settings_path}[/]")
        for event in added:
            console.print(f"  {event}")
    else:
        console.print(f"[yellow]Hooks already present[/] in [bold]{settings_path}[/] — nothing changed.")


# ---------------------------------------------------------------------------
# Reporting (task v1 3.1)
# ---------------------------------------------------------------------------


@app.command()
def report(
    all_time: bool = typer.Option(False, "--all", help="Show all time instead of current month."),
) -> None:
    """Show AI usage and cost summary."""
    from halyard.ai_log import find_project_dir, parse_sessions

    project_dir = find_project_dir()
    if project_dir is None:
        console.print("[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first.")
        raise typer.Exit(code=1)

    sessions = parse_sessions(project_dir)

    if not all_time:
        now = datetime.now()
        sessions = [s for s in sessions if s.start.year == now.year and s.start.month == now.month]

    if not sessions:
        period = "all time" if all_time else datetime.now().strftime("%B %Y")
        console.print(f"[yellow]No AI sessions recorded for {period}.[/]")
        console.print("Run [bold]halyard install-hook[/] to start capturing sessions automatically.")
        raise typer.Exit(code=0)

    total_cost = sum(s.cost_usd for s in sessions)
    total_input = sum(s.input_tokens for s in sessions)
    total_output = sum(s.output_tokens for s in sessions)

    by_project: dict[str, list[float]] = {}
    for s in sessions:
        key = s.project or "(unattributed)"
        by_project.setdefault(key, []).append(s.cost_usd)

    by_model: dict[str, list[float]] = {}
    for s in sessions:
        by_model.setdefault(s.model, []).append(s.cost_usd)

    period_label = "All time" if all_time else datetime.now().strftime("%B %Y")
    console.print(f"\n[bold]AI Report — {period_label}[/]")
    console.print("─" * 48)
    console.print(f"  Sessions   [bold]{len(sessions)}[/]")
    console.print(f"  Cost       [bold green]${total_cost:.2f}[/]")
    if total_input:
        console.print(f"  Tokens     in {total_input:,}  out {total_output:,}")

    if by_project:
        console.print("\n[bold]By project[/]")
        for proj, costs in sorted(by_project.items(), key=lambda x: -sum(x[1])):
            console.print(f"  {proj:<32} [green]${sum(costs):.2f}[/]  {len(costs)} sessions")

    if by_model:
        console.print("\n[bold]By model[/]")
        for model, costs in sorted(by_model.items(), key=lambda x: -sum(x[1])):
            console.print(f"  {model:<32} [green]${sum(costs):.2f}[/]  {len(costs)} sessions")

    console.print("─" * 48 + "\n")


if __name__ == "__main__":
    app()
