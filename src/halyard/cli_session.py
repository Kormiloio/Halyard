"""halyard session — time tracking, invoicing, and AI session recording sub-commands."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

import typer
from rich.console import Console

console = Console()


def register(app: typer.Typer) -> None:
    @app.command()
    def log(
        message: str = typer.Argument(..., help="Natural-language description of work."),
        json_output: bool = typer.Option(False, "--json", help="Emit structured JSON."),
        period: str = typer.Option("month", "--period", help="today | week | month | all"),
        agent: str | None = typer.Option(
            None,
            "--agent",
            help="Query provider: local | claude | openai. Defaults to ~/.halyard/config.toml"
            " value.",
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
        project: str | None = typer.Option(
            None, "--project", help="Filter local queries by project."
        ),
        model_filter: str | None = typer.Option(
            None, "--model-filter", help="Filter local queries by model substring."
        ),
        branch: str | None = typer.Option(
            None, "--branch", help="Filter local queries by branch tag."
        ),
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
            timer = start_timer(Path.cwd(), account)
        except TimerAlreadyRunning as e:
            console.print(
                f"[bold red]Error:[/] Timer already running for [bold]{e.slug}[/].\n"
                "Run [bold]halyard stop[/] first."
            )
            raise typer.Exit(code=1) from e

        console.print(f"[bold green]Started[/] [bold]{timer.slug}[/] at {timer.started}.")
        console.print(
            "[dim]AI sessions captured automatically — [bold]halyard stop[/] when done.[/]"
        )

    @app.command()
    def stop() -> None:
        """Stop the active timer."""
        from halyard.orchestration import stop_timer
        from halyard.reports import _elapsed_minutes, format_minutes, read_active_timer

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

        result = stop_timer(Path.cwd())

        try:
            from halyard.auto_timer import auto_timer_close_now

            auto_timer_close_now()
        except Exception:
            pass

        if result.was_running:
            from halyard.visuals import stop_card

            started = active.started or now.strftime("%Y-%m-%d %H:%M:%S")
            elapsed_mins = _elapsed_minutes(started, now)
            elapsed = format_minutes(elapsed_mins)
            console.print(stop_card(slug, elapsed_mins, elapsed, result.backfill_count))
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
                "[yellow]No timeclock data found.[/] Run [bold]halyard start[/]"
                " to begin tracking time."
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
                console.print(
                    f"  {skipped_no_window} session(s) have no matching timeclock window."
                )
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

    @app.command()
    def invoice(
        client: str = typer.Argument(..., help="Client slug to invoice."),
        month: str | None = typer.Option(None, "--month", help="last | this | YYYY-MM"),
        from_: str | None = typer.Option(None, "--from", help="ISO date (inclusive lower bound)"),
        to: str | None = typer.Option(None, "--to", help="ISO date (inclusive upper bound)"),
        project: str | None = typer.Option(
            None, "--project", help="Project slug under the client."
        ),
        period: str | None = typer.Option(None, "--period", help="Billing period as YYYY-MM."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
        pdf: bool = typer.Option(
            False, "--pdf", help="Render a PDF via typst after writing markdown."
        ),
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

    @app.command(name="record-session")
    def record_session(
        project: str | None = typer.Option(
            None,
            "--project",
            help="Project slug as client:project. Defaults to the active timer project.",
        ),
        tool: str = typer.Option(
            "manual",
            "--tool",
            help="AI tool slug (e.g. claude-code, cursor, vscode).",
        ),
        model: str = typer.Option("unspecified", "--model", help="Model label."),
        input_tokens: int = typer.Option(0, "--input-tokens", help="Input token count."),
        output_tokens: int = typer.Option(0, "--output-tokens", help="Output token count."),
        cost: float | None = typer.Option(None, "--cost", help="Explicit USD cost."),
        minutes: int = typer.Option(1, "--minutes", help="Session duration in minutes."),
        note: str | None = typer.Option(None, "--note", help="Short note, spaces are allowed."),
        source: str = typer.Option("manual", "--source", help="Capture source label."),
        branch: str | None = typer.Option(None, "--branch", help="Git branch name, if known."),
        commit_count: int | None = typer.Option(None, "--commit-count", help="Commits in window."),
        tool_calls: int | None = typer.Option(None, "--tool-calls", help="Tool call count."),
        tool_errors: int | None = typer.Option(None, "--tool-errors", help="Tool error count."),
        wall_seconds: int | None = typer.Option(None, "--wall-seconds", help="Wall-clock seconds."),
        agent_active_seconds: int | None = typer.Option(
            None, "--agent-active-seconds", help="Agent-active seconds."
        ),
        code_added: int | None = typer.Option(None, "--code-added", help="Lines added."),
        code_removed: int | None = typer.Option(None, "--code-removed", help="Lines removed."),
        interaction_count: int | None = typer.Option(
            None, "--interaction-count", help="Total safe interaction count."
        ),
        user_message_count: int | None = typer.Option(
            None, "--user-message-count", help="User message count."
        ),
        assistant_message_count: int | None = typer.Option(
            None, "--assistant-message-count", help="Assistant message count."
        ),
        prompt_count: int | None = typer.Option(None, "--prompt-count", help="Prompt count."),
        accepted_suggestion_count: int | None = typer.Option(
            None, "--accepted-suggestion-count", help="Accepted suggestion count."
        ),
        rejected_suggestion_count: int | None = typer.Option(
            None, "--rejected-suggestion-count", help="Rejected suggestion count."
        ),
        files_touched_count: int | None = typer.Option(
            None, "--files-touched-count", help="Number of touched files."
        ),
        test_run_count: int | None = typer.Option(None, "--test-run-count", help="Test run count."),
        test_status: str | None = typer.Option(None, "--test-status", help="pass|fail|unknown."),
        build_status: str | None = typer.Option(None, "--build-status", help="pass|fail|unknown."),
        human_active_seconds: int | None = typer.Option(
            None, "--human-active-seconds", help="Human-active seconds."
        ),
        idle_seconds: int | None = typer.Option(None, "--idle-seconds", help="Idle seconds."),
        interaction_data_available: bool | None = typer.Option(
            None,
            "--interaction-data-available/--interaction-data-unavailable",
            help="Whether interaction metadata was available.",
        ),
        outcome_data_available: bool | None = typer.Option(
            None,
            "--outcome-data-available/--outcome-data-unavailable",
            help="Whether outcome metadata was available.",
        ),
        telemetry_source: str | None = typer.Option(
            None, "--telemetry-source", help="Telemetry producer label."
        ),
        telemetry_trust: str | None = typer.Option(
            None, "--telemetry-trust", help="observed|estimated|manual."
        ),
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

        valid_status = {"pass", "fail", "unknown"}
        valid_trust = {"observed", "estimated", "manual"}
        if test_status is not None and test_status not in valid_status:
            console.print(
                f"[bold red]Error:[/] --test-status must be pass, fail, or unknown"
                f" (got '{test_status}')."
            )
            raise typer.Exit(code=1)
        if build_status is not None and build_status not in valid_status:
            console.print(
                f"[bold red]Error:[/] --build-status must be pass, fail, or unknown"
                f" (got '{build_status}')."
            )
            raise typer.Exit(code=1)
        if telemetry_trust is not None and telemetry_trust not in valid_trust:
            console.print(
                f"[bold red]Error:[/] --telemetry-trust must be observed, estimated, or manual"
                f" (got '{telemetry_trust}')."
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
            source=source,
            note=note,
            branch=branch,
            commit_count=commit_count,
            tool_calls=tool_calls,
            tool_errors=tool_errors,
            wall_seconds=wall_seconds,
            agent_active_seconds=agent_active_seconds,
            code_added=code_added,
            code_removed=code_removed,
            interaction_count=interaction_count,
            user_message_count=user_message_count,
            assistant_message_count=assistant_message_count,
            prompt_count=prompt_count,
            accepted_suggestion_count=accepted_suggestion_count,
            rejected_suggestion_count=rejected_suggestion_count,
            files_touched_count=files_touched_count,
            test_run_count=test_run_count,
            test_status=test_status,
            build_status=build_status,
            human_active_seconds=human_active_seconds,
            idle_seconds=idle_seconds,
            interaction_data_available=interaction_data_available,
            outcome_data_available=outcome_data_available,
            telemetry_source=telemetry_source,
            telemetry_trust=telemetry_trust,
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
            source="manual",
            branch=None,
            commit_count=None,
            tool_calls=None,
            tool_errors=None,
            wall_seconds=None,
            agent_active_seconds=None,
            code_added=None,
            code_removed=None,
            interaction_count=None,
            user_message_count=None,
            assistant_message_count=None,
            prompt_count=None,
            accepted_suggestion_count=None,
            rejected_suggestion_count=None,
            files_touched_count=None,
            test_run_count=None,
            test_status=None,
            build_status=None,
            human_active_seconds=None,
            idle_seconds=None,
            interaction_data_available=None,
            outcome_data_available=None,
            telemetry_source=None,
            telemetry_trust=None,
        )

    @app.command(name="seed-demo")
    def seed_demo(
        yes: bool = typer.Option(False, "--yes", help="Confirm appending to an existing log."),
    ) -> None:
        """Seed ai-sessions.log with realistic demo data for dashboard previews."""
        import random
        from datetime import datetime as _dt
        from datetime import timedelta as _td

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

        now = _dt.now()
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
            (None,                 "cursor",      0.14,  6000,  900,  9, None, None, None, None, 19),  # noqa: E501
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
            start = month_start + _td(days=day_off, hours=base_hour, minutes=base_min)
            end = start + _td(minutes=mins)
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
        project_dir: Path | None = typer.Option(
            None,
            "--project-dir",
            help="Halyard project directory to validate against (default: hub, then cwd).",
        ),
    ) -> None:
        """Assign unattributed AI sessions to a project."""
        from halyard.orchestration import interactive_assign_unattributed

        interactive_assign_unattributed(explicit_project=project, project_dir=project_dir)

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
