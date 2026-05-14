"""halyard hooks — AI tool hook installation and hidden collector entry points."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

console = Console()


def _halyard_exe() -> str:
    """Return the absolute path to the running halyard executable.

    Prefers the resolved sys.argv[0] so that hooks embed the exact binary that
    ran `install-*-hook`, rather than relying on PATH being set up correctly
    in the hook execution environment (e.g. Gemini CLI, Cursor, Claude Code).
    """
    candidate = Path(sys.argv[0]).resolve()
    if candidate.name in ("halyard", "halyard.exe") and candidate.exists():
        return str(candidate)
    found = shutil.which("halyard")
    if found:
        return str(Path(found).resolve())
    return "halyard"  # fallback: trust PATH at hook-run time


# Claude Code hook config injected by `halyard install-hook`
_CC_HOOKS: dict[str, list[dict[str, Any]]] = {
    "UserPromptSubmit": [
        {"matcher": "", "hooks": [{"type": "command", "command": "halyard cc-session"}]}
    ],
    "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "halyard cc-hook"}]}],
}

# Gemini CLI hook config injected by `halyard install-gemini-hook`
_GC_HOOKS: dict[str, str] = {
    "SessionStart": "halyard gc-session",
    "AfterModel": "halyard gc-model",
    "AfterAgent": "halyard gc-hook",
}

# Cursor hook config injected by `halyard install-cursor-hook`
_CURSOR_HOOKS: dict[str, str] = {
    "beforeSubmitPrompt": "halyard cursor-session",
    "stop": "halyard cursor-hook",
}

_VSCODE_TASK_LABEL = "Halyard: Record VS Code AI session"
_VSCODE_TASK_INPUTS: tuple[dict[str, str], ...] = (
    {
        "id": "halyardModel",
        "type": "promptString",
        "description": "Model or assistant label",
        "default": "github-copilot",
    },
    {
        "id": "halyardMinutes",
        "type": "promptString",
        "description": "Minutes to record",
        "default": "15",
    },
    {
        "id": "halyardNote",
        "type": "promptString",
        "description": "Short note",
        "default": "VS Code AI work",
    },
)


def _cc_hook_cmd_key(cmd: str) -> str:
    """Normalise hook command to subcommand name so absolute paths don't create false duplicates."""
    parts = cmd.split()
    return f"{Path(parts[0]).name} {' '.join(parts[1:])}" if parts else cmd


def _cc_hook_commands_from_path(path: Path) -> set[str]:
    """Return normalised command keys from a Claude settings file."""
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return set()
    keys: set[str] = set()
    hooks = data.get("hooks", {}) if isinstance(data, dict) else {}
    for entries in hooks.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for h in entry.get("hooks", []):
                if isinstance(h, dict) and isinstance(h.get("command"), str):
                    keys.add(_cc_hook_cmd_key(h["command"]))
    return keys


def _do_install_hook_claude(global_: bool = False) -> None:
    if global_:
        settings_path = Path.home() / ".claude" / "settings.json"
        other_path = Path.cwd() / ".claude" / "settings.json"
    else:
        settings_path = Path.cwd() / ".claude" / "settings.json"
        other_path = Path.home() / ".claude" / "settings.json"

    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, ValueError):
            existing = {}

    exe = _halyard_exe()

    proposed_keys: set[str] = set()
    for entries in _CC_HOOKS.values():
        resolved = json.loads(json.dumps(entries).replace("halyard ", f"{exe} ", 1))
        cmd = resolved[0]["hooks"][0]["command"]
        proposed_keys.add(_cc_hook_cmd_key(cmd))

    other_keys = _cc_hook_commands_from_path(other_path)
    if proposed_keys & other_keys:
        console.print(
            f"[yellow]Claude Code hooks already present in {other_path} — skipping.[/]\n"
            f"Having hooks in both files records every session twice.\n"
            f"To expand to global coverage run: [bold]halyard install-hook --global[/]"
        )
        return

    hooks = existing.setdefault("hooks", {})
    added: list[str] = []

    for event, entries in _CC_HOOKS.items():
        resolved = json.loads(json.dumps(entries).replace("halyard ", f"{exe} ", 1))
        current = hooks.setdefault(event, [])
        command = resolved[0]["hooks"][0]["command"]
        new_key = _cc_hook_cmd_key(command)
        already = any(
            _cc_hook_cmd_key(h.get("command", "")) == new_key
            for entry in current
            for h in entry.get("hooks", [])
        )
        if not already:
            current.extend(resolved)
            added.append(event)

    settings_path.write_text(json.dumps(existing, indent=2) + "\n")

    if added:
        console.print(f"[bold green]Claude Code hooks installed[/] in [bold]{settings_path}[/]")
    else:
        console.print(f"[yellow]Claude Code hooks already present[/] in [bold]{settings_path}[/]")


