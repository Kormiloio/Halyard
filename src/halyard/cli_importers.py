"""halyard importers — Codex, Copilot, and Gemini session history import sub-commands."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def run_gemini_import(*, dry_run: bool, all_projects: bool, quiet: bool = False) -> int:
    """Import Gemini CLI sessions; return the number imported.

    Shared by the ``import-gemini`` command and ``import-all``. Idempotent —
    sessions already recorded with a ``gemini:<id>`` job_id are skipped.
    ``quiet`` suppresses per-session lines (used by the batch ``import-all``).
    """
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

    if all_projects:
        session_files = find_all_session_files()
    else:
        cwd = Path.cwd()
        project_dir = find_project_dir(start=cwd)
        from halyard.collectors.gemini_history import _GEMINI_HISTORY, _GEMINI_TMP

        session_files = []
        if project_dir:
            for slug_dir in _GEMINI_HISTORY.glob("*"):
                pr = slug_dir / ".project_root"
                if pr.exists():
                    try:
                        if (
                            Path(pr.read_text(encoding="utf-8").strip()).resolve()
                            == project_dir.resolve()
                        ):
                            chats_dir = _GEMINI_TMP / slug_dir.name / "chats"
                            session_files.extend(chats_dir.glob("session-*.json"))
                            session_files.extend(chats_dir.glob("session-*.jsonl"))
                    except Exception as e:
                        from halyard.ai_log import _log_error

                        _log_error("reading gemini .project_root failed", e)
                        console.print(
                            f"[yellow]Warning:[/] could not read Gemini project root "
                            f"({type(e).__name__}). See ~/.halyard/halyard.log."
                        )
        if not session_files:
            session_files = find_all_session_files()

    if not session_files:
        if not quiet:
            console.print("[yellow]No Gemini session files found.[/]")
        return 0

    hub = find_hub()

    # Dedup against the dir each session actually routes to (cwd-independent),
    # cached per dir. The previous global set was built only from the current
    # project + hub, so a run from a different working directory (e.g. a
    # launchd-scheduled run) failed to see existing rows in per-slug project
    # logs and re-imported them, creating duplicates on every run.
    dedup_cache: dict[Path, set[str]] = {}

    def _existing_gemini_ids(target: Path) -> set[str]:
        rd = target.resolve()
        cached = dedup_cache.get(rd)
        if cached is None:
            cached = set()
            if (target / AI_LOG_FILENAME).exists():
                # Collect BOTH id forms, mirroring ai_log._gemini_session_key.
                # parse_sessions collapses each gemini session to one
                # canonical row at read time, and when hook rows exist the
                # better-attributed hook row wins — exposing session_id, not
                # the importer's job_id. Reading job_id alone made every
                # hook-covered session invisible to this dedup, so each run
                # re-imported it and collapse re-hid the evidence: an
                # unbounded append loop on the 30-minute timer (v5.21; the
                # repaired Halyard ledger had accumulated ~447 such rows).
                for s in parse_sessions(target):
                    if s.tool != "gemini-cli":
                        continue
                    if s.session_id:
                        cached.add(s.session_id)
                    if s.job_id and s.job_id.startswith("gemini:"):
                        cached.add(s.job_id[len("gemini:") :])
            dedup_cache[rd] = cached
        return cached

    imported: list[AiSession] = []
    skipped = 0

    for path in sorted(session_files):
        summary = parse_session_file(path)
        if summary is None:
            continue

        slug = path.parent.parent.name
        pd = project_dir_for_slug(slug)
        target_dir = pd if pd and (pd / "halyard.toml").exists() else hub

        if target_dir is None:
            if not quiet:
                console.print(f"  [dim]skip {summary.session_id[:8]} — no project dir or hub[/dim]")
            continue

        if summary.session_id in _existing_gemini_ids(target_dir):
            skipped += 1
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

        if not quiet:
            label = "[dim](dry run)[/dim] " if dry_run else ""
            console.print(
                f"  {label}{session.start:%Y-%m-%d %H:%M}  "
                f"[cyan]{session.model}[/]  "
                f"in={session.input_tokens:,} out={session.output_tokens:,}  "
                f"${session.cost_usd:.4f}  [dim]{slug}[/dim]"
            )

        if not dry_run:
            append_session(target_dir, session)
            _existing_gemini_ids(target_dir).add(summary.session_id)

    if not imported:
        if not quiet:
            console.print("[yellow]No new Gemini sessions to import.[/]")
        return 0

    if not quiet:
        label = "[dim](dry run)[/dim] " if dry_run else ""
        console.print(
            f"\n{label}[bold green]{'Would import' if dry_run else 'Imported'}[/] "
            f"{len(imported)} Gemini session(s). "
            f"({skipped} already imported, skipped.)"
        )
    return len(imported)


def register(app: typer.Typer) -> None:
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
        run_gemini_import(dry_run=dry_run, all_projects=all_projects)

    @app.command(name="import-claude")
    def import_claude(
        dry_run: bool = typer.Option(
            False, "--dry-run", help="Show what would be imported without writing anything."
        ),
        all_projects: bool = typer.Option(
            False,
            "--all",
            help="Import sessions for all Halyard projects, not just the current one.",
        ),
    ) -> None:
        """Import Claude Code session history into ai-sessions.log."""
        from halyard.ai_log import find_project_dir
        from halyard.collectors.claude_code import import_claude_sessions

        project_dir = find_project_dir()
        if project_dir is None and not all_projects:
            console.print(
                "[bold red]Error:[/] No Halyard project found. "
                "Run [bold]halyard init[/] first or use [bold]--all[/]."
            )
            raise typer.Exit(code=1)

        sessions = import_claude_sessions(
            project_dir=project_dir,
            dry_run=dry_run,
            all_projects=all_projects,
        )

        if not sessions:
            console.print("[yellow]No new Claude Code sessions to import.[/]")
            return

        label = "[dim](dry run)[/dim] " if dry_run else ""
        console.print(f"{label}[bold green]Imported[/] {len(sessions)} Claude Code session(s).")
        for s in sessions:
            proj = s.project or "(unattributed)"
            console.print(
                f"  {s.start:%Y-%m-%d %H:%M} → {s.end:%H:%M}  "
                f"[cyan]{s.model}[/]  out={s.output_tokens}  "
                f"[dim]{proj}[/dim]"
            )

    @app.command(name="import-all")
    def import_all(
        dry_run: bool = typer.Option(
            False, "--dry-run", help="Show what would be imported without writing anything."
        ),
    ) -> None:
        """Run every importer (Codex, Copilot, Gemini, Claude) across all projects.

        Idempotent — already-imported sessions are skipped — so it is safe to
        run on a schedule to keep importer-based tools current.
        """
        from halyard.ai_log import find_project_dir
        from halyard.collectors.claude_code import import_claude_sessions
        from halyard.collectors.codex_app import import_codex_sessions
        from halyard.collectors.copilot import import_copilot_sessions

        project_dir = find_project_dir()
        codex = import_codex_sessions(project_dir=project_dir, dry_run=dry_run, all_projects=True)
        copilot = import_copilot_sessions(
            project_dir=project_dir, dry_run=dry_run, all_projects=True
        )
        claude = import_claude_sessions(project_dir=project_dir, dry_run=dry_run, all_projects=True)
        gemini_n = run_gemini_import(dry_run=dry_run, all_projects=True, quiet=True)

        label = "(dry run) " if dry_run else ""
        console.print(
            f"[bold green]{label}import-all:[/] "
            f"Codex {len(codex)}, Copilot {len(copilot)}, Gemini {gemini_n}, "
            f"Claude {len(claude)} session(s)."
        )

    @app.command(name="install-import-timer")
    def install_import_timer_cmd(
        interval_minutes: int = typer.Option(
            30, "--interval", help="Minutes between scheduled imports.", min=5
        ),
    ) -> None:
        """Schedule `halyard import-all` via a macOS LaunchAgent (keeps Codex/
        Copilot/Gemini fresh). First run bulk-imports existing on-disk history."""
        if sys.platform != "darwin":
            console.print("[yellow]Scheduled import currently supports macOS (launchd) only.[/]")
            raise typer.Exit(code=1)
        from halyard.import_timer import install_import_timer

        path = install_import_timer(interval_seconds=interval_minutes * 60)
        console.print(
            f"[bold green]Scheduled[/] import-all every {interval_minutes} min.\n"
            f"  agent: {path}\n"
            f"  stop:  halyard uninstall-import-timer"
        )

    @app.command(name="uninstall-import-timer")
    def uninstall_import_timer_cmd() -> None:
        """Remove the scheduled-import LaunchAgent."""
        if sys.platform != "darwin":
            console.print("[yellow]Scheduled import currently supports macOS (launchd) only.[/]")
            raise typer.Exit(code=1)
        from halyard.import_timer import uninstall_import_timer

        uninstall_import_timer()
        console.print("[bold green]Removed[/] the scheduled-import LaunchAgent.")

    @app.command(name="import-copilot")
    def import_copilot(
        dry_run: bool = typer.Option(
            False, "--dry-run", help="Show what would be imported without writing anything."
        ),
        all_projects: bool = typer.Option(
            False,
            "--all",
            help="Import sessions for all Halyard projects, not just the current one.",
        ),
    ) -> None:
        """Import GitHub Copilot session history into ai-sessions.log."""
        from halyard.ai_log import find_project_dir
        from halyard.collectors.copilot import import_copilot_sessions

        project_dir = find_project_dir()
        if project_dir is None and not all_projects:
            console.print(
                "[bold red]Error:[/] No Halyard project found. "
                "Run [bold]halyard init[/] first or use [bold]--all[/]."
            )
            raise typer.Exit(code=1)

        sessions = import_copilot_sessions(
            project_dir=project_dir,
            dry_run=dry_run,
            all_projects=all_projects,
        )

        if not sessions:
            console.print("[yellow]No new Copilot sessions to import.[/]")
            return

        label = "[dim](dry run)[/dim] " if dry_run else ""
        console.print(f"{label}[bold green]Imported[/] {len(sessions)} Copilot session(s).")
        for s in sessions:
            proj = s.project or "(unattributed)"
            console.print(
                f"  {s.start:%Y-%m-%d %H:%M} → {s.end:%H:%M}  "
                f"[cyan]{s.model}[/]  out={s.output_tokens}  "
                f"[dim]{proj}[/dim]"
            )
