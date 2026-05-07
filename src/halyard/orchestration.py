"""Interactive and multi-step CLI workflows."""

from __future__ import annotations

import subprocess
import tomllib
from dataclasses import replace
from pathlib import Path

import typer
from rich.console import Console

from halyard.ai_log import (
    AI_LOG_FILENAME,
    AiSession,
    append_session,
    assign_unattributed_sessions,
    confirm_session_attributions,
    find_project_dir,
    unattributed_log_path,
)
from halyard.hub import find_hub, set_hub

console = Console()

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
prefix = "{{{{year}}}}-{{{{month:02d}}}}-{{{{client_slug}}}}"
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
"""

_GITIGNORE = """\
# Halyard
.halyard-cache/
.DS_Store

# Uncomment the line below to keep generated PDFs out of version control.
# invoices/*.pdf
"""


def scaffold_project(target_dir: Path, hub: bool = False) -> None:
    """Create the full Halyard project layout in target_dir."""
    config_file = target_dir / "halyard.toml"

    if config_file.exists():
        console.print(
            "[bold red]Error:[/] [bold]halyard.toml[/] already exists here.\n"
            "Remove or move it before re-initializing."
        )
        raise typer.Exit(code=1)

    business_name = _detect_business_name()
    halyard_toml = _HALYARD_TOML_TEMPLATE.format(business_name=business_name)
    config_file.write_text(halyard_toml)
    (target_dir / "clients.toml").write_text(_CLIENTS_TOML)
    (target_dir / "projects.toml").write_text(_PROJECTS_TOML)
    (target_dir / "time.timeclock").write_text(_TIMECLOCK)
    (target_dir / "ai-sessions.log").write_text(_AI_SESSIONS_LOG)
    (target_dir / "ai-plans.toml").write_text(_AI_PLANS_TOML)
    (target_dir / "invoices").mkdir(exist_ok=True)
    _ensure_gitignore(target_dir / ".gitignore")

    if hub:
        set_hub(target_dir)

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
    console.print("\nTrack time: halyard start/stop   |   View AI spend: halyard report")


def interactive_assign_unattributed(
    explicit_project: str | None = None,
) -> None:
    """Interactive loop to assign or discard unattributed AI sessions."""
    global_log = unattributed_log_path()
    if global_log.exists() and any(
        line.strip().startswith("s ") for line in global_log.read_text().splitlines()
    ):
        remaining = global_log.read_text().splitlines()
        assigned = 0
        hubbed = 0
        discarded = 0
        skipped = 0

        for line in list(remaining):
            if not line.strip().startswith("s "):
                continue
            session = AiSession.from_log_line(line)
            if session is None:
                skipped += 1
                continue

            console.print(
                "\n[bold]Unattributed session[/]\n"
                f"  {session.start:%Y-%m-%d %H:%M} → {session.end:%H:%M}\n"
                f"  {session.tool} / {session.model}  ${session.cost_usd:.4f}\n"
                f"  tags: {', '.join(session.tags) if session.tags else '(none)'}"
            )

            choice = (
                "a"
                if explicit_project
                else typer.prompt("[a]ssign / [h]ub / [d]iscard / [s]kip", default="s")
                .strip()
                .lower()[:1]
            )

            if choice == "a":
                target_project = explicit_project or typer.prompt("Project slug").strip()
                target_dir = find_project_dir() or find_hub()
                if target_dir is None:
                    console.print("[bold red]No current project or hub found.[/] Skipping session.")
                    skipped += 1
                    continue

                if not _is_valid_project(target_project, target_dir):
                    console.print(
                        f"[bold red]Error:[/] Project '[bold]{target_project}[/]' not found "
                        f"in {target_dir / 'projects.toml'}."
                    )
                    skipped += 1
                    continue

                append_session(target_dir, replace(session, project=target_project))
                remaining.remove(line)
                _rewrite_lines_atomic(global_log, remaining)
                assigned += 1
            elif choice == "h":
                hub_dir = find_hub()
                if hub_dir is None:
                    console.print("[bold red]No hub configured.[/] Skipping session.")
                    skipped += 1
                    continue
                append_session(hub_dir, session)
                remaining.remove(line)
                _rewrite_lines_atomic(global_log, remaining)
                hubbed += 1
            elif choice == "d":
                if typer.confirm("Discard this session?", default=False):
                    remaining.remove(line)
                    _rewrite_lines_atomic(global_log, remaining)
                    discarded += 1
                else:
                    skipped += 1
            else:
                skipped += 1

        console.print(
            f"\n[bold green]Done.[/] {assigned} assigned, {hubbed} moved to hub, "
            f"{discarded} discarded, {skipped} skipped."
        )
        return

    project_dir = find_project_dir()
    if project_dir is None:
        console.print("[yellow]No unattributed sessions.[/]")
        return

    from halyard.reports import get_active_project

    target_project = explicit_project or get_active_project(project_dir)
    if not target_project:
        console.print(
            "[bold red]Error:[/] No project provided and no active timer. "
            "Use [bold]--project client:project[/]."
        )
        raise typer.Exit(code=1)

    if not _is_valid_project(target_project, project_dir):
        console.print(
            f"[bold red]Error:[/] Project '[bold]{target_project}[/]' not found "
            f"in {project_dir / 'projects.toml'}."
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


def interactive_confirm_attribution(project_dir: Path) -> None:
    """Review and confirm AI sessions with project attribution inferred from timeclock overlap."""
    from halyard.ledger import infer_project_attribution
    from halyard.reports import parse_timeclock

    log_path = project_dir / AI_LOG_FILENAME
    if not log_path.exists():
        console.print("[yellow]No ai-sessions.log found in this project.[/]")
        return

    tc_entries = parse_timeclock(project_dir / "time.timeclock")
    if not tc_entries:
        console.print(
            "[yellow]No timeclock entries found.[/] Attribution inference requires "
            "time.timeclock data. Run [bold]halyard start[/] to begin tracking time."
        )
        return

    raw_lines = log_path.read_text().splitlines()
    candidates: list[tuple[str, AiSession, str]] = []

    for raw_line in raw_lines:
        line = raw_line.rstrip()
        if not (line.startswith("s ") and " project=" not in line):
            continue
        session = AiSession.from_log_line(line)
        if session is None:
            continue
        inferred = infer_project_attribution(session, tc_entries)
        if inferred is not None:
            candidates.append((line, session, inferred))

    if not candidates:
        console.print("[green]No unattributed sessions with inferred attribution found.[/]")
        return

    console.print(f"\n[bold]{len(candidates)} session(s) with inferred attribution[/]\n")

    confirmations: list[tuple[str, str]] = []
    confirmed_count = rejected = skipped = 0

    for raw_line, session, inferred in candidates:
        duration = max(1, int((session.end - session.start).total_seconds() // 60))
        console.print(
            f"\n  {session.start:%Y-%m-%d %H:%M} → {session.end:%H:%M}  ({duration}m)\n"
            f"  {session.tool} / {session.model}  ${session.cost_usd:.4f}\n"
            f"  Inferred: [bold cyan]{inferred}[/]"
        )
        choice = typer.prompt("  [y]es / [n]o / [s]kip", default="s").strip().lower()[:1]
        if choice == "y":
            confirmations.append((raw_line, inferred))
            confirmed_count += 1
        elif choice == "n":
            rejected += 1
        else:
            skipped += 1

    if confirmations:
        count = confirm_session_attributions(project_dir, confirmations)
        console.print(f"\n[bold green]{count} session(s) attributed.[/]")
    else:
        console.print("\n[yellow]No attributions confirmed.[/]")

    parts = []
    if rejected:
        parts.append(f"{rejected} rejected")
    if skipped:
        parts.append(f"{skipped} skipped")
    if parts:
        console.print(f"  {', '.join(parts)}")


def _is_valid_project(slug: str, project_dir: Path) -> bool:
    """Return True if slug exists in projects.toml."""
    path = project_dir / "projects.toml"
    if not path.exists():
        return False
    try:
        data = tomllib.loads(path.read_text())
        for entry in data.get("project", []):
            if entry.get("slug") == slug:
                return True
    except Exception:
        pass
    return False


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


def _rewrite_lines_atomic(path: Path, lines: list[str]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    content = "\n".join(lines)
    tmp.write_text((content + "\n") if content else "")
    tmp.replace(path)
