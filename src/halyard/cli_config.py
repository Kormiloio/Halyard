"""halyard config — rate history and invoice audit sub-commands."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console()

app = typer.Typer(name="config", help="Rate history and invoice audit commands.")


@app.command(name="history")
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


@app.command(name="audit")
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
