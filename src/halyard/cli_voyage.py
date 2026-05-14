"""halyard voyage — Friends of the Sea lifecycle sub-commands."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console()

app = typer.Typer(name="voyage", help="Manage project voyage lifecycle and sea creatures.")


@app.callback(invoke_without_command=True)
def voyage_list(ctx: typer.Context) -> None:
    """List all project voyages with stage, progress, and creature."""
    if ctx.invoked_subcommand is not None:
        return

    from halyard.ai_log import AiSession, find_project_dir, parse_sessions
    from halyard.hub import find_hub
    from halyard.voyages import STAGE_LABELS, build_voyage_summaries, check_auto_complete

    project_dir = find_project_dir() or find_hub()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    sessions = parse_sessions(project_dir)
    sessions_by_project: dict[str, list[AiSession]] = {}
    for s in sessions:
        if s.project:
            sessions_by_project.setdefault(s.project, []).append(s)

    check_auto_complete(project_dir, sessions_by_project)
    summaries = build_voyage_summaries(project_dir, sessions_by_project)

    if not summaries:
        console.print("[dim]No voyages yet. Attribute sessions to projects to begin.[/]")
        return

    console.print("\n[bold]⛵  Friends of the Sea · Voyages[/]\n")
    for v in summaries:
        creature = v.creature or "·"
        label = STAGE_LABELS.get(v.stage, v.stage)
        bar_filled = min(20, round(20 * v.session_count / max(v.target_sessions, 1)))
        bar = "▓" * bar_filled + "░" * (20 - bar_filled)
        if v.stage == "moored":
            console.print(
                f"  {creature}  [bold]{v.slug}[/]  [green]{label}[/]"
                + (f"  [dim]{v.creature_trait}[/]" if v.creature_trait else "")
            )
        else:
            console.print(
                f"  {creature}  [bold]{v.slug}[/]  [cyan]{label}[/]  "
                f"[dim]{v.session_count}/{v.target_sessions}[/]"
            )
            console.print(f"       {bar}", style="dim")
    console.print()


@app.command(name="complete")
def voyage_complete(
    project: str = typer.Argument(..., help="Project slug to mark complete."),
) -> None:
    """Manually mark a project voyage as complete (Shipshape · Moored)."""
    from datetime import date

    from halyard.ai_log import AiSession, find_project_dir, parse_sessions
    from halyard.hub import find_hub
    from halyard.voyages import (
        _had_concurrent_projects,
        assign_creature,
        read_voyages,
        voyage_for_slug,
        write_voyages,
    )

    project_dir = find_project_dir() or find_hub()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    sessions = parse_sessions(project_dir)
    project_sessions = [s for s in sessions if s.project == project]

    entries = read_voyages(project_dir)
    entry = voyage_for_slug(entries, project)

    if entry.stage == "moored":
        console.print(
            f"[yellow]{project}[/] is already moored  {entry.creature}  {entry.creature_trait}"
        )
        raise typer.Exit()

    all_completed = {
        e.slug: len([s for s in sessions if s.project == e.slug])
        for e in entries
        if e.stage == "moored"
    }
    all_completed[project] = len(project_sessions)

    sessions_by_project: dict[str, list[AiSession]] = {}
    for s in sessions:
        if s.project:
            sessions_by_project.setdefault(s.project, []).append(s)
    coral_reef = _had_concurrent_projects(sessions_by_project, project)

    emoji, trait = assign_creature(project, project_sessions, all_completed, coral_reef=coral_reef)
    today = date.today().isoformat()
    started = project_sessions[0].start.strftime("%Y-%m-%d") if project_sessions else ""

    entry.stage = "moored"
    entry.started_at = entry.started_at or started
    entry.completed_at = today
    entry.creature = emoji
    entry.creature_trait = trait

    slug_map = {e.slug: e for e in entries}
    slug_map[project] = entry
    write_voyages(project_dir, list(slug_map.values()))

    console.print(
        f"\n[bold green]Shipshape · Moored![/]  {emoji}  [bold]{project}[/]  [dim]{trait}[/]\n"
    )


@app.command(name="set")
def voyage_set(
    project: str = typer.Argument(..., help="Project slug."),
    sessions: int | None = typer.Option(None, "--sessions", help="Session budget target."),
    inactivity: int | None = typer.Option(
        None, "--inactivity", help="Days of inactivity before auto-complete."
    ),
) -> None:
    """Edit voyage settings — session budget and inactivity threshold."""
    from halyard.ai_log import find_project_dir
    from halyard.hub import find_hub
    from halyard.voyages import read_voyages, voyage_for_slug, write_voyages

    if sessions is None and inactivity is None:
        console.print("[yellow]No changes specified. Use --sessions or --inactivity.[/]")
        raise typer.Exit()

    project_dir = find_project_dir() or find_hub()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
        )
        raise typer.Exit(code=1)

    entries = read_voyages(project_dir)
    entry = voyage_for_slug(entries, project)

    if sessions is not None:
        if sessions < 1:
            console.print("[bold red]Error:[/] --sessions must be ≥ 1.")
            raise typer.Exit(code=1)
        entry.target_sessions = sessions

    if inactivity is not None:
        if inactivity < 1:
            console.print("[bold red]Error:[/] --inactivity must be ≥ 1.")
            raise typer.Exit(code=1)
        entry.inactivity_days = inactivity

    slug_map = {e.slug: e for e in entries}
    slug_map[project] = entry
    write_voyages(project_dir, list(slug_map.values()))

    console.print(
        f"[bold]{project}[/]  target=[bold cyan]{entry.target_sessions}[/] sessions  "
        f"inactivity=[bold cyan]{entry.inactivity_days}[/] days"
    )
