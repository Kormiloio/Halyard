"""halyard setup — project initialisation and first-run setup sub-commands."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

console = Console()

# A project slug is written verbatim into halyard.toml as a quoted string;
# restrict it so it cannot inject TOML or path separators that escape it.
_SLUG_RE = re.compile(r"^[A-Za-z0-9._:/-]+$")


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
        from halyard.cli_hooks import (
            _auto_install_detected_hooks,
            _auto_install_detected_mcp,
        )
        from halyard.orchestration import scaffold_project

        scaffold_project(Path.cwd(), hub=hub)
        if not no_interactive:
            _auto_install_detected_hooks()
            _auto_install_detected_mcp()

    # NOTE: the hub directory setter lives in cli_hub as `halyard hub set`.
    # A bare `hub` command was registered here until v5.29, but cli.py adds
    # the cli_hub sub-app under the same name afterwards, so it was silently
    # shadowed and unreachable — while doctor still advertised it as the fix
    # for "no hub configured". Do not re-add a `hub` command here.

    @app.command(name="doctor")
    def doctor_cmd(
        json_: bool = typer.Option(False, "--json", help="Write machine-readable JSON."),
        first_capture: bool = typer.Option(
            False,
            "--first-capture",
            help="Verify that a recent AI session was captured somewhere.",
        ),
        tool: str = typer.Option(
            "all", "--tool", help="claude | cursor | gemini | windsurf | copilot | all"
        ),
    ) -> None:
        """Diagnose Halyard setup, hooks, logs, and first-capture readiness."""
        from typing import Any, cast

        from halyard.doctor import build_doctor_report, has_errors, render_json, render_text

        if tool not in {"claude", "cursor", "gemini", "windsurf", "copilot", "all"}:
            console.print(
                "[bold red]Error:[/] --tool must be one of: "
                "claude, cursor, gemini, windsurf, copilot, all"
            )
            raise typer.Exit(code=1)

        report = build_doctor_report(tool=cast(Any, tool), first_capture=first_capture)
        if json_:
            sys.stdout.write(render_json(report))
        else:
            console.print(escape(render_text(report)))

        if has_errors(report):
            raise typer.Exit(code=1)

    @app.command(name="setup")
    def setup_cmd(
        all_tools: bool = typer.Option(False, "--all", help="Install all supported hooks."),
        claude: bool = typer.Option(False, "--claude", help="Install Claude Code hooks."),
        cursor: bool = typer.Option(False, "--cursor", help="Install Cursor hooks."),
        gemini: bool = typer.Option(False, "--gemini", help="Install Gemini CLI hooks."),
        windsurf: bool = typer.Option(False, "--windsurf", help="Install Windsurf hooks."),
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
            _do_install_hook_windsurf,
            _do_install_mcp,
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
            windsurf=windsurf,
            yes=yes,
        )

        tools = list(selection.tools)
        if not tools and not yes:
            for candidate in ("claude", "cursor", "gemini", "windsurf"):
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
                    elif selected == "windsurf":
                        _do_install_hook_windsurf()
                    _do_install_mcp(selected)
                except OSError as exc:
                    install_errors.append(f"{tool_label(selected)}: {exc}")
                    console.print(
                        f"[bold red]Could not install {tool_label(selected)} hooks:[/] {exc}"
                    )

        report = build_doctor_report()
        console.print("")
        console.print(escape(render_text(report)))
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
                f"Sessions from this directory are currently tracked as [dim]{current_auto_slug}[/]"
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
        if not _SLUG_RE.match(slug):
            console.print(
                "[bold red]Error:[/] invalid slug. Use only letters, digits, "
                "and the characters . _ : / -"
            )
            raise typer.Exit(code=1)

        toml_content = f'[project]\nslug = "{slug}"\n'
        (target / "halyard.toml").write_text(toml_content, encoding="utf-8")

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

    @app.command(name="reattribute")
    def reattribute(
        source: str = typer.Argument(..., help="Existing slug to migrate from (e.g. git/Halyard)."),
        canonical: str = typer.Argument(..., help="Canonical slug to migrate to."),
        apply: bool = typer.Option(False, "--apply", help="Write the alias."),
    ) -> None:
        """Map an old project slug onto a canonical one.

        v5.36: `halyard adopt` has told users to run this since it shipped,
        but the command did not exist — the message named a fix that could
        not be run. One logical project therefore stayed split across the
        slug forms it accumulated as attribution improved
        (`git/Halyard` and `kormilo:halyard` were observed side by side,
        25 and 30 sessions of the same work).

        This records a read-time alias. The ledger is append-only and is
        never rewritten: `canonical_project` resolves the old slug on every
        read, so history reports under one identity without rewriting
        history. Dry-run by default, because an alias silently moves
        billable sessions between projects.
        """
        from halyard.ai_log import find_project_dir, parse_sessions
        from halyard.attribution import canonical_project, load_project_aliases, set_project_alias
        from halyard.hub import find_hub

        if source == canonical:
            console.print("[bold red]Error:[/] source and canonical are the same slug.")
            raise typer.Exit(code=1)

        target = find_project_dir() or find_hub()
        affected = 0
        if target is not None:
            aliases = load_project_aliases(target)
            affected = sum(
                1 for s in parse_sessions(target) if canonical_project(s.project, aliases) == source
            )

        if not apply:
            console.print(f"[bold]{source}[/] → [bold]{canonical}[/]")
            console.print(f"  {affected} session(s) would report under [bold]{canonical}[/].")
            console.print(
                "\n[dim]Read-time only — the ledger is not rewritten.[/]\n"
                "[yellow]Dry run.[/] Re-run with [bold]--apply[/] to record the alias."
            )
            return

        set_project_alias(source, canonical)
        console.print(f"[bold green]Aliased[/] [dim]{source}[/] → [bold]{canonical}[/]")
        console.print(f"  {affected} session(s) now report under [bold]{canonical}[/].")

    @app.command(name="link-path")
    def link_path(
        path: str = typer.Argument(..., help="Recorded directory to map (as the tool saw it)."),
        project: str = typer.Argument(..., help="Project slug (client:project)."),
        apply: bool = typer.Option(False, "--apply", help="Write the mapping."),
    ) -> None:
        """Map a recorded session directory to a project.

        v5.39. `link-repo` matches on git *remotes*, which imported sessions
        do not carry — they record the directory they ran in. That directory
        may since have moved, or may be a repository's parent, and either way
        yields no remote, so the session is unattributable no matter how many
        remotes are mapped.

        Resolution is read-time: the ledger is append-only and is never
        rewritten, so mapping a path attributes existing history as well as
        future imports. Dry-run by default, since attribution moves billable
        sessions between projects.
        """
        from halyard.ai_log import find_project_dir, parse_sessions
        from halyard.git_context import register_path
        from halyard.hub import find_hub

        target = find_project_dir() or find_hub()
        affected = 0
        if target is not None:
            affected = sum(
                1 for s in parse_sessions(target) if s.source_path == path and not s.project
            )

        if not apply:
            console.print(f"[bold]{path}[/] → [bold]{project}[/]")
            console.print(f"  {affected} unattributed session(s) would resolve to {project}.")
            console.print(
                "\n[dim]Read-time only — the ledger is not rewritten.[/]\n"
                "[yellow]Dry run.[/] Re-run with [bold]--apply[/] to write the mapping."
            )
            return

        register_path(path, project)
        console.print(f"[bold green]Mapped[/] [dim]{path}[/] → [bold]{project}[/]")
        console.print(f"  {affected} session(s) now resolve to {project}.")

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
        # v5.36: link-repo fixes attribution forward only. Existing rows keep
        # whatever slug they were written with, so one project stays split
        # until an alias is recorded. `adopt` says this; link-repo did not.
        console.print(
            "[dim]Existing sessions keep their current slug — "
            f"run [bold]halyard reattribute <old-slug> {project}[/] to migrate them.[/]"
        )