def _do_install_hook_gemini() -> None:
    settings_path = Path.home() / ".gemini" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, ValueError):
            existing = {}

    hooks = existing.setdefault("hooks", {})
    added: list[str] = []
    exe = _halyard_exe()

    for event, template in _GC_HOOKS.items():
        command = template.replace("halyard ", f"{exe} ", 1)
        current = hooks.setdefault(event, [])
        already = any(
            h.get("command") == command for entry in current for h in entry.get("hooks", [])
        )
        if not already:
            current.append(
                {
                    "matcher": "*",
                    "hooks": [{"name": "halyard", "type": "command", "command": command}],
                }
            )
            added.append(event)

    settings_path.write_text(json.dumps(existing, indent=2) + "\n")

    if added:
        console.print(f"[bold green]Gemini CLI hooks installed[/] in [bold]{settings_path}[/]")
    else:
        console.print(f"[yellow]Gemini CLI hooks already present[/] in [bold]{settings_path}[/]")


def _do_install_hook_cursor() -> None:
    settings_path = Path.home() / ".cursor" / "hooks.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, ValueError):
            existing = {}

    existing.setdefault("version", 1)
    hooks = existing.setdefault("hooks", {})
    added: list[str] = []
    exe = _halyard_exe()

    for event, template in _CURSOR_HOOKS.items():
        command = template.replace("halyard ", f"{exe} ", 1)
        current = hooks.setdefault(event, [])
        already = any(entry.get("command") == command for entry in current)
        if not already:
            current.append({"command": command})
            added.append(event)

    settings_path.write_text(json.dumps(existing, indent=2) + "\n")

    if added:
        console.print(f"[bold green]Cursor hooks installed[/] in [bold]{settings_path}[/]")
    else:
        console.print(f"[yellow]Cursor hooks already present[/] in [bold]{settings_path}[/]")


def _vscode_record_task(command: str) -> dict[str, Any]:
    return {
        "label": _VSCODE_TASK_LABEL,
        "type": "process",
        "command": command,
        "args": [
            "record-session",
            "--tool",
            "vscode",
            "--model",
            "${input:halyardModel}",
            "--minutes",
            "${input:halyardMinutes}",
            "--note",
            "${input:halyardNote}",
        ],
        "problemMatcher": [],
        "presentation": {"reveal": "always", "panel": "dedicated"},
    }


def _merge_vscode_inputs(existing_inputs: object) -> list[dict[str, Any]]:
    inputs = (
        [dict(item) for item in existing_inputs if isinstance(item, dict)]
        if isinstance(existing_inputs, list)
        else []
    )
    existing_ids = {item.get("id") for item in inputs}
    for item in _VSCODE_TASK_INPUTS:
        if item["id"] not in existing_ids:
            inputs.append(dict(item))
    return inputs


def _do_install_vscode_tasks() -> Path:
    settings_path = Path.cwd() / ".vscode" / "tasks.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, ValueError):
            existing = {}

    existing.setdefault("version", "2.0.0")
    tasks = existing.setdefault("tasks", [])
    if not isinstance(tasks, list):
        tasks = []
        existing["tasks"] = tasks

    command = _halyard_exe()
    labels = {task.get("label") for task in tasks if isinstance(task, dict)}
    if _VSCODE_TASK_LABEL not in labels:
        tasks.append(_vscode_record_task(command))

    existing["inputs"] = _merge_vscode_inputs(existing.get("inputs"))
    settings_path.write_text(json.dumps(existing, indent=2) + "\n")
    return settings_path


def _auto_install_detected_hooks() -> None:
    """Detect installed AI tools on PATH and auto-install their Halyard hooks."""
    found: list[str] = []
    not_found: list[str] = []
    failed: list[str] = []

    for binary, label, installer in [
        ("claude", "Claude Code", lambda: _do_install_hook_claude(global_=True)),
        ("cursor", "Cursor", _do_install_hook_cursor),
        ("gemini", "Gemini CLI", _do_install_hook_gemini),
    ]:
        if shutil.which(binary):
            try:
                installer()  # type: ignore[no-untyped-call]
                found.append(label)
            except OSError:
                failed.append(f"{label} (run halyard install-hook-{binary})")
        else:
            not_found.append(label)

    if found:
        console.print(f"\n[bold green]Auto-installed hooks:[/] {', '.join(found)}")
    if failed:
        console.print(f"[yellow]Hook install failed:[/] {', '.join(failed)}")
    if not_found:
        console.print(
            f"[dim]Not on PATH:[/] {', '.join(not_found)} "
            f"(install later with [bold]halyard install-hook-<tool>[/])"
        )


