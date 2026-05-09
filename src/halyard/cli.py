"""Halyard CLI entry point."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import typer
from rich.console import Console
from rich.markup import escape


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
    """Drop into the interactive REPL when invoked with no subcommand."""
    if ctx.invoked_subcommand is None:
        from halyard.ai_log import find_project_dir
        from halyard.repl import run_repl

        project_dir = find_project_dir()
        if project_dir is None:
            console.print(
                "[bold red]Error:[/] No Halyard project found. "
                "Run [bold]halyard init[/] to create one."
            )
            raise typer.Exit(code=1)

        run_repl(project_dir)


# ---------------------------------------------------------------------------
# Hook auto-detection
# ---------------------------------------------------------------------------


def _auto_install_detected_hooks() -> None:
    """Detect installed AI tools on PATH and auto-install their Halyard hooks."""
    found: list[str] = []
    not_found: list[str] = []

    for binary, label, installer in [
        ("claude", "Claude Code", lambda: _do_install_hook_claude(global_=True)),
        ("cursor", "Cursor", _do_install_hook_cursor),
        ("gemini", "Gemini CLI", _do_install_hook_gemini),
    ]:
        if shutil.which(binary):
            try:
                installer()  # type: ignore[no-untyped-call]
                found.append(label)
            except OSError:
                not_found.append(f"{label} (install failed — run halyard install-hook-{binary})")
        else:
            not_found.append(label)

    if found:
        console.print(f"\n[bold green]Auto-installed hooks:[/] {', '.join(found)}")
    if not_found:
        console.print(
            f"[dim]Not found on PATH:[/] {', '.join(not_found)} "
            f"(install later with [bold]halyard install-hook-<tool>[/])"
        )


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
    from halyard.orchestration import scaffold_project

    scaffold_project(Path.cwd(), hub=hub)
    _auto_install_detected_hooks()


@app.command()
def hub(
    set_path: str | None = typer.Argument(
        None, metavar="PATH", help="Set hub to this directory (must contain halyard.toml)."
    ),
) -> None:
    """Show or set the global hub directory for cross-project session capture."""
    from halyard.hub import get_hub_status, set_hub

    if set_path is not None:
        target = Path(set_path).resolve()
        try:
            set_hub(target)
        except ValueError as e:
            console.print(f"[bold red]Error:[/] {e} — run [bold]halyard init[/] there first.")
            raise typer.Exit(code=1) from None

        console.print(f"[bold green]Hub set[/] → [bold]{target}[/]")
        return

    status = get_hub_status()
    if status.path is None:
        console.print(
            "[yellow]No hub configured.[/]\n"
            "Sessions outside any halyard.toml directory are currently dropped.\n\n"
            "To fix: [bold]halyard init --hub[/] in a central directory, or\n"
            "        [bold]halyard hub <path>[/] to point at an existing project."
        )
    else:
        console.print(
            f"[bold cyan]Hub[/] → [bold]{status.path}[/]  ({status.session_count} sessions)"
        )


@app.command(name="doctor")
def doctor_cmd(
    json_: bool = typer.Option(False, "--json", help="Write machine-readable JSON."),
    first_capture: bool = typer.Option(
        False,
        "--first-capture",
        help="Verify that a recent AI session was captured somewhere.",
    ),
    tool: str = typer.Option("all", "--tool", help="claude | cursor | gemini | all"),
) -> None:
    """Diagnose Halyard setup, hooks, logs, and first-capture readiness."""
    from halyard.doctor import build_doctor_report, has_errors, render_json, render_text

    if tool not in {"claude", "cursor", "gemini", "all"}:
        console.print("[bold red]Error:[/] --tool must be one of: claude, cursor, gemini, all")
        raise typer.Exit(code=1)

    report = build_doctor_report(tool=cast(Any, tool), first_capture=first_capture)
    if json_:
        sys.stdout.write(render_json(report))
    else:
        console.print(render_text(report))

    if has_errors(report):
        raise typer.Exit(code=1)


@app.command(name="setup")
def setup_cmd(
    all_tools: bool = typer.Option(False, "--all", help="Install all supported hooks."),
    claude: bool = typer.Option(False, "--claude", help="Install Claude Code hooks."),
    cursor: bool = typer.Option(False, "--cursor", help="Install Cursor hooks."),
    gemini: bool = typer.Option(False, "--gemini", help="Install Gemini CLI hooks."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Run non-interactively."),
    global_claude: bool = typer.Option(
        False,
        "--global-claude",
        help="Install Claude Code hooks into ~/.claude/settings.json.",
    ),
) -> None:
    """Guided first-run setup for Halyard capture."""
    from halyard.doctor import build_doctor_report, render_text
    from halyard.setup import next_step_text, readiness, resolve_selection, tool_label

    state = readiness()
    console.print("[bold cyan]Halyard Setup[/]")
    if state.project_dir is not None:
        console.print(f"Project: [bold]{state.project_dir}[/]")
    else:
        console.print("[yellow]Project:[/] none found")
    if state.hub_dir is not None:
        console.print(f"Hub: [bold]{state.hub_dir}[/]")
    else:
        console.print("[yellow]Hub:[/] not configured")
    if not state.has_destination:
        console.print(
            "[bold yellow]Capture has no destination yet.[/] "
            "Run [bold]halyard init[/] or [bold]halyard init --hub[/]."
        )

    selection = resolve_selection(
        all_tools=all_tools,
        claude=claude,
        cursor=cursor,
        gemini=gemini,
        yes=yes,
    )

    tools = list(selection.tools)
    if not tools and not yes:
        for candidate in ("claude", "cursor", "gemini"):
            install = typer.confirm(
                f"Install {tool_label(candidate)} hooks?",
                default=candidate == "claude",
            )
            if install:
                tools.append(candidate)

    install_errors: list[str] = []
    if not tools:
        console.print("[yellow]No hooks selected.[/]")
    else:
        console.print("Installing: " + ", ".join(tool_label(tool) for tool in tools))
        for selected in tools:
            try:
                if selected == "claude":
                    install_hook(global_=global_claude)
                elif selected == "cursor":
                    install_cursor_hook()
                elif selected == "gemini":
                    install_gemini_hook()
            except OSError as exc:
                install_errors.append(f"{tool_label(selected)}: {exc}")
                console.print(f"[bold red]Could not install {tool_label(selected)} hooks:[/] {exc}")

    report = build_doctor_report()
    console.print("")
    console.print(render_text(report))
    console.print("")
    console.print(f"[bold green]{next_step_text()}[/]")
    if install_errors:
        raise typer.Exit(code=1)


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
    json_output: bool = typer.Option(False, "--json", help="Emit structured JSON."),
    period: str = typer.Option("month", "--period", help="today | week | month | all"),
    agent: str | None = typer.Option(
        None,
        "--agent",
        help="Query provider: local | claude | openai. Defaults to ~/.halyard/config.toml value.",
    ),
    model: str | None = typer.Option(
        None, "--model", help="Provider model for model-backed agents."
    ),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        help="Base URL for OpenAI-compatible endpoint (default: https://api.openai.com/v1). "
        "Use http://localhost:11434/v1 for Ollama.",
    ),
    tool: str | None = typer.Option(None, "--tool", help="Filter local queries by tool."),
    project: str | None = typer.Option(None, "--project", help="Filter local queries by project."),
    model_filter: str | None = typer.Option(
        None, "--model-filter", help="Filter local queries by model substring."
    ),
    branch: str | None = typer.Option(None, "--branch", help="Filter local queries by branch tag."),
) -> None:
    """Answer a natural-language query about captured work metadata.

    Providers: local (no API key), claude (ANTHROPIC_API_KEY),
    openai (OPENAI_API_KEY or --base-url for local servers like Ollama).
    """
    from halyard.ai_log import find_project_dir
    from halyard.hub import find_hub
    from halyard.log_agent import LogAgent, LogAgentError, LogQueryFilters, run_log_query
    from halyard.log_config import load_log_config

    project_dir = find_project_dir() or find_hub()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    cfg = load_log_config()
    resolved_agent = agent or cfg.default_agent

    if resolved_agent not in {"local", "claude", "openai"}:
        console.print("[bold red]Error:[/] --agent must be one of: local, claude, openai.")
        raise typer.Exit(code=1)

    try:
        response = run_log_query(
            message,
            project_dir=project_dir,
            agent=cast(LogAgent, resolved_agent),
            period=period,
            model=model,
            base_url=base_url,
            filters=LogQueryFilters(
                tool=tool,
                project=project,
                model=model_filter,
                branch=branch,
            ),
        )
    except LogAgentError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1) from None

    if json_output:
        sys.stdout.write(json.dumps(response.to_dict(), indent=2) + "\n")
        return

    console.print(f"[bold]{response.answer}[/]")
    if response.projects:
        console.print("\n[bold]By project[/]")
        for bucket in response.projects:
            console.print(
                f"  {bucket.label:<32} ${bucket.cost_usd:.2f}  {bucket.sessions} sessions"
            )
    if response.models:
        console.print("\n[bold]By model[/]")
        for bucket in response.models:
            console.print(
                f"  {bucket.label:<32} ${bucket.cost_usd:.2f}  {bucket.sessions} sessions"
            )


@app.command()
def start(
    slug: str = typer.Argument(..., help="client/project slug, e.g. acme/auth-migration"),
) -> None:
    """Start the active timer."""
    from halyard.orchestration import TimerAlreadyRunning, start_timer

    timeclock_candidate = Path.cwd() / "time.timeclock"
    if not timeclock_candidate.exists():
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
    try:
        # v2.17 task 5.4: delegate to shared start_timer (orchestration.py)
        timer = start_timer(Path.cwd(), account)
    except TimerAlreadyRunning as e:
        console.print(
            f"[bold red]Error:[/] Timer already running for [bold]{e.slug}[/].\n"
            "Run [bold]halyard stop[/] first."
        )
        raise typer.Exit(code=1) from e

    console.print(f"[bold green]Started[/] [bold]{timer.slug}[/] at {timer.started}.")


@app.command()
def stop() -> None:
    """Stop the active timer."""
    from halyard.orchestration import stop_timer
    from halyard.reports import _elapsed_minutes, format_minutes, read_active_timer

    # Peek at the active timer first so we can surface a helpful error and
    # compute elapsed time for the user-facing message.
    active = read_active_timer()
    if active is None:
        console.print(
            "[bold red]Error:[/] No active timer. Run "
            "[bold]halyard start <client/project>[/] first."
        )
        raise typer.Exit(code=1)

    if active.timeclock is None or not active.timeclock.exists():
        console.print("[bold red]Error:[/] Active timer has no valid timeclock path.")
        from halyard.reports import _HALYARD_ACTIVE
        _HALYARD_ACTIVE.unlink(missing_ok=True)
        raise typer.Exit(code=1)

    slug = active.slug
    now = datetime.now()

    # v2.17 task 5.4: delegate to shared stop_timer (orchestration.py)
    result = stop_timer(Path.cwd())

    if result.was_running:
        elapsed = format_minutes(_elapsed_minutes(active.started or now.strftime("%Y-%m-%d %H:%M:%S"), now))
        console.print(f"[bold green]Stopped[/] [bold]{slug}[/]. Elapsed: {elapsed}.")
        if result.backfill_count:
            noun = "session" if result.backfill_count == 1 else "sessions"
            console.print(f"  Attributed {result.backfill_count} AI {noun} to [bold]{slug}[/].")
    else:
        console.print("[yellow]No active timer was running.[/]")


@app.command()
def backfill(
    project: str = typer.Option("", "--project", help="Restrict to one project slug."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report without writing."),
    confirm: bool = typer.Option(
        False, "--confirm", help="Prompt interactively for ambiguous sessions."
    ),
) -> None:
    """Attribute unattributed AI sessions using timeclock windows."""
    from halyard.ai_log import (
        AI_LOG_FILENAME,
        AiSession,
        _is_assignable_session_line,
        _parse_line,
        confirm_session_attributions,
        find_project_dir,
    )
    from halyard.reports import parse_timeclock

    project_dir = find_project_dir()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    log_path = project_dir / AI_LOG_FILENAME
    if not log_path.exists():
        console.print("[yellow]No ai-sessions.log found.[/]")
        return

    windows = parse_timeclock(project_dir / "time.timeclock")
    if not windows:
        console.print(
            "[yellow]No timeclock data found.[/] Run [bold]halyard start[/] to begin tracking time."
        )
        return

    if project:
        slug = project.replace("/", ":", 1)
        windows = [(s, e, a) for s, e, a in windows if a == slug]
        if not windows:
            console.print(f"[yellow]No timeclock windows found for [bold]{slug}[/].[/]")
            return

    raw_lines = log_path.read_text().splitlines()
    unambiguous: list[tuple[str, str]] = []
    ambiguous: list[tuple[str, AiSession, list[str]]] = []
    skipped_no_window = 0

    for raw_line in raw_lines:
        line = raw_line.rstrip()
        if not _is_assignable_session_line(line):
            continue
        session = _parse_line(line)
        if session is None:
            continue

        matched_projects = list({a for s, e, a in windows if s <= session.start < e})

        if len(matched_projects) == 0:
            skipped_no_window += 1
        elif len(matched_projects) == 1:
            unambiguous.append((line, matched_projects[0]))
        else:
            ambiguous.append((line, session, matched_projects))

    if confirm and ambiguous:
        for raw_line, session, candidates in ambiguous:
            dur = max(1, int((session.end - session.start).total_seconds() // 60))
            console.print(
                f"\n  {session.start:%Y-%m-%d %H:%M} → {session.end:%H:%M}  ({dur}m)\n"
                f"  {session.tool} / {session.model}  ${session.cost_usd:.4f}\n"
                f"  Candidates: [bold]{', '.join(candidates)}[/]"
            )
            choice = typer.prompt("  Project slug (or Enter to skip)", default="").strip()
            if choice:
                unambiguous.append((raw_line, choice.replace("/", ":", 1)))

    if not unambiguous:
        console.print("[yellow]No sessions to attribute.[/]")
        if skipped_no_window:
            console.print(f"  {skipped_no_window} session(s) have no matching timeclock window.")
        if ambiguous:
            console.print(
                f"  {len(ambiguous)} session(s) are ambiguous"
                " — run with [bold]--confirm[/] to resolve."
            )
        return

    if dry_run:
        console.print(f"\n[bold]{len(unambiguous)} session(s) would be attributed:[/]\n")
        for raw_line, proj in unambiguous:
            session = _parse_line(raw_line)
            if session:
                console.print(
                    f"  {session.start:%Y-%m-%d %H:%M}  {session.tool}/{session.model}"
                    f"  → [bold cyan]{proj}[/]"
                )
    else:
        count = confirm_session_attributions(project_dir, unambiguous)
        noun = "session" if count == 1 else "sessions"
        console.print(f"[bold green]Attributed[/] {count} {noun}.")

    parts = []
    if ambiguous and not confirm:
        parts.append(f"{len(ambiguous)} ambiguous (run [bold]--confirm[/] to resolve)")
    if skipped_no_window:
        parts.append(f"{skipped_no_window} with no timeclock window")
    if parts:
        console.print("  Skipped: " + ", ".join(parts) + ".")


@app.command()
def status() -> None:
    """Show the active timer, or report that none is running."""
    from halyard.reports import read_active_timer

    active = read_active_timer()
    if active is None:
        console.print(
            "[yellow]No active timer.[/] Start one with [bold]halyard start <project>[/]."
        )
        return

    console.print(
        f"[bold cyan]{active.slug}[/]  {active.elapsed_label} elapsed  "
        f"(started {active.started or '?'})"
    )


# ---------------------------------------------------------------------------
# Invoicing
# ---------------------------------------------------------------------------


@app.command()
def invoice(
    client: str = typer.Argument(..., help="Client slug to invoice."),
    month: str | None = typer.Option(None, "--month", help="last | this | YYYY-MM"),
    from_: str | None = typer.Option(None, "--from", help="ISO date (inclusive lower bound)"),
    to: str | None = typer.Option(None, "--to", help="ISO date (inclusive upper bound)"),
    project: str | None = typer.Option(None, "--project", help="Project slug under the client."),
    period: str | None = typer.Option(None, "--period", help="Billing period as YYYY-MM."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
    pdf: bool = typer.Option(False, "--pdf", help="Render a PDF via typst after writing markdown."),
    force: bool = typer.Option(
        False, "--force", help="Overwrite an existing invoice for the period."
    ),
    rate: float | None = typer.Option(None, "--rate", help="Override hourly rate."),
    include_ai_evidence: bool = typer.Option(
        False, "--include-ai-evidence", help="Append AI usage evidence appendix."
    ),
) -> None:
    """Generate an invoice from logged time entries."""
    from halyard.ai_log import find_project_dir
    from halyard.invoicing import (
        InvoiceError,
        generate_invoice,
        normalize_invoice_month,
        render_pdf,
    )

    if from_ or to:
        console.print(
            "[bold red]Error:[/] --from/--to ranges are not implemented yet. Use --period."
        )
        raise typer.Exit(code=1)

    project_dir = find_project_dir()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    try:
        invoice_period = period or normalize_invoice_month(month)
    except ValueError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1) from None
    try:
        result = generate_invoice(
            client,
            project_slug=project,
            period=invoice_period,
            project_dir=project_dir,
            force=force,
            dry_run=dry_run,
            rate_override=rate,
            include_ai_evidence=include_ai_evidence,
        )
    except InvoiceError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1) from None

    if result.warning:
        console.print(f"[yellow]{result.warning}[/]")

    if dry_run:
        console.print(result.rendered)
        return

    if result.path is not None:
        console.print(f"[bold green]Invoice written:[/] {result.path.relative_to(project_dir)}")
        if pdf:
            warning = render_pdf(result.path)
            if warning:
                console.print(f"[yellow]{warning}[/]")


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


def _do_install_hook_claude(global_: bool = False) -> None:
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
        console.print(f"[bold green]Claude Code hooks installed[/] in [bold]{settings_path}[/]")
    else:
        console.print(f"[yellow]Claude Code hooks already present[/] in [bold]{settings_path}[/]")


@app.command(name="install-hook-claude")
def install_hook_claude(
    global_: bool = typer.Option(
        False,
        "--global",
        help="Install into ~/.claude/settings.json instead of .claude/settings.json.",
    ),
) -> None:
    """Install Claude Code hooks to auto-capture AI sessions."""
    _do_install_hook_claude(global_=global_)


@app.command(name="install-hook", hidden=True)
def install_hook(
    global_: bool = typer.Option(
        False,
        "--global",
        help="Install into ~/.claude/settings.json instead of .claude/settings.json.",
    ),
) -> None:
    """Deprecated alias for install-hook-claude."""
    _do_install_hook_claude(global_=global_)


def _do_install_hook_gemini() -> None:
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
        console.print(f"[bold green]Gemini CLI hooks installed[/] in [bold]{settings_path}[/]")
    else:
        console.print(f"[yellow]Gemini CLI hooks already present[/] in [bold]{settings_path}[/]")


@app.command(name="install-hook-gemini")
def install_hook_gemini() -> None:
    """Install Gemini CLI hooks to auto-capture AI sessions."""
    _do_install_hook_gemini()


@app.command(name="install-gemini-hook", hidden=True)
def install_gemini_hook() -> None:
    """Deprecated alias for install-hook-gemini."""
    _do_install_hook_gemini()


def _do_install_hook_cursor() -> None:
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
        console.print(f"[bold green]Cursor hooks installed[/] in [bold]{settings_path}[/]")
    else:
        console.print(f"[yellow]Cursor hooks already present[/] in [bold]{settings_path}[/]")


@app.command(name="install-hook-cursor")
def install_hook_cursor() -> None:
    """Install Cursor hooks to auto-capture AI sessions."""
    _do_install_hook_cursor()


@app.command(name="install-cursor-hook", hidden=True)
def install_cursor_hook() -> None:
    """Deprecated alias for install-hook-cursor."""
    _do_install_hook_cursor()


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
    from halyard.reports import get_active_project

    project_dir = find_project_dir()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    attributed_project = project or get_active_project(project_dir)
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


@app.command(name="seed-demo")
def seed_demo(
    yes: bool = typer.Option(False, "--yes", help="Confirm appending to an existing log."),
) -> None:
    """Seed ai-sessions.log with realistic demo data for dashboard previews."""
    import random
    from datetime import datetime, timedelta

    from halyard.ai_log import AiSession, append_session, find_project_dir, parse_sessions

    project_dir = find_project_dir()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    existing = parse_sessions(project_dir)
    if existing and not yes:
        console.print(
            f"[yellow]Log already has {len(existing)} session(s).[/] "
            "Pass [bold]--yes[/] to append demo data anyway."
        )
        raise typer.Exit(code=1)

    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    rng = random.Random(42)  # deterministic seed for reproducible demos

    tool_models = {
        "claude-code": "claude-sonnet-4-6",
        "gemini-cli": "gemini-2.0-flash",
        "cursor": "gpt-4o",
    }

    # fmt: off
    # (project, tool, cost, in_tok, out_tok, mins, calls, errs, added, removed, day)
    sessions_spec = [
        ("acme:auth",          "claude-code", 0.45, 18000, 3200, 25, 32,   3,  88, 12,  0),
        ("acme:auth",          "claude-code", 0.82, 31000, 5400, 40, 58,   2, 215, 40,  1),
        ("acme:auth",          "gemini-cli",  0.28, 12000, 1800, 18, 20,   1,  44,  8,  1),
        ("acme:auth",          "claude-code", 1.24, 48000, 7200, 60, 91,  24,  31, 10,  2),
        ("acme:auth",          "claude-code", 1.10, 41000, 6100, 55, 78,  21,  28,  9,  2),
        ("acme:auth",          "cursor",      0.19,  8000, 1200, 12, None, None, 52,  5,  3),
        ("acme:api",           "claude-code", 0.63, 24000, 4100, 32, 44,   2, 180, 22,  4),
        ("acme:api",           "claude-code", 0.91, 35000, 5800, 45, 62,   5, 243, 38,  5),
        ("acme:api",           "gemini-cli",  0.35, 15000, 2200, 22, 28,   0,  95, 14,  5),
        ("acme:api",           "cursor",      0.12,  5000,  800,  8, None, None, 30,  3,  6),
        ("acme:api",           "claude-code", 0.74, 28000, 4500, 36, 51,   3, 197, 29,  7),
        ("globex:ml-pipeline", "gemini-cli",  0.55, 22000, 3500, 28, 38,   2, 120, 18,  8),
        ("globex:ml-pipeline", "gemini-cli",  0.48, 19000, 3000, 24, 31,   1,  88, 11,  8),
        ("globex:ml-pipeline", "claude-code", 0.93, 36000, 5900, 47, 65,   4, 228, 35,  9),
        ("globex:ml-pipeline", "cursor",      0.22,  9000, 1400, 14, None, None, 61,  7, 10),
        ("globex:ml-pipeline", "gemini-cli",  0.67, 26000, 4200, 33, 47,   3, 152, 24, 11),
        ("globex:data-infra",  "claude-code", 0.38, 15000, 2500, 19, 26,   1,  75,  9, 12),
        ("globex:data-infra",  "gemini-cli",  0.29, 12500, 1900, 18, 21,   0,  58,  7, 12),
        ("globex:data-infra",  "claude-code", 0.71, 27000, 4300, 35, 49,   2, 188, 28, 13),
        ("globex:data-infra",  "cursor",      0.15,  6500,  950, 10, None, None, 40,  4, 14),
        ("globex:data-infra",  "claude-code", 1.05, 40000, 6000, 52, 73,   8,   0,  0, 15),
        ("acme:auth",          "claude-code", 0.33, 13000, 2000, 20, 22,   1,  55,  8, 16),
        ("acme:auth",          "claude-code", 0.41, 17000, 2700, 26, 30,   2,  72, 10, 16),
        ("acme:auth",          "claude-code", 0.38, 15500, 2400, 23, 27,   3,  61,  9, 16),
        (None,                 "claude-code", 1.35, 52000, 7800, 65, 88,   5, None, None, 17),
        (None,                 "gemini-cli",  0.88, 34000, 5200, 43, 57,   3, None, None, 18),
        (None,                 "cursor",      0.14,  6000,  900,  9, None, None, None, None, 19),
        ("acme:api",           "claude-code", 0.56, 22000, 3600, 28, 39,   2, 163, 21, 20),
        ("acme:api",           "gemini-cli",  0.44, 18000, 2800, 22, 33,   1, 108, 15, 21),
        ("globex:ml-pipeline", "claude-code", 0.79, 30000, 4800, 38, 53,   3, 205, 31, 22),
    ]
    # fmt: on

    added: list[AiSession] = []
    for row in sessions_spec:
        proj, tool, cost, inp, out, mins, tcalls, terrs, cadd, crem, day_off = row
        base_hour = rng.randint(8, 17)
        base_min = rng.randint(0, 45)
        start = month_start + timedelta(days=day_off, hours=base_hour, minutes=base_min)
        end = start + timedelta(minutes=mins)
        tags: list[str] = []
        if proj in ("acme:auth", "acme:api"):
            tags.append("branch:main")
        session = AiSession(
            start=start,
            end=end,
            tool=tool,
            model=tool_models[tool],
            input_tokens=inp,
            output_tokens=out,
            cost_usd=cost,
            project=proj,
            tokens_available=True,
            billing="api",
            source="demo",
            tags=tags,
            tool_calls=tcalls,
            tool_errors=terrs,
            code_added=cadd,
            code_removed=crem,
        )
        append_session(project_dir, session)
        added.append(session)

    projects_written = sorted({s.project or "(unattributed)" for s in added})
    console.print(f"[bold green]Seeded[/] {len(added)} demo sessions:")
    for p in projects_written:
        count = sum(1 for s in added if (s.project or "(unattributed)") == p)
        console.print(f"  {p}  {count} sessions")
    console.print(
        "\nRun [bold]halyard health[/], [bold]halyard dashboard[/], "
        "or [bold]halyard schedule[/] to explore."
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
    from halyard.orchestration import interactive_assign_unattributed

    interactive_assign_unattributed(explicit_project=project)


@app.command(name="confirm-attribution")
def confirm_attribution() -> None:
    """Confirm AI sessions with project attribution inferred from timeclock overlap."""
    from halyard.ai_log import find_project_dir
    from halyard.orchestration import interactive_confirm_attribution

    project_dir = find_project_dir()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    interactive_confirm_attribution(project_dir)


@app.command(name="check-log")
def check_log(
    log_path: str | None = typer.Option(
        None,
        "--log",
        help="Path to ai-sessions.log. Defaults to current project log.",
    ),
) -> None:
    """Validate an AI session log and quarantine malformed lines."""
    from halyard.ai_log import AI_LOG_FILENAME, AiSession, find_project_dir

    resolved_log_path: Path
    if log_path is None:
        from halyard.hub import find_hub

        project_dir = find_project_dir() or find_hub()
        if project_dir is None:
            console.print(
                "[bold red]Error:[/] No Halyard project or hub found. "
                "Run [bold]halyard init[/] first or pass [bold]--log[/]."
            )
            raise typer.Exit(code=1)
        resolved_log_path = project_dir / AI_LOG_FILENAME
    else:
        resolved_log_path = Path(log_path)

    if not resolved_log_path.exists():
        console.print(f"[bold red]Error:[/] Log not found: {resolved_log_path}")
        raise typer.Exit(code=1)

    valid = 0
    invalid = 0
    for lineno, raw_line in enumerate(resolved_log_path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        error = AiSession.log_line_error(line)
        if error is not None:
            AiSession.from_log_line(line)
            invalid += 1
            console.print(f"[red]Line {lineno}: {error}[/]")
            console.print(f"  {line}")
        else:
            valid += 1

    if invalid:
        console.print(
            f"[bold red]{invalid} invalid[/], {valid} valid. See ~/.halyard/quarantine.log."
        )
        raise typer.Exit(code=1)

    console.print(f"[bold green]All {valid} lines valid.[/]")


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
                    except Exception as e:
                        from halyard.ai_log import _log_error
                        _log_error("reading gemini .project_root failed", e)
                        console.print(
                            f"[yellow]Warning:[/] could not read Gemini project root "
                            f"({type(e).__name__}). See ~/.halyard/halyard.log."
                        )
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
                    imported_ids.add(s.job_id[len("gemini:") :])

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
            console.print(f"  [dim]skip {summary.session_id[:8]} — no project dir or hub[/dim]")
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
    from halyard.reports import (
        build_filtered_ai_report,
        build_human_time_report,
        check_pricing_staleness,
        format_minutes,
    )

    project_dir = find_project_dir()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    # Staleness warning for pricing table
    age, is_stale = check_pricing_staleness()
    if is_stale:
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

    report = build_filtered_ai_report(
        project_dir, project=project, client=client, all_time=all_time, now=period
    )
    human = build_human_time_report(project_dir, now=period)

    filter_label = f" — {project or client}" if (project or client) else ""
    console.print(f"\n[bold]Report — {report.period_label}{filter_label}[/]")
    console.print("─" * 48)

    if human.month_minutes:
        console.print(
            f"  Human time [bold cyan]{format_minutes(human.month_minutes)}[/]  this month"
            f"  (today: {format_minutes(human.today_minutes)})"
        )

    if not report.sessions:
        console.print(f"  [yellow]No AI sessions recorded for {report.period_label}.[/]")
        console.print(
            "\n  Run [bold]halyard install-hook[/] to start capturing sessions automatically."
        )
        console.print("─" * 48 + "\n")
        raise typer.Exit(code=0)

    console.print(f"  AI sessions  [bold]{len(report.sessions)}[/]")
    console.print(f"  AI cost      [bold green]${report.total_cost:.2f}[/]")
    if report.total_input_tokens:
        console.print(
            f"  Tokens       in {report.total_input_tokens:,}  out {report.total_output_tokens:,}"
        )

    if not project and report.by_project:
        console.print("\n[bold]By project[/]")
        for bucket in report.by_project:
            console.print(
                f"  {bucket.label:<32} [green]${bucket.cost_usd:.2f}[/]  {bucket.sessions} sessions"
            )

    if report.by_model:
        console.print("\n[bold]By model[/]")
        for bucket in report.by_model:
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
                report.sessions, plans, tc_entries, year=period.year, month=period.month
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

    from halyard.ai_log import unattributed_log_count

    global_unattributed = unattributed_log_count()
    if global_unattributed:
        console.print(
            f"\n[yellow]{global_unattributed} unattributed session(s) in "
            "~/.halyard/unattributed.log — run 'halyard assign-unattributed' to review.[/]"
        )

    console.print("─" * 48 + "\n")


@app.command()
def health(
    period: str = typer.Option("month", "--period", help="today | week | month | all"),
    project: str | None = typer.Option(None, "--project", help="Filter to a project slug."),
    format_: str = typer.Option("text", "--format", help="text | json"),
) -> None:
    """Show AI work health signals for the current period."""
    import json as _json
    from datetime import datetime, timedelta

    from halyard.ai_log import find_project_dir, parse_sessions
    from halyard.hub import find_hub
    from halyard.work_health import build_health_report, render_json, render_text

    project_dir = find_project_dir() or find_hub()
    if project_dir is None:
        console.print("No Halyard project found.")
        raise typer.Exit(code=1)

    sessions = parse_sessions(project_dir)

    # Period filter
    now = datetime.now()
    p = period.lower()
    if p == "today":
        sessions = [s for s in sessions if s.start.date() == now.date()]
    elif p == "week":
        week_start = now - timedelta(days=now.weekday())
        sessions = [s for s in sessions if s.start.date() >= week_start.date()]
    elif p == "month":
        sessions = [s for s in sessions if s.start.year == now.year and s.start.month == now.month]
    elif p != "all":
        console.print("[bold red]Error:[/] --period must be one of: today, week, month, all")
        raise typer.Exit(code=1)

    # Project filter
    if project:
        sessions = [s for s in sessions if s.project == project]

    report = build_health_report(sessions, period=p)

    if format_ == "json":
        sys.stdout.write(_json.dumps(render_json(report), indent=2) + "\n")
    else:
        console.print(render_text(report))


@app.command(name="org")
def org_summary_cmd(
    period: str = typer.Option("month", "--period", help="today | week | month | all"),
    format_: str = typer.Option("text", "--format", help="text | json"),
) -> None:
    """Show AI usage rolled up by team and project using org.toml identity."""
    from datetime import datetime, timedelta

    from halyard.ai_log import find_project_dir, parse_sessions
    from halyard.cost_centers import read_cost_center_config
    from halyard.hub import find_hub
    from halyard.org import read_org_config
    from halyard.org_rollups import build_org_summary, render_org_text

    project_dir = find_project_dir() or find_hub()
    if project_dir is None:
        console.print("No Halyard project found.")
        raise typer.Exit(code=1)

    org = read_org_config(project_dir)
    if org is None:
        console.print(
            f"[bold red]Error:[/] No org.toml found in [bold]{project_dir}[/].\n"
            "Create org.toml to define your org identity and team mappings."
        )
        raise typer.Exit(code=1)

    cost_centers = read_cost_center_config(project_dir)
    sessions = parse_sessions(project_dir)

    now = datetime.now()
    p = period.lower()
    if p == "today":
        sessions = [s for s in sessions if s.start.date() == now.date()]
    elif p == "week":
        week_start = now - timedelta(days=now.weekday())
        sessions = [s for s in sessions if s.start.date() >= week_start.date()]
    elif p == "month":
        sessions = [s for s in sessions if s.start.year == now.year and s.start.month == now.month]
    elif p != "all":
        console.print("[bold red]Error:[/] --period must be: today, week, month, all")
        raise typer.Exit(code=1)

    summary = build_org_summary(sessions, org, cost_centers, period=p)

    if format_ == "json":
        import json as _json

        sys.stdout.write(
            _json.dumps(
                {
                    "org": summary.org_name,
                    "period": summary.period,
                    "total_sessions": summary.total_sessions,
                    "total_cost": summary.total_cost,
                    "active_users": summary.active_users,
                    "trust": summary.trust,
                    "teams": [
                        {
                            "team_id": t.team_id,
                            "team_name": t.team_name,
                            "sessions": t.sessions,
                            "total_cost": t.total_cost,
                            "active_users": t.active_users,
                            "trust": t.trust,
                            "unattributed_count": t.unattributed_count,
                        }
                        for t in summary.teams
                    ],
                    "governance_flags": [
                        {
                            "category": f.category,
                            "team_id": f.team_id,
                            "user": f.user,
                            "detail": f.detail,
                        }
                        for f in summary.governance_flags
                    ],
                },
                indent=2,
            )
            + "\n"
        )
    else:
        console.print(render_org_text(summary))


@app.command(name="export")
def export_cmd(
    period: str = typer.Option("month", "--period", help="YYYY-MM | today | week | month | all"),
    format_: str = typer.Option("csv", "--format", help="csv"),
    output: str | None = typer.Option(None, "--output", help="Output file path."),
    stdout: bool = typer.Option(False, "--stdout", help="Write to stdout."),
) -> None:
    """Export cost allocation data as CSV (finance/BI format)."""
    from datetime import datetime, timedelta
    from pathlib import Path as _Path

    from halyard.ai_log import find_project_dir, parse_sessions
    from halyard.cost_centers import read_cost_center_config
    from halyard.hub import find_hub
    from halyard.org import read_org_config
    from halyard.org_rollups import build_org_summary, render_finance_csv

    project_dir = find_project_dir() or find_hub()
    if project_dir is None:
        console.print("No Halyard project found.")
        raise typer.Exit(code=1)

    org = read_org_config(project_dir)
    if org is None:
        console.print(
            "[bold red]Error:[/] No org.toml found. Create org.toml to enable org-level exports."
        )
        raise typer.Exit(code=1)

    cost_centers = read_cost_center_config(project_dir)
    sessions = parse_sessions(project_dir)

    now = datetime.now()
    # Accept YYYY-MM as period
    p = period.lower()
    if len(period) == 7 and period[4] == "-":
        try:
            target = datetime.strptime(period, "%Y-%m")
            sessions = [
                s for s in sessions if s.start.year == target.year and s.start.month == target.month
            ]
            p = period
        except ValueError:
            pass
    elif p == "today":
        sessions = [s for s in sessions if s.start.date() == now.date()]
    elif p == "week":
        week_start = now - timedelta(days=now.weekday())
        sessions = [s for s in sessions if s.start.date() >= week_start.date()]
    elif p == "month":
        sessions = [s for s in sessions if s.start.year == now.year and s.start.month == now.month]

    summary = build_org_summary(sessions, org, cost_centers, period=p)
    csv_content = render_finance_csv(summary.finance_rows)

    if stdout:
        sys.stdout.write(csv_content)
        return

    if output:
        dest = _Path(output)
    else:
        period_slug = p.replace("-", "")
        dest = project_dir / "exports" / f"{period_slug}-{org.org.id}.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(csv_content, encoding="utf-8")
    console.print(f"[bold green]Exported[/] {len(summary.finance_rows)} rows → [bold]{dest}[/]")


@app.command()
def schedule(
    period: str = typer.Option("month", "--period", help="today | week | month | all"),
    project: str | None = typer.Option(None, "--project", help="Filter to a project slug."),
    output: str | None = typer.Option(None, "--output", help="Output file path."),
    stdout: bool = typer.Option(False, "--stdout", help="Write ICS to stdout instead of a file."),
) -> None:
    """Export AI sessions as a .ics calendar file."""
    from datetime import datetime, timedelta
    from pathlib import Path as _Path

    from halyard.ai_log import find_project_dir, parse_sessions
    from halyard.hub import find_hub
    from halyard.schedule import build_calendar

    project_dir = find_project_dir() or find_hub()
    if project_dir is None:
        console.print("No Halyard project found.")
        raise typer.Exit(code=1)

    sessions = parse_sessions(project_dir)

    now = datetime.now()
    p = period.lower()
    if p == "today":
        sessions = [s for s in sessions if s.start.date() == now.date()]
    elif p == "week":
        week_start = now - timedelta(days=now.weekday())
        sessions = [s for s in sessions if s.start.date() >= week_start.date()]
    elif p == "month":
        sessions = [s for s in sessions if s.start.year == now.year and s.start.month == now.month]
    elif p != "all":
        console.print("[bold red]Error:[/] --period must be one of: today, week, month, all")
        raise typer.Exit(code=1)

    if project:
        sessions = [s for s in sessions if s.project == project]

    ics = build_calendar(sessions)

    if stdout:
        sys.stdout.write(ics)
        return

    dest = _Path(output) if output else project_dir / "ai-schedule.ics"
    dest.write_text(ics, encoding="utf-8")
    noun = "session" if len(sessions) == 1 else "sessions"
    console.print(f"[bold green]Exported[/] {len(sessions)} {noun} → [bold]{dest}[/]")


@app.command()
def dashboard(
    port: int = typer.Option(7432, "--port", help="Local port (default 7432)."),
    open_: bool = typer.Option(False, "--open", help="Open the dashboard in a browser."),
    project_dir_opt: Path = typer.Option(
        None, "--project-dir", help="Halyard project directory (default: auto-detect)."
    ),
) -> None:
    """Start the local Halyard Glass Cockpit dashboard."""
    from halyard.ai_log import find_project_dir
    from halyard.dashboard import run_dashboard

    project_dir = project_dir_opt or find_project_dir()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    run_dashboard(project_dir, port=port, open_browser=open_)


# ---------------------------------------------------------------------------
# Service management (background LaunchAgent — macOS)
# ---------------------------------------------------------------------------

service_app = typer.Typer(
    name="service", help="Manage the Halyard Glass Cockpit background service."
)
app.add_typer(service_app)


@service_app.command(name="install")
def service_install(
    port: int = typer.Option(7432, "--port", help="Port for the background dashboard."),
) -> None:
    """Install Halyard as a macOS login service (auto-starts the Glass Cockpit)."""
    import platform

    if platform.system() != "Darwin":
        console.print("[bold red]Error:[/] Service management is only supported on macOS.")
        raise typer.Exit(code=1)

    from halyard.ai_log import find_project_dir
    from halyard.hub import find_hub
    from halyard.service import install_service

    project_dir = find_project_dir() or find_hub()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project or hub found. "
            "Run [bold]halyard init[/] or [bold]halyard set-hub[/] first."
        )
        raise typer.Exit(code=1)

    try:
        url = install_service(project_dir, port=port)
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    console.print("[bold green]Service installed.[/] Glass Cockpit will start at login.")
    console.print(f"  Dashboard: [bold cyan]{url}[/]")
    console.print("  Logs:      ~/Library/Logs/halyard-dashboard.log")
    console.print("\nTo uninstall: [bold]halyard service uninstall[/]")


@service_app.command(name="uninstall")
def service_uninstall() -> None:
    """Uninstall the Halyard background service."""
    import platform

    if platform.system() != "Darwin":
        console.print("[bold red]Error:[/] Service management is only supported on macOS.")
        raise typer.Exit(code=1)

    from halyard.service import PLIST_PATH, uninstall_service

    if not PLIST_PATH.exists():
        console.print("[yellow]Service is not installed.[/]")
        return

    uninstall_service()
    console.print("[bold green]Service uninstalled.[/]")


@service_app.command(name="status")
def service_status_cmd() -> None:
    """Show whether the Halyard background service is running."""
    import platform

    if platform.system() != "Darwin":
        console.print("[bold red]Error:[/] Service management is only supported on macOS.")
        raise typer.Exit(code=1)

    from halyard.service import service_status

    running, info = service_status()
    if running:
        console.print(f"[bold green]Running[/]  {info}")
    else:
        console.print(f"[yellow]Stopped[/]  {info}")


# ---------------------------------------------------------------------------
# Config history and rate audit (v2.15)
# ---------------------------------------------------------------------------

config_app = typer.Typer(name="config", help="Rate history and invoice audit commands.")
app.add_typer(config_app)


@config_app.command(name="history")
def config_history(
    client: str = typer.Option("", "--client", help="Filter to a single client slug."),
) -> None:
    """Show rate change history from git log or clients.toml rate_history entries."""
    from rich.table import Table

    from halyard.ai_log import find_project_dir
    from halyard.config_history import (
        is_git_repo,
        rate_history_from_git,
        rate_history_from_toml,
    )

    project_dir = find_project_dir()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    if is_git_repo(project_dir):
        changes = rate_history_from_git(project_dir)
        source_label = "git log"
    else:
        changes = rate_history_from_toml(project_dir)
        source_label = "clients.toml"

    if client:
        slug = client.replace("/", ":", 1)
        changes = [c for c in changes if c.client_slug == slug]

    if not changes:
        console.print(
            "[yellow]No rate history found.[/] "
            "Add [bold][[client.rate_history]][/] entries to clients.toml "
            "or commit rate changes to git."
        )
        return

    table = Table(title=f"Rate history  ({source_label})", show_lines=False)
    table.add_column("Client", style="cyan")
    table.add_column("Date")
    table.add_column("Rate", justify="right")
    table.add_column("Source", style="dim")

    for c in changes:
        table.add_row(
            c.client_slug,
            str(c.effective_date),
            f"${c.rate:,.2f}/hr",
            c.source,
        )

    console.print(table)
    console.print("\n[dim]Tip: commit clients.toml to git for a full, auditable rate history.[/]")


@config_app.command(name="audit")
def config_audit(
    client: str = typer.Option("", "--client", help="Filter to a single client slug."),
    period: str = typer.Option("", "--period", help="Filter to a billing period (YYYY-MM)."),
) -> None:
    """Cross-check invoice rates against effective rates from clients.toml."""
    from rich.table import Table

    from halyard.ai_log import find_project_dir
    from halyard.config_history import audit_invoices

    project_dir = find_project_dir()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    invoice_dir = project_dir / "invoices"
    if not invoice_dir.exists() or not any(invoice_dir.glob("*.md")):
        console.print("[yellow]No invoices found in [bold]invoices/[/bold].[/]")
        return

    mismatches = audit_invoices(
        project_dir,
        client_filter=client.replace("/", ":", 1) if client else None,
        period_filter=period or None,
    )

    if not mismatches:
        console.print(
            "[bold green]Audit clean.[/] All invoice rates match the effective rate history."
        )
        return

    table = Table(title="Rate mismatches", show_lines=False)
    table.add_column("Invoice", style="dim")
    table.add_column("Client", style="cyan")
    table.add_column("Period")
    table.add_column("Expected", justify="right")
    table.add_column("Actual", justify="right", style="red")

    for m in mismatches:
        table.add_row(
            m.invoice_file,
            m.client_slug,
            m.period,
            f"${m.expected_rate:,.2f}/hr",
            f"${m.actual_rate:,.2f}/hr",
        )

    console.print(table)
    console.print(
        f"\n[bold red]{len(mismatches)} mismatch(es) found.[/] "
        "Check [bold]clients.toml[/] rate_history and re-generate affected invoices."
    )
    raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# SQLite read-model cache (v2.14)
# ---------------------------------------------------------------------------

db_app = typer.Typer(name="db", help="SQLite cache management.")
app.add_typer(db_app)


@db_app.command(name="sync")
def db_sync(
    status: bool = typer.Option(False, "--status", help="Show last sync status without syncing."),
) -> None:
    """Sync plain-text log files into the SQLite cache (~/.halyard/cache.db)."""
    from halyard.db import db_path, last_sync, sync_all

    if status:
        info = last_sync()
        if info is None:
            console.print("[yellow]Never synced.[/] Run [bold]halyard db sync[/] first.")
        else:
            console.print(f"[bold]Last sync:[/] {info['synced_at']}")
            console.print(f"  Files read:  {info['files_read']}")
            console.print(f"  Rows added:  {info['rows_added']}")
            console.print(f"  Cache:       {db_path()}")
        return

    result = sync_all()
    session_noun = "session" if result.sessions_added == 1 else "sessions"
    tc_noun = "entry" if result.timeclock_added == 1 else "entries"
    console.print(
        f"[bold green]Synced[/] {result.sessions_added} {session_noun} and "
        f"{result.timeclock_added} timeclock {tc_noun} "
        f"across {result.files_read} file(s)."
    )
    console.print(f"  Cache: [dim]{db_path()}[/]")


@db_app.command(name="reset")
def db_reset() -> None:
    """Delete the SQLite cache (cache.db). Safe to re-run sync afterwards."""
    from halyard.db import db_path, reset

    path = db_path()
    if not path.exists():
        console.print("[yellow]No cache file found.[/]")
        return

    reset()
    console.print(f"[bold green]Deleted[/] {path}")


@app.command(name="tui")
def tui_cmd() -> None:
    """Launch the interactive Textual terminal dashboard."""
    from halyard.ai_log import AI_LOG_FILENAME, find_project_dir
    from halyard.hub import find_hub

    try:
        from halyard.tui.app import HalyardApp
    except ImportError as exc:
        console.print(f"[bold red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(code=1) from None

    project_dir = find_project_dir()
    hub_dir = find_hub()

    header_note: str | None = None
    if hub_dir is not None:
        log_path = hub_dir / AI_LOG_FILENAME
    elif project_dir is not None:
        log_path = project_dir / AI_LOG_FILENAME
    else:
        log_path = Path.cwd() / AI_LOG_FILENAME
        header_note = "No project or hub found - run 'halyard init' or 'halyard set-hub'"

    project_slug = project_dir.name if project_dir is not None else None
    HalyardApp(log_path=log_path, project_slug=project_slug, header_note=header_note).run()


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
            console.print(f"    Today      ${s.today_spend:.2f} / ${s.today_limit:.2f}{mark}{pct}")
        else:
            console.print(f"    Today      ${s.today_spend:.2f}  [dim](no limit)[/dim]")
        # This month
        if s.month_limit is not None:
            over = s.month_spend > s.month_limit
            mark = "  [bold yellow]⚠ over[/]" if over else "  [green]✓[/]"
            pct = f" {s.month_spend / s.month_limit * 100:.0f}% used" if not over else ""
            console.print(f"    This month ${s.month_spend:.2f} / ${s.month_limit:.2f}{mark}{pct}")
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


# ---------------------------------------------------------------------------
# Org admin commands
# ---------------------------------------------------------------------------


@app.command(name="org-init")
def org_init(
    hub: Path = typer.Option(None, "--hub", help="Hub directory (defaults to current project)."),
    org_id: str = typer.Option(..., "--org-id", help="Org slug, e.g. acme-corp."),
    org_name: str = typer.Option("", "--name", help="Human-readable org name."),
) -> None:
    """Create a starter org.toml at the hub (or current project directory)."""
    from halyard.ai_log import find_project_dir
    from halyard.hub import find_hub

    target = hub or find_project_dir() or find_hub()
    if target is None:
        console.print("[bold red]No project or hub found.[/] Pass --hub or run from a project dir.")
        raise typer.Exit(code=1)

    org_toml_path = target / "org.toml"
    if org_toml_path.exists():
        console.print(f"[yellow]org.toml already exists at {org_toml_path}[/]")
        raise typer.Exit(code=1)

    org_toml_path.write_text(
        f'[org]\nid = "{org_id}"\nname = "{org_name or org_id}"\n\n'
        '# [[department]]\n# id = "engineering"\n# name = "Engineering"\n\n'
        '# [[team]]\n# id = "auth-team"\n# name = "Auth"\n# department_id = "engineering"\n\n'
        '# [[member]]\n# email = "alice@example.com"\n# team_id = "auth-team"\n'
        '# display_name = "Alice"\n'
    )
    console.print(f"Created [bold cyan]{org_toml_path}[/]")
    console.print("Edit org.toml to add departments, teams, and members.")


@app.command(name="sync")
def sync_cmd(
    hub: Path = typer.Option(None, "--hub", help="Hub directory containing org.toml and org.db."),
    project: Path = typer.Option(None, "--project", help="Project dir to sync (default: CWD)."),
    all_projects: bool = typer.Option(False, "--all", help="Sync all projects under hub."),
) -> None:
    """Push local ai-sessions.log records to the org store."""
    from halyard.ai_log import find_project_dir
    from halyard.hub import find_hub
    from halyard.sync import sync_hub, sync_project

    effective_hub = hub or find_hub()

    if all_projects:
        if effective_hub is None:
            console.print("[bold red]No hub configured.[/] Pass --hub or run `halyard hub set`.")
            raise typer.Exit(code=1)
        result = sync_hub(effective_hub)
    else:
        project_dir = project or find_project_dir() or effective_hub
        if project_dir is None:
            console.print("[bold red]No project directory found.[/] Pass --project.")
            raise typer.Exit(code=1)
        result = sync_project(project_dir, hub_dir=effective_hub)

    if result.errors:
        for err in result.errors:
            console.print(f"[bold red]Error:[/] {err}")
        if result.inserted == 0:
            raise typer.Exit(code=1)

    console.print(
        f"Sync complete — [bold green]{result.inserted}[/] inserted, "
        f"[dim]{result.skipped}[/] already synced"
    )


@app.command(name="org-report")
def org_report(
    view: str = typer.Argument(
        "summary",
        help="View: summary | teams | projects | people | governance | finance",
    ),
    period: str = typer.Option(None, "--period", help="Billing period YYYY-MM (default: current)."),
    team: str = typer.Option(None, "--team", help="Filter by team ID."),
    project_filter: str = typer.Option(None, "--project", help="Filter by project ID."),
    hub: Path = typer.Option(None, "--hub", help="Hub directory."),
    csv_out: Path = typer.Option(None, "--csv", help="Write CSV to this file (finance view)."),
) -> None:
    """Show org admin dashboard views."""
    from halyard.ai_log import find_project_dir
    from halyard.hub import find_hub
    from halyard.org import read_org_config
    from halyard.org_reports import (
        export_finance_csv,
        print_finance_table,
        print_governance,
        print_org_summary,
        print_people_rollup,
        print_project_rollup,
        print_team_rollup,
    )
    from halyard.org_store import ORG_DB_FILENAME

    effective_hub = hub or find_hub() or find_project_dir()
    if effective_hub is None:
        console.print("[bold red]No hub found.[/] Pass --hub.")
        raise typer.Exit(code=1)

    org_config = read_org_config(effective_hub)
    if org_config is None:
        console.print(f"[bold red]No org.toml at {effective_hub}.[/] Run `halyard org-init` first.")
        raise typer.Exit(code=1)

    db_path = effective_hub / ORG_DB_FILENAME

    # parse --period
    now = datetime.now()
    if period:
        try:
            year, month = int(period[:4]), int(period[5:7])
        except (ValueError, IndexError):
            console.print("[bold red]Invalid --period format.[/] Use YYYY-MM.")
            raise typer.Exit(code=1) from None
    else:
        year, month = now.year, now.month

    org_id = org_config.org.id

    if view == "summary":
        print_org_summary(db_path, org_id, year, month)
    elif view == "teams":
        print_team_rollup(db_path, org_id, year, month, team_id=team)
    elif view == "projects":
        print_project_rollup(db_path, org_id, year, month, project_id=project_filter, team_id=team)
    elif view == "people":
        print_people_rollup(db_path, org_id, year, month, team_id=team)
    elif view == "governance":
        print_governance(db_path, org_id, year, month)
    elif view == "finance":
        if csv_out:
            csv_text = export_finance_csv(db_path, org_id, year, month, hub_dir=effective_hub)
            if csv_text:
                csv_out.write_text(csv_text)
                console.print(f"Exported to [bold cyan]{csv_out}[/]")
            else:
                console.print("[yellow]No data to export.[/]")
        else:
            print_finance_table(db_path, org_id, year, month, hub_dir=effective_hub)
    else:
        console.print(
            f"[bold red]Unknown view '{view}'.[/] "
            "Choose: summary, teams, projects, people, governance, finance"
        )
        raise typer.Exit(code=1)


@app.command(name="org-audit")
def org_audit(
    hub: Path = typer.Option(None, "--hub", help="Hub directory."),
    limit: int = typer.Option(50, "--limit", help="Number of recent audit events to show."),
) -> None:
    """Show the sync audit log."""
    from rich.table import Table

    from halyard.ai_log import find_project_dir
    from halyard.hub import find_hub
    from halyard.org import read_org_config
    from halyard.org_store import ORG_DB_FILENAME, read_sync_audit

    effective_hub = hub or find_hub() or find_project_dir()
    if effective_hub is None:
        console.print("[bold red]No hub found.[/] Pass --hub.")
        raise typer.Exit(code=1)
    org_config = read_org_config(effective_hub)
    if org_config is None:
        console.print(f"[bold red]No org.toml at {effective_hub}.[/]")
        raise typer.Exit(code=1)
    db_path = effective_hub / ORG_DB_FILENAME
    rows = read_sync_audit(db_path, org_config.org.id, limit=limit)
    if not rows:
        console.print("[yellow]No audit events recorded yet.[/]")
        return
    t = Table("When", "By", "Event", "Inserted", "Skipped", "Source", box=None, padding=(0, 2))
    for r in rows:
        t.add_row(
            r["synced_at"][:19],
            r["synced_by"],
            r["event"],
            str(r["inserted"]),
            str(r["skipped"]),
            r.get("source_path", ""),
        )
    console.print(t)


@app.command(name="org-purge-user")
def org_purge_user(
    user_id: str = typer.Argument(..., help="User email to purge from the org store."),
    hub: Path = typer.Option(None, "--hub", help="Hub directory."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Permanently delete a user's session records from the org store (GDPR removal)."""
    import getpass

    from halyard.ai_log import find_project_dir
    from halyard.hub import find_hub
    from halyard.org import read_org_config
    from halyard.org_store import ORG_DB_FILENAME, purge_user

    effective_hub = hub or find_hub() or find_project_dir()
    if effective_hub is None:
        console.print("[bold red]No hub found.[/] Pass --hub.")
        raise typer.Exit(code=1)
    org_config = read_org_config(effective_hub)
    if org_config is None:
        console.print(f"[bold red]No org.toml at {effective_hub}.[/]")
        raise typer.Exit(code=1)

    if not yes:
        console.print(
            f"[bold yellow]This will permanently delete all org session records for[/] "
            f"[bold]{user_id}[/] from [bold]{org_config.org.id}[/].\n"
            "The user's local ai-sessions.log is NOT affected."
        )
        confirm = typer.prompt("Type the user email to confirm", default="")
        if confirm != user_id:
            console.print("[yellow]Aborted.[/]")
            raise typer.Exit()

    try:
        purged_by = getpass.getuser()
    except Exception as e:
        from halyard.ai_log import _log_error
        _log_error("getpass.getuser failed in org-purge", e)
        purged_by = "unknown"

    db_path = effective_hub / ORG_DB_FILENAME
    count = purge_user(db_path, org_config.org.id, user_id, purged_by=purged_by)
    console.print(
        f"Purged [bold]{count}[/] session record(s) for [bold cyan]{user_id}[/]. "
        "Logged to audit trail."
    )


if __name__ == "__main__":
    app()
