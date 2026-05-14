"""halyard org — org admin, sync, and GDPR sub-commands."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def register(app: typer.Typer) -> None:
    @app.command(name="org-init")
    def org_init(
        hub: Path = typer.Option(
            None, "--hub", help="Hub directory (defaults to current project)."
        ),
        org_id: str = typer.Option(..., "--org-id", help="Org slug, e.g. acme-corp."),
        org_name: str = typer.Option("", "--name", help="Human-readable org name."),
    ) -> None:
        """Create a starter org.toml at the hub (or current project directory)."""
        from halyard.ai_log import find_project_dir
        from halyard.hub import find_hub

        target = hub or find_project_dir() or find_hub()
        if target is None:
            console.print(
                "[bold red]No project or hub found.[/] Pass --hub or run from a project dir."
            )
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
        hub: Path = typer.Option(
            None, "--hub", help="Hub directory containing org.toml and org.db."
        ),
        project: Path = typer.Option(
            None, "--project", help="Project dir to sync (default: CWD)."
        ),
        all_projects: bool = typer.Option(False, "--all", help="Sync all projects under hub."),
    ) -> None:
        """Push local ai-sessions.log records to the org store."""
        from halyard.ai_log import find_project_dir
        from halyard.hub import find_hub
        from halyard.sync import sync_hub, sync_project

        effective_hub = hub or find_hub()

        if all_projects:
            if effective_hub is None:
                console.print(
                    "[bold red]No hub configured.[/] Pass --hub or run `halyard hub set`."
                )
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
        period: str = typer.Option(
            None, "--period", help="Billing period YYYY-MM (default: current)."
        ),
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
            console.print(
                f"[bold red]No org.toml at {effective_hub}.[/] Run `halyard org-init` first."
            )
            raise typer.Exit(code=1)

        db_path = effective_hub / ORG_DB_FILENAME

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
            print_project_rollup(
                db_path, org_id, year, month, project_id=project_filter, team_id=team
            )
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
        t = Table(
            "When", "By", "Event", "Inserted", "Skipped", "Source", box=None, padding=(0, 2)
        )
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