def register(app: typer.Typer) -> None:
    @app.command(name="cc-session", hidden=True)
    def cc_session() -> None:
        """Record Claude Code session start (called by UserPromptSubmit hook)."""
        from halyard.collectors.claude_code import record_session_start

        raise typer.Exit(code=record_session_start())

    @app.command(name="cc-hook", hidden=True)
    def cc_hook() -> None:
        """Process Claude Code Stop hook payload (called by Stop hook)."""
        from halyard.collectors.claude_code import handle_stop_hook

        raise typer.Exit(code=handle_stop_hook())

    @app.command(name="gc-session", hidden=True)
    def gc_session() -> None:
        """Record Gemini CLI session start (called by SessionStart hook)."""
        from halyard.collectors.gemini_cli import record_session_start

        raise typer.Exit(code=record_session_start())

    @app.command(name="gc-model", hidden=True)
    def gc_model() -> None:
        """Accumulate Gemini CLI token counts (called by AfterModel hook)."""
        from halyard.collectors.gemini_cli import record_model_usage

        raise typer.Exit(code=record_model_usage())

    @app.command(name="gc-hook", hidden=True)
    def gc_hook() -> None:
        """Finalise Gemini CLI session record (called by AfterAgent hook)."""
        from halyard.collectors.gemini_cli import handle_agent_stop

        raise typer.Exit(code=handle_agent_stop())

    @app.command(name="cursor-session", hidden=True)
    def cursor_session() -> None:
        """Record Cursor session start (called by beforeSubmitPrompt hook)."""
        from halyard.collectors.cursor import record_session_start

        raise typer.Exit(code=record_session_start())

    @app.command(name="cursor-hook", hidden=True)
    def cursor_hook() -> None:
        """Process Cursor stop hook payload (called by stop hook)."""
        from halyard.collectors.cursor import handle_stop_hook

        raise typer.Exit(code=handle_stop_hook())

    @app.command(name="install-hook-claude")
    def install_hook_claude(
        global_: bool = typer.Option(
            False,
            "--global",
            help="Install into ~/.claude/settings.json instead of .claude/settings.json.",
        ),
    ) -> None:
        """Install Claude Code hooks to auto-capture AI sessions."""
        _do_install_hook_claude(global_=global_)

    @app.command(name="install-hook", hidden=True)
    def install_hook(
        global_: bool = typer.Option(
            False,
            "--global",
            help="Install into ~/.claude/settings.json instead of .claude/settings.json.",
        ),
    ) -> None:
        """Deprecated alias for install-hook-claude."""
        _do_install_hook_claude(global_=global_)

    @app.command(name="install-hook-gemini")
    def install_hook_gemini() -> None:
        """Install Gemini CLI hooks to auto-capture AI sessions."""
        _do_install_hook_gemini()

    @app.command(name="install-gemini-hook", hidden=True)
    def install_gemini_hook() -> None:
        """Deprecated alias for install-hook-gemini."""
        _do_install_hook_gemini()

    @app.command(name="install-hook-cursor")
    def install_hook_cursor() -> None:
        """Install Cursor hooks to auto-capture AI sessions."""
        _do_install_hook_cursor()

    @app.command(name="install-cursor-hook", hidden=True)
    def install_cursor_hook() -> None:
        """Deprecated alias for install-hook-cursor."""
        _do_install_hook_cursor()

    @app.command(name="install-vscode-tasks")
    def install_vscode_tasks() -> None:
        """Install VS Code tasks for manual AI session capture."""
        settings_path = _do_install_vscode_tasks()
        console.print(f"[bold green]VS Code Halyard task installed[/] in [bold]{settings_path}[/]")
        console.print(
            "[dim]Run the task from VS Code: "
            "Terminal → Run Task → Halyard: Record VS Code AI session[/]"
        )

    @app.command(name="install-hook-vscode", hidden=True)
    def install_hook_vscode() -> None:
        """Deprecated alias for install-vscode-tasks."""
        settings_path = _do_install_vscode_tasks()
        console.print(f"[bold green]VS Code Halyard task installed[/] in [bold]{settings_path}[/]")
        console.print(
            "[dim]Run the task from VS Code: "
            "Terminal → Run Task → Halyard: Record VS Code AI session[/]"
        )
