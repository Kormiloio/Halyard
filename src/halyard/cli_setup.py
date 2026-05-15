"""halyard setup — project initialisation and first-run setup sub-commands."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def register(app: typer.Typer) -> None:
    @app.command()
    def init(
        hub: bool = typer.Option(
            False, "--hub", help="Also designate this directory as the global hub for all tools."
        ),
        no_interactive: bool = typer.Option(
            False,
            "--no-interactive",
            help="Skip hook auto-installation and any future interactive prompts. "
            "Use in CI or unattended setup.",
        ),
    ) -> None:
        """Scaffold a new Halyard project in the current directory."""
        from halyard.cli_hooks import _auto_install_detected_hooks
        from halyard.orchestration import scaffold_project

        scaffold_project(Path.cwd(), hub=hub)
        if not no_interactive:
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
        from typing import Any, cast

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
        from halyard.cli_hooks import (
            _do_install_hook_claude,
            _do_install_hook_cursor,
            _do_install_hook_gemini,
        )
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
                        use_global = global_claude
                        if not use_global and not yes and sys.stdin.isatty():
                            use_global = typer.confirm(
                                "Do you work on more than one project?",
                                default=False,
                            )
                            if use_global:
                                console.print(
                                    "[dim]Installing globally — all Claude Code sessions "
                                    "will be captured regardless of working directory.[/]"
                                )
                            else:
                                console.print(
                                    "[dim]Installing for this project. "
                                    "Run [bold]halyard install-hook --global[/] "
                                    "to expand coverage later.[/]"
                                )
                        _do_install_hook_claude(global_=use_global)
                    elif selected == "cursor":
                        _do_install_hook_cursor()
                    elif selected == "gemini":
                        _do_install_hook_gemini()
                except OSError as exc:
                    install_errors.append(f"{tool_label(selected)}: {exc}")
                    console.print(
                        f"[bold red]Could not install {tool_label(selected)} hooks:[/] {exc}"
                    )

        report = build_doctor_report()
        console.print("")
        console.print(render_text(report))
        console.print("")
        console.print(f"[bold green]{next_step_text()}[/]")
        if install_errors:
            raise typer.Exit(code=1)

    @app.command(name="adopt")
    def adopt_cmd(
        path: str = typer.Argument(
            ".", metavar="PATH", help="Directory to adopt (default: current directory)."
        ),
        slug: str | None = typer.Option(None, "--slug", help="Project slug (skips prompt)."),
        yes: bool = typer.Option(
            False, "--yes", "-y", help="Accept suggested slug without prompting."
        ),
    ) -> None:
        """Promote an auto-tracked directory to a named Halyard project.

        Creates a minimal halyard.toml with [project].slug so future sessions
        are attributed to the chosen slug instead of the generic git/<repo-name>
        auto-slug.  Also wires up repos.toml so the git remote maps to the same
        slug on machines without a local halyard.toml.
        """
        from halyard.git_context import _extract_repo_name, _git_remote_url, register_repo
        from halyard.registry import add_project

        target = Path(path).resolve()

        if not target.is_dir():
            console.print(f"[bold red]Error:[/] {target} is not a directory.")
            raise typer.Exit(code=1)

        if (target / "halyard.toml").exists():
            console.print(
                "[bold red]Error:[/] halyard.toml already exists here.\n"
                "Use [bold]halyard init[/] to scaffold a full project, or edit the "
                "existing [bold]halyard.toml[/] directly."
            )
            raise typer.Exit(code=1)

        remote = _git_remote_url(target)
        repo_name = _extract_repo_name(remote) if remote else None
        current_auto_slug = f"git/{repo_name}" if repo_name else None

        if current_auto_slug:
            console.print(
                f"Sessions from this directory are currently tracked as "
                f"[dim]{current_auto_slug}[/]"
            )
        else:
            console.print(
                "[dim]No git remote — slug will be used for path-based attribution only.[/]"
            )

        suggested = repo_name or target.name

        if slug is None:
            if yes or not sys.stdin.isatty():
                slug = suggested
            else:
                slug = typer.prompt("Project slug", default=suggested)

        slug = slug.strip()
        if not slug:
            console.print("[bold red]Error:[/] slug cannot be empty.")
            raise typer.Exit(code=1)

        toml_content = f'[project]\nslug = "{slug}"\n'
        (target / "halyard.toml").write_text(toml_content)

        if remote:
            register_repo(remote, slug)

        add_project(target)

        console.print(f"\n[bold green]Adopted[/] [bold]{target}[/] → [bold]{slug}[/]")
        if current_auto_slug and current_auto_slug != slug:
            console.print(
                f"[dim]Future sessions will be attributed to [bold]{slug}[/]. "
                f"Existing hub sessions remain under [bold]{current_auto_slug}[/] — "
                f"run [bold]halyard reattribute {current_auto_slug} {slug}[/] to migrate them.[/]"
            )
        if remote:
            console.print(f"[dim]repos.toml updated: {remote} → {slug}[/]")

    @app.command(name="link-repo")
    def link_repo(
        project: str = typer.Argument(
            ..., help="Project slug (client:project) to map this repo to."
        ),
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
