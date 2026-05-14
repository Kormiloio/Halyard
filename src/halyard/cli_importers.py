"""halyard importers — Codex and Gemini session history import sub-commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

console = Console()


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
                session_files = find_all_session_files()

        if not session_files:
            console.print("[yellow]No Gemini session files found.[/]")
            return

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

            slug = path.parent.parent.name
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
