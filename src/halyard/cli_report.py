"""halyard report — reporting, analytics, dashboard, and pricing sub-commands."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NoReturn

import typer
from rich.console import Console

console = Console()
err_console = Console(stderr=True)


def _fail(json_: bool, message: str, code: int = 1) -> NoReturn:
    """Uniform command failure.

    With ``--json`` emit ``{"error": message}`` (to stdout, the JSON
    channel) so a programmatic consumer always gets a parseable
    object; otherwise print a human error to **stderr**, never stdout.
    Always raises ``typer.Exit(code)``.
    """
    if json_:
        from halyard.jsonio import emit

        emit({"error": message})
    else:
        err_console.print(f"[bold red]Error:[/] {message}")
    raise typer.Exit(code=code)


def register(app: typer.Typer) -> None:
    @app.command()
    def honors() -> None:
        """Display your service record — rank, stripes, and earned medals."""
        from rich.panel import Panel
        from rich.text import Text

        from halyard.achievements import RANKS, build_service_record
        from halyard.ai_log import find_project_dir, parse_sessions
        from halyard.hub import find_hub

        project_dir = find_project_dir() or find_hub()
        if project_dir is None:
            console.print(
                "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
            )
            raise typer.Exit(code=1)

        sessions = parse_sessions(project_dir)
        record = build_service_record(project_dir, sessions)
        rank = record.rank

        body = Text()
        body.append(f"  {rank.icon}  ", style="bold")
        body.append(f"{rank.name}\n", style="bold cyan")
        body.append(f"  {rank.flavor}\n", style="italic dim")
        body.append("\n")

        if record.next_rank:
            earned = record.attributed_sessions
            target = record.next_rank.sessions_required
            filled = min(20, round(20 * earned / max(target, 1)))
            bar = "▓" * filled + "░" * (20 - filled)
            body.append(f"  {bar}  ", style="bold")
            body.append(
                f"{earned} / {target} attributed sessions → {record.next_rank.name}\n",
                style="dim",
            )
        else:
            body.append("  ✦ Highest rank achieved ✦\n", style="bold gold1")

        body.append("\n")

        stripe_count = min(4, record.watch_streak // 7)
        body.append("  Stripes  ", style="bold")
        if stripe_count:
            body.append("▐" * stripe_count, style="bold cyan")
            body.append("  ", style="dim")
        body.append(f"  {record.watch_streak}-day watch streak", style="dim")
        if record.gold_stripe_earned:
            body.append("  ✦ gold stripe", style="bold gold1")
        body.append("\n")

        body.append(
            f"  Proof score  {record.proof_score}%  "
            f"({record.attributed_sessions}/{record.total_sessions} attributed)\n",
            style="dim",
        )

        console.print(
            Panel(
                body,
                title="[bold]⚓  Captain's Quarters · Service Record[/]",
                border_style="cyan",
                padding=(0, 1),
                expand=False,
            )
        )

        if record.passport:
            console.print("\n[dim]· — — ·  — — —  · — ·  —[/]  [bold]Passport · Ports of Call[/]")
            for stamp in record.passport:
                console.print(f"  {stamp.icon}  [bold]{stamp.name}[/]  [dim]{stamp.tool}[/]")
        else:
            console.print("\n[dim]Passport empty — capture sessions to earn stamps.[/]")

        if record.earned_medals:
            console.print("\n[dim]· · ·  — — —  · · ·[/]  [bold]Medals earned[/]")
            for medal in record.earned_medals:
                console.print(f"  {medal.icon}  [bold]{medal.name}[/]  [dim]{medal.description}[/]")
                console.print(f"     [dim italic]{medal.detail}[/]")
        else:
            console.print("\n[dim]No medals yet — complete watches to start earning honors.[/]")

        console.print("\n[dim]· — ·  · —  — ·  — · —[/]  [dim]All ranks:[/]")
        for r in RANKS[1:]:
            marker = "▶ " if r.level == rank.level else "  "
            style = "bold cyan" if r.level == rank.level else "dim"
            console.print(
                f"  {marker}{r.icon}  {r.name:<16}  {r.sessions_required} attributed sessions",
                style=style,
            )

    @app.command()
    def report(
        all_time: bool = typer.Option(
            False, "--all", help="Show all time instead of current month."
        ),
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
        outcomes: bool = typer.Option(False, "--outcomes", help="Show outcome bucket totals."),
        json_: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
        json_sessions: bool = typer.Option(
            False, "--json-sessions", help="With --json, include the per-session array."
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
            if json_:
                from halyard.jsonio import emit

                emit({"error": "No Halyard project found. Run 'halyard init' first."})
                raise typer.Exit(code=1)
            console.print(
                "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
            )
            raise typer.Exit(code=1)

        if not json_:
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

        now = datetime.now()
        if month:
            try:
                period = datetime.strptime(month, "%Y-%m")
            except ValueError:
                _fail(json_, "--month must be YYYY-MM (e.g. 2026-05).")
        else:
            period = now

        ai_report = build_filtered_ai_report(
            project_dir, project=project, client=client, all_time=all_time, now=period
        )
        human = build_human_time_report(project_dir, now=period)

        if json_:
            from halyard.attribution import attribution_mix
            from halyard.jsonio import emit

            payload: dict[str, object] = {
                "period_label": ai_report.period_label,
                "filter": {"project": project, "client": client},
                "totals": {
                    "cost_usd": round(ai_report.total_cost, 4),
                    "input_tokens": ai_report.total_input_tokens,
                    "output_tokens": ai_report.total_output_tokens,
                    "cache_read_tokens": ai_report.total_cache_read_tokens,
                    "cache_write_tokens": ai_report.total_cache_write_tokens,
                    "tool_calls": ai_report.total_tool_calls,
                    "tool_errors": ai_report.total_tool_errors,
                },
                "human_time": {
                    "month_minutes": human.month_minutes,
                    "today_minutes": human.today_minutes,
                },
                "by_project": ai_report.by_project,
                "by_model": ai_report.by_model,
                "by_tool": ai_report.by_tool,
                "by_tool_usage": ai_report.by_tool_usage,
                "attribution": attribution_mix(ai_report.sessions),
                "unattributed_count": ai_report.unattributed_count,
            }
            if json_sessions:
                payload["sessions"] = ai_report.sessions
            emit(payload)
            return

        filter_label = f" — {project or client}" if (project or client) else ""
        console.print(f"\n[bold]Report — {ai_report.period_label}{filter_label}[/]")
        console.print("─" * 48)

        if human.month_minutes:
            console.print(
                f"  Human time [bold cyan]{format_minutes(human.month_minutes)}[/]  this month"
                f"  (today: {format_minutes(human.today_minutes)})"
            )

        if not ai_report.sessions:
            console.print(f"  [yellow]No AI sessions recorded for {ai_report.period_label}.[/]")
            console.print(
                "\n  Run [bold]halyard install-hook[/] to start capturing sessions automatically."
            )
            console.print("─" * 48 + "\n")
            raise typer.Exit(code=0)

        console.print(f"  AI sessions  [bold]{len(ai_report.sessions)}[/]")
        console.print(f"  AI cost      [bold green]${ai_report.total_cost:.2f}[/]")
        if ai_report.total_input_tokens:
            console.print(
                f"  Tokens       in {ai_report.total_input_tokens:,}"
                f"  out {ai_report.total_output_tokens:,}"
            )

        if not all_time:
            from halyard.visuals import trail_heatmap

            console.print()
            console.print(trail_heatmap(ai_report.sessions, period))

        if not project and ai_report.by_project:
            console.print("\n[bold]By project[/]")
            for bucket in ai_report.by_project:
                console.print(
                    f"  {bucket.label:<32} [green]${bucket.cost_usd:.2f}[/]"
                    f"  {bucket.sessions} sessions"
                )

        if ai_report.by_model:
            console.print("\n[bold]By model[/]")
            for bucket in ai_report.by_model:
                console.print(
                    f"  {bucket.label:<32} [green]${bucket.cost_usd:.2f}[/]"
                    f"  {bucket.sessions} sessions"
                )

        if ai_report.by_tool_usage:
            console.print("\n[bold]By tool[/]")
            for tbucket in ai_report.by_tool_usage:
                tok_label = f"{tbucket.tokens:,} tokens  " if tbucket.tokens else ""
                console.print(
                    f"  {tbucket.tool:<32} [green]${tbucket.cost_usd:.2f}[/]"
                    f"  {tbucket.sessions} sessions  {tok_label}"
                )

        if ai_report.sessions:
            from halyard.attribution import format_attribution_mix

            console.print(f"\n[bold]Attribution[/]  {format_attribution_mix(ai_report.sessions)}")

        branch_sessions = [(s.branch, s) for s in ai_report.sessions if s.branch]
        if branch_sessions:
            from collections import Counter

            branch_counts = Counter(b for b, _ in branch_sessions)
            console.print("\n[bold]By branch[/]")
            for branch_name, count in branch_counts.most_common(10):
                branch_sessions_list = [s for b, s in branch_sessions if b == branch_name]
                commits = sum(s.commit_count or 0 for s in branch_sessions_list)
                added = sum(s.code_added or 0 for s in branch_sessions_list)
                meta = f"  [dim]{commits} commits  +{added} lines[/]" if commits or added else ""
                console.print(
                    f"  {branch_name:<32} [dim]{count} session{'s' if count != 1 else ''}[/]{meta}"
                )

        if outcomes:
            from halyard.ai_log import parse_sessions
            from halyard.outcomes import outcome_report

            all_sessions = parse_sessions(project_dir)
            buckets = outcome_report(all_sessions, project_slug=project)
            console.print("\n[bold]Outcome buckets[/]")
            for b in buckets:
                if b.session_count == 0:
                    continue
                cost_col = f"[green]${b.total_cost:.2f}[/]" if b.trust else "[dim]—[/]"
                plural = "s" if b.session_count != 1 else ""
                console.print(
                    f"  {b.label:<30} [bold]{b.session_count:>4}[/] session{plural}  {cost_col}"
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
                    ai_report.sessions,
                    plans,
                    tc_entries,
                    year=period.year,
                    month=period.month,
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
                    "\n[dim]No ai-plans.toml configured. "
                    "Add plans to see seat/credits allocation.[/]"
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
    def evidence(
        all_time: bool = typer.Option(
            False, "--all", help="All time instead of the current month."
        ),
        project: str | None = typer.Option(
            None, "--project", help="Filter to a project slug (client:project)."
        ),
        client: str | None = typer.Option(
            None, "--client", help="Filter to all projects for a client."
        ),
        month: str | None = typer.Option(
            None, "--month", help="Billing month as YYYY-MM. Defaults to current month."
        ),
        out: Path = typer.Option(
            None, "--out", help="Write the artifact to this path instead of stdout."
        ),
        force: bool = typer.Option(False, "--force", help="Overwrite an existing --out file."),
        verify: Path = typer.Option(
            None, "--verify", help="Verify an existing artifact's integrity digest and exit."
        ),
        json_: bool = typer.Option(
            False, "--json", help="Emit structured metrics (no digest) instead of the artifact."
        ),
    ) -> None:
        """Emit a standalone AI-work evidence artifact with an integrity digest.

        Unsigned and keyless: the digest is tamper-evident (anyone can
        re-hash the file) but is NOT a signature and does not prove
        authorship. Cryptographic attestation is a Halyard Enterprise
        feature.
        """
        from halyard.evidence import build_evidence_artifact, verify_evidence_artifact

        if verify is not None and json_:
            _fail(json_, "--verify and --json are mutually exclusive.")

        if verify is not None:
            if not verify.is_file():
                console.print(f"[bold red]Error:[/] No such file: {verify}")
                raise typer.Exit(code=1)
            ok = verify_evidence_artifact(verify.read_text(encoding="utf-8"))
            if ok:
                console.print(f"[green]✓ Evidence digest verified:[/] {verify}")
                raise typer.Exit(code=0)
            console.print(f"[bold red]✗ Digest mismatch — artifact was modified:[/] {verify}")
            raise typer.Exit(code=1)

        if month:
            from datetime import datetime

            try:
                datetime.strptime(month, "%Y-%m")
            except ValueError:
                _fail(json_, "--month must be YYYY-MM (e.g. 2026-05).")

        from halyard.ai_log import find_project_dir

        project_dir = find_project_dir()
        if project_dir is None:
            if json_:
                from halyard.jsonio import emit

                emit({"error": "No Halyard project found. Run 'halyard init' first."})
                raise typer.Exit(code=1)
            console.print(
                "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
            )
            raise typer.Exit(code=1)

        if json_:
            from halyard.evidence import build_evidence_data
            from halyard.jsonio import emit

            emit(
                build_evidence_data(
                    project_dir,
                    project=project,
                    client=client,
                    all_time=all_time,
                    month=month,
                )
            )
            return

        artifact = build_evidence_artifact(
            project_dir, project=project, client=client, all_time=all_time, month=month
        )

        if out is not None:
            if out.exists() and not force:
                console.print(
                    f"[bold red]Error:[/] {out} exists — pass [bold]--force[/] to overwrite."
                )
                raise typer.Exit(code=1)
            out.write_text(artifact, encoding="utf-8")
            console.print(f"[green]Evidence artifact written:[/] {out}")
            return

        # Print the exact artifact bytes (no Rich markup) so a piped
        # file keeps a valid digest.
        print(artifact, end="")

    @app.command()
    def health(
        period: str = typer.Option("month", "--period", help="today | week | month | all"),
        project: str | None = typer.Option(None, "--project", help="Filter to a project slug."),
        format_: str = typer.Option("text", "--format", help="text | json"),
    ) -> None:
        """Show AI work health signals for the current period."""
        from datetime import datetime, timedelta

        from halyard.ai_log import find_project_dir, parse_sessions
        from halyard.hub import find_hub
        from halyard.work_health import build_health_report, render_json, render_text

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
            sessions = [
                s for s in sessions if s.start.year == now.year and s.start.month == now.month
            ]
        elif p != "all":
            console.print("[bold red]Error:[/] --period must be one of: today, week, month, all")
            raise typer.Exit(code=1)

        if project:
            sessions = [s for s in sessions if s.project == project]

        health_report = build_health_report(sessions, period=p)

        if format_ == "json":
            from halyard.jsonio import emit

            emit(render_json(health_report))
        else:
            console.print(render_text(health_report))

    @app.command()
    def schedule(
        period: str = typer.Option("month", "--period", help="today | week | month | all"),
        project: str | None = typer.Option(None, "--project", help="Filter to a project slug."),
        output: str | None = typer.Option(None, "--output", help="Output file path."),
        stdout: bool = typer.Option(
            False, "--stdout", help="Write ICS to stdout instead of a file."
        ),
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
            sessions = [
                s for s in sessions if s.start.year == now.year and s.start.month == now.month
            ]
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
        """Start the local Halyard dashboard (The Bridge).

        With no --project-dir, aggregates every registered project (+ hub)
        so the default view is your total real work, not a single log.
        """
        from halyard.dashboard import DashboardError, run_dashboard
        from halyard.reports import aggregate_session_dirs

        if project_dir_opt is None and not aggregate_session_dirs():
            console.print(
                "[bold red]Error:[/] No Halyard project found. Run [bold]halyard init[/] first."
            )
            raise typer.Exit(code=1)

        # None ⇒ aggregate across all real project logs + hub.
        try:
            run_dashboard(project_dir_opt, port=port, open_browser=open_)
        except DashboardError as exc:
            console.print(f"[bold red]Error:[/] {exc}")
            raise typer.Exit(code=1) from exc

    @app.command(name="tui")
    def tui_cmd(
        hub: bool = typer.Option(False, "--hub", help="Use the configured hub log instead of CWD."),
        project_dir_opt: Path = typer.Option(
            None, "--project-dir", help="Halyard project directory (default: auto-detect)."
        ),
    ) -> None:
        """Launch the interactive Textual terminal dashboard."""
        from rich.markup import escape

        from halyard.ai_log import AI_LOG_FILENAME, find_project_dir
        from halyard.hub import find_hub

        try:
            from halyard.tui.app import HalyardApp
        except ImportError as exc:
            console.print(f"[bold red]Error:[/] {escape(str(exc))}")
            raise typer.Exit(code=1) from None

        project_dir = project_dir_opt or find_project_dir()
        hub_dir = find_hub()

        header_note: str | None = None
        if hub and hub_dir is not None:
            log_path = hub_dir / AI_LOG_FILENAME
        elif project_dir is not None:
            log_path = project_dir / AI_LOG_FILENAME
        elif hub_dir is not None:
            log_path = hub_dir / AI_LOG_FILENAME
        else:
            log_path = Path.cwd() / AI_LOG_FILENAME
            header_note = "No project or hub found - run 'halyard init' or 'halyard set-hub'"

        project_slug = project_dir.name if project_dir is not None else None
        HalyardApp(log_path=log_path, project_slug=project_slug, header_note=header_note).run()

    @app.command(name="update-pricing")
    def update_pricing_cmd(
        accept_changed: bool = typer.Option(
            False,
            "--accept-changed",
            help="Accept a changed pricing table without prompting.",
        ),
    ) -> None:
        """Fetch the latest model pricing table from GitHub and save locally."""
        from halyard.pricing import PricingFetchError, PricingHashChangedError, update_pricing

        console.print("Fetching pricing table from github.com/Kormiloio/Halyard...")
        try:
            new_count, updated_count = update_pricing(accept_changed=accept_changed)
        except PricingHashChangedError as exc:
            console.print(f"[bold yellow]Warning:[/] {exc}")
            raise typer.Exit(code=1) from None
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

    @app.command()
    def budget(
        json_: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Show current AI spend vs. configured budget limits for all projects."""
        from datetime import datetime

        from halyard.budget import budget_status, load_budgets

        budgets = load_budgets()

        if json_:
            from halyard.jsonio import emit

            def _row(spend: float, limit: float | None) -> dict[str, object]:
                if limit is None:
                    return {
                        "spend_usd": round(spend, 4),
                        "limit_usd": None,
                        "pct": None,
                        "state": "ok",
                    }
                pct = round(spend / limit * 100, 1) if limit else None
                return {
                    "spend_usd": round(spend, 4),
                    "limit_usd": limit,
                    "pct": pct,
                    "state": "over" if spend > limit else "ok",
                }

            if not budgets:
                emit([])
                return
            emit(
                [
                    {
                        "project": s.slug,
                        "today": _row(s.today_spend, s.today_limit),
                        "month": _row(s.month_spend, s.month_limit),
                    }
                    for s in budget_status(now=datetime.now())
                ]
            )
            return

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
            if s.today_limit is not None:
                over = s.today_spend > s.today_limit
                mark = "  [bold yellow]⚠ over[/]" if over else "  [green]✓[/]"
                pct = f" {s.today_spend / s.today_limit * 100:.0f}% used" if not over else ""
                console.print(
                    f"    Today      ${s.today_spend:.2f} / ${s.today_limit:.2f}{mark}{pct}"
                )
            else:
                console.print(f"    Today      ${s.today_spend:.2f}  [dim](no limit)[/dim]")
            if s.month_limit is not None:
                over = s.month_spend > s.month_limit
                mark = "  [bold yellow]⚠ over[/]" if over else "  [green]✓[/]"
                pct = f" {s.month_spend / s.month_limit * 100:.0f}% used" if not over else ""
                console.print(
                    f"    This month ${s.month_spend:.2f} / ${s.month_limit:.2f}{mark}{pct}"
                )
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

    @app.command()
    def usage(
        range_key: str = typer.Option(
            "30d",
            "--range",
            help="Time window: all | 30d | 7d",
        ),
        json_: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Show usage analytics: sessions, tokens, streaks, peak hour, model mix."""
        from typing import cast

        from halyard.ai_log import find_project_dir, parse_sessions
        from halyard.hub import find_hub
        from halyard.usage import UsageRangeKey, build_usage_analytics, compact_number

        if range_key not in ("all", "30d", "7d"):
            _fail(json_, "--range must be one of: all, 30d, 7d")

        project_dir = find_hub() or find_project_dir()
        if project_dir is None:
            _fail(json_, "No Halyard project or hub found. Run 'halyard init' first.")

        sessions = parse_sessions(project_dir)
        analytics = build_usage_analytics(sessions, range_key=cast(UsageRangeKey, range_key))

        if json_:
            from halyard.jsonio import emit

            emit(
                {
                    "range": analytics.range,
                    "summary": analytics.summary,
                    "daily": analytics.daily,
                    "by_model": analytics.by_model,
                    "by_tool": analytics.by_tool,
                }
            )
            return

        s = analytics.summary
        console.print(f"\n[bold]Usage — {analytics.range.label}[/]")
        console.print(
            f"  {s.sessions:>5} sessions · "
            f"{compact_number(s.total_tokens)} tokens · "
            f"${s.total_cost_usd:.2f} cost"
        )
        console.print(
            f"  {s.active_days} active days · "
            f"current streak {s.current_streak_days}d · "
            f"longest {s.longest_streak_days}d"
        )
        peak = "—" if s.peak_hour is None else f"{s.peak_hour:02d}:00"
        favorite = s.favorite_model or "—"
        console.print(f"  peak hour {peak} · favorite model {favorite}")

        if s.unattributed_sessions:
            console.print(
                f"[yellow]  {s.unattributed_sessions} session(s) without project attribution[/]"
            )
        if s.token_data_missing_sessions:
            console.print(
                f"[yellow]  {s.token_data_missing_sessions} session(s) missing token data[/]"
            )

        if analytics.by_model:
            console.print("\n[bold]Models[/]")
            for mbucket in analytics.by_model[:5]:
                pct = int(mbucket.token_share * 100)
                console.print(
                    f"  {mbucket.model:<30} {compact_number(mbucket.tokens):>8} tokens  {pct:>3}%"
                )

        if analytics.by_tool:
            console.print("\n[bold]Tools[/]")
            for tbucket in analytics.by_tool:
                console.print(
                    f"  {tbucket.tool:<30} "
                    f"{tbucket.sessions:>5} sessions  "
                    f"{compact_number(tbucket.tokens):>8} tokens"
                )
