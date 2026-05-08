"""Interactive REPL — natural-language queries over captured work metadata."""

from __future__ import annotations

import atexit
from contextlib import suppress
from pathlib import Path
from typing import cast

from rich.console import Console
from rich.rule import Rule

from halyard.log_agent import LogAgent, LogAgentError, run_log_query
from halyard.log_config import load_log_config

_HISTORY_FILE = Path.home() / ".halyard" / "repl_history"
_PROMPT = "halyard> "

_HELP = """\
  Ask anything about your captured work:
    "How much did I spend on Claude Code this week?"
    "Which project used the most tokens last month?"
    "Show me sessions from the auth project today."

  Commands:
    /agent <local|claude|openai>    Switch query provider
    /model <name>                   Set model for claude/openai agents
    /period <today|week|month|all>  Change time window  (default: month)
    /help  /?                       Show this message
    /quit  /q  Ctrl-D               Exit
"""


def run_repl(project_dir: Path, *, default_agent: str = "local") -> None:
    """Run the interactive Halyard REPL until the user quits or sends EOF."""
    console = Console()
    cfg = load_log_config()
    agent: str = default_agent or cfg.default_agent
    model: str | None = None
    period: str = "month"

    _setup_readline()

    console.print(Rule(style="cyan"))
    console.print(f"  [bold cyan]Halyard[/]  {project_dir.name}")
    console.print(f"  agent [bold]{agent}[/]  ·  period [bold]{period}[/]")
    console.print("  [dim]/help for commands · Ctrl-D to exit[/]")
    console.print(Rule(style="cyan"))

    while True:
        try:
            raw = input(_PROMPT).strip()
        except EOFError:
            console.print("\n[dim]Goodbye.[/]")
            break
        except KeyboardInterrupt:
            console.print("")
            continue

        if not raw:
            continue

        if raw.startswith("/"):
            parts = raw.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if cmd in ("/quit", "/q"):
                console.print("[dim]Goodbye.[/]")
                break

            elif cmd in ("/help", "/?"):
                console.print(_HELP)

            elif cmd == "/agent":
                if arg not in {"local", "claude", "openai"}:
                    console.print("[red]Agent must be one of: local, claude, openai[/]")
                else:
                    agent = arg
                    console.print(f"[dim]agent → {agent}[/]")

            elif cmd == "/model":
                if not arg:
                    console.print(f"[dim]model: {model or '(provider default)'}[/]")
                else:
                    model = arg
                    console.print(f"[dim]model → {model}[/]")

            elif cmd == "/period":
                if arg not in {"today", "week", "month", "all"}:
                    console.print("[red]Period must be one of: today, week, month, all[/]")
                else:
                    period = arg
                    console.print(f"[dim]period → {period}[/]")

            else:
                console.print(f"[red]Unknown command:[/] {cmd}  (type /help)")

            continue

        try:
            response = run_log_query(
                raw,
                project_dir=project_dir,
                agent=cast(LogAgent, agent),
                period=period,
                model=model,
            )
        except LogAgentError as exc:
            console.print(f"[red]Error:[/] {exc}")
            continue

        console.print(f"\n  [bold]{response.answer}[/]")
        if response.projects:
            console.print("\n  [bold]By project[/]")
            for bucket in response.projects:
                console.print(
                    f"  {bucket.label:<32} ${bucket.cost_usd:.2f}  {bucket.sessions} sessions"
                )
        if response.models:
            console.print("\n  [bold]By model[/]")
            for bucket in response.models:
                console.print(
                    f"  {bucket.label:<32} ${bucket.cost_usd:.2f}  {bucket.sessions} sessions"
                )
        console.print("")


def _setup_readline() -> None:
    with suppress(ImportError, OSError):
        import readline
        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with suppress(FileNotFoundError):
            readline.read_history_file(_HISTORY_FILE)
        readline.set_history_length(500)
        atexit.register(_write_history)


def _write_history() -> None:
    with suppress(ImportError, OSError):
        import readline
        readline.write_history_file(_HISTORY_FILE)
