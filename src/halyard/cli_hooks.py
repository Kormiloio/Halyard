"""halyard hooks — AI tool hook installation and hidden collector entry points."""

from __future__ import annotations

import json
import shlex
import shutil
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

console = Console()
_hook_err_console = Console(stderr=True)


def _run_hook(fn: Callable[[], int]) -> int:
    """Run a collector hook entry point with an absolute crash backstop.

    Hooks run as subprocesses of the host AI tool (Claude Code, Gemini,
    Cursor). An uncaught exception here becomes a traceback + nonzero
    exit *inside the host tool*. The per-collector code is defensive,
    but this is the guarantee of last resort: any failure is logged to
    stderr and the hook exits 0 so the host is never disrupted.
    """
    try:
        return fn()
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:
        with suppress(Exception):
            _hook_err_console.print(f"[dim]halyard hook suppressed: {exc!r}[/dim]")
        return 0


def _is_trusted_exe_path(path: Path) -> bool:
    """True if *path* lives under a trusted install prefix.

    `argv[0]` is only trustworthy when it resolves into a real
    venv/site/system install — not a writable or temp dir where a
    `halyard`-named wrapper could be dropped and then persisted into
    tool configs as a per-session executed command.
    """
    trusted_roots = {
        Path(sys.prefix).resolve(),
        Path(sys.base_prefix).resolve(),
        Path(sys.executable).resolve().parent,
    }
    return any(root == path or root in path.parents for root in trusted_roots)


def _halyard_exe() -> str:
    """Return the path hooks should use to invoke halyard.

    Resolution order (most→least trustworthy):
    1. ``shutil.which("halyard")`` *only if* it lies under a trusted prefix
       (venv/site/system), so an attacker-controlled PATH entry cannot be
       persisted into hook/service configs.
    2. resolved ``sys.argv[0]`` *only if* it lies under a trusted prefix
       (venv/site/system), so a writable-dir wrapper can't be embedded.
    3. the literal ``"halyard"`` — trust PATH at hook-run time.
    """
    found = shutil.which("halyard")
    if found:
        found_path = Path(found).resolve()
        if _is_trusted_exe_path(found_path):
            return str(found_path)
    candidate = Path(sys.argv[0]).resolve()
    if (
        candidate.name in ("halyard", "halyard.exe")
        and candidate.exists()
        and _is_trusted_exe_path(candidate)
    ):
        return str(candidate)
    return "halyard"  # fallback: trust PATH at hook-run time


def _command_parts(cmd: str) -> list[str]:
    """Split a hook command string while respecting shell quotes."""
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def _hook_command(exe: str, subcommand: str) -> str:
    """Return a shell-safe hook command string for command-style hook APIs."""
    return f"{shlex.quote(exe)} {subcommand}"


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

# Windsurf hook config injected by `halyard install-hook-windsurf`
_WS_HOOKS: dict[str, str] = {
    "pre_user_prompt": "halyard windsurf-session-start",
    "post_cascade_response": "halyard windsurf-session-stop",
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
    """Normalise hook command to subcommand name so absolute paths don't create false duplicates.

    Uses ``Path.stem`` (not ``.name``) so ``halyard.exe`` on Windows and
    ``halyard`` on POSIX produce the same key — otherwise the dedup check
    against an existing settings file with the bare ``halyard`` token would
    miss its own prior install on Windows.
    """
    parts = _command_parts(cmd)
    return f"{Path(parts[0]).stem} {' '.join(parts[1:])}" if parts else cmd


def _is_halyard_hook_cmd(cmd: str) -> bool:
    """True iff *cmd* invokes the halyard binary, regardless of its path.

    Keyed off the basename of arg0 only, so every stale variant
    (uv-tool, repo venv, deleted temp/pipx venvs) is recognised as ours
    while another vendor's command never is.
    """
    parts = _command_parts(cmd)
    return bool(parts) and Path(parts[0]).name in ("halyard", "halyard.exe")


def _resolve_claude_hook_entries(entries: list[dict[str, Any]], exe: str) -> list[dict[str, Any]]:
    """Return a deep copy of Claude hook entries with the halyard binary resolved."""
    resolved_entries: list[dict[str, Any]] = []
    for entry in entries:
        resolved_entry: dict[str, Any] = {**entry}
        raw_hooks = entry.get("hooks")
        if isinstance(raw_hooks, list):
            resolved_hooks: list[dict[str, Any]] = []
            for hook in raw_hooks:
                if isinstance(hook, dict) and isinstance(hook.get("command"), str):
                    command = hook["command"]
                    if command.startswith("halyard "):
                        command = _hook_command(exe, command.removeprefix("halyard "))
                    resolved_hooks.append({**hook, "command": command})
                else:
                    resolved_hooks.append(hook)
            resolved_entry["hooks"] = resolved_hooks
        resolved_entries.append(resolved_entry)
    return resolved_entries


def _cc_hook_commands_from_path(path: Path) -> set[str]:
    """Return normalised command keys from a Claude settings file."""
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
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


class HookWriteError(OSError):
    """A hook settings file could not be written.

    Subclasses OSError so the best-effort auto-install path in
    ``_auto_install_detected_hooks`` (which does ``except OSError``)
    keeps degrading gracefully — a read-only Gemini config must never
    hard-fail ``halyard init``. The explicit ``halyard install-hook-*``
    commands catch this specifically and surface the actionable message.
    """

    def __init__(self, settings_path: Path, original: OSError, message: str | None = None) -> None:
        self.settings_path = settings_path
        self.original = original
        if message is not None:
            super().__init__(message)
        else:
            super().__init__(
                f"could not write {settings_path} — {original.strerror}. "
                "The file may be read-only, or managed by an MDM, "
                "config-management, or dotfile tool that deploys it read-only. "
                "Fix the file's write permission, or add the hook manually."
            )


def _write_settings(settings_path: Path, content: str) -> None:
    """Write a hook settings file, raising HookWriteError on failure.

    Settings files like ``~/.gemini/settings.json`` are sometimes deployed
    read-only by an MDM, config-management, or dotfile tool. An unguarded
    ``write_text`` would crash with a raw traceback.
    """
    try:
        settings_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise HookWriteError(settings_path, exc) from exc


def _load_existing_settings(settings_path: Path) -> dict[str, Any]:
    """Return the parsed settings dict, or {} for absent/empty files.

    A non-empty file that does not parse as JSON (or is unreadable) is
    NOT silently reset to {} — that would overwrite a user's
    hand-maintained config (e.g. JSONC with comments). Raise
    HookWriteError instead: the explicit installer surfaces a clean
    message, and the best-effort auto-install path (except OSError)
    simply skips rather than destroying the file.
    """
    if not settings_path.exists():
        return {}
    try:
        text = settings_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HookWriteError(settings_path, exc) from exc
    if not text.strip():
        return {}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HookWriteError(
            settings_path,
            exc if isinstance(exc, OSError) else OSError(str(exc)),
            message=(
                f"{settings_path} exists but is not valid JSON ({exc}); "
                "refusing to overwrite it. Fix or remove the file, then re-run."
            ),
        ) from exc
    if not isinstance(parsed, dict):
        raise HookWriteError(
            settings_path,
            OSError("not a JSON object"),
            message=(f"{settings_path} is not a JSON object; refusing to overwrite it."),
        )
    return parsed


def _settings_unchanged(settings_path: Path, new_text: str) -> bool:
    """True if *settings_path* already contains exactly *new_text*.

    Lets install be a true no-op (byte-stable file) when nothing needs
    to change, instead of rewriting identical content every run.
    """
    try:
        return settings_path.exists() and settings_path.read_text(encoding="utf-8") == new_text
    except OSError:
        return False


def _run_installer(fn: Callable[[], None]) -> None:
    """Run an explicit ``halyard install-hook-*`` command body.

    Converts a HookWriteError into a clean actionable message and a
    non-zero exit, instead of letting the raw traceback escape. The
    best-effort auto-install path does NOT use this — it relies on the
    ``except OSError`` in ``_auto_install_detected_hooks`` so a read-only
    config never hard-fails ``halyard init``.
    """
    try:
        fn()
    except HookWriteError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1) from exc


def _do_install_hook_claude(global_: bool = False) -> None:
    if global_:
        settings_path = Path.home() / ".claude" / "settings.json"
        other_path = Path.cwd() / ".claude" / "settings.json"
    else:
        settings_path = Path.cwd() / ".claude" / "settings.json"
        other_path = Path.home() / ".claude" / "settings.json"

    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = _load_existing_settings(settings_path)

    exe = _halyard_exe()

    proposed_keys: set[str] = set()
    for entries in _CC_HOOKS.values():
        resolved = _resolve_claude_hook_entries(entries, exe)
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
        resolved = _resolve_claude_hook_entries(entries, exe)
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

    new_text = json.dumps(existing, indent=2) + "\n"
    if _settings_unchanged(settings_path, new_text):
        # Byte-stable no-op (matches the Gemini/Cursor/MCP installers):
        # never rewrite the file or churn its mtime when nothing changed.
        console.print(f"[yellow]Claude Code hooks already present[/] in [bold]{settings_path}[/]")
        return
    _write_settings(settings_path, new_text)

    if added:
        console.print(f"[bold green]Claude Code hooks installed[/] in [bold]{settings_path}[/]")
    else:
        console.print(f"[yellow]Claude Code hooks already present[/] in [bold]{settings_path}[/]")


def _do_install_hook_gemini() -> None:
    settings_path = Path.home() / ".gemini" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = _load_existing_settings(settings_path)

    hooks = existing.setdefault("hooks", {})
    exe = _halyard_exe()

    for event, template in _GC_HOOKS.items():
        command = _hook_command(exe, template.removeprefix("halyard "))
        current = hooks.setdefault(event, [])
        # Drop every prior halyard block for this event (any path,
        # incl. dead venvs), preserving foreign blocks and order, then
        # re-add exactly one for the current binary.
        kept = [
            entry
            for entry in current
            if not any(_is_halyard_hook_cmd(h.get("command", "")) for h in entry.get("hooks", []))
        ]
        kept.append(
            {
                "matcher": "*",
                "hooks": [{"name": "halyard", "type": "command", "command": command}],
            }
        )
        hooks[event] = kept

    new_text = json.dumps(existing, indent=2) + "\n"
    if _settings_unchanged(settings_path, new_text):
        console.print(f"[yellow]Gemini CLI hooks already present[/] in [bold]{settings_path}[/]")
        return
    _write_settings(settings_path, new_text)
    console.print(f"[bold green]Gemini CLI hooks installed[/] in [bold]{settings_path}[/]")


_GEMINI_OTEL_OUTFILE = str(Path.home() / ".halyard" / "gemini-otel.log")


def _do_install_gemini_telemetry() -> None:
    """Configure Gemini's opt-in local OTLP outfile (v2.67).

    Touches only the four telemetry keys Halyard manages; foreign
    telemetry keys (otlpEndpoint, useCollector, …) and every other
    top-level setting are round-tripped intact. Byte-stable no-op when
    already configured. logPrompts is forced false (capture-only
    privacy — Gemini 0.41.1 defaults it true).
    """
    settings_path = Path.home() / ".gemini" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = _load_existing_settings(settings_path)
    tel = existing.setdefault("telemetry", {})
    if not isinstance(tel, dict):
        raise HookWriteError(
            settings_path,
            OSError("telemetry is not a JSON object"),
            message=(
                f"{settings_path} has a non-object `telemetry` value; refusing to overwrite it."
            ),
        )
    tel["enabled"] = True
    tel["target"] = "local"
    tel["outfile"] = _GEMINI_OTEL_OUTFILE
    tel["logPrompts"] = False

    new_text = json.dumps(existing, indent=2) + "\n"
    if _settings_unchanged(settings_path, new_text):
        console.print(f"[yellow]Gemini telemetry already configured[/] in [bold]{settings_path}[/]")
        return
    _write_settings(settings_path, new_text)
    console.print(
        f"[bold green]Gemini telemetry configured[/] "
        f"(outfile [bold]{_GEMINI_OTEL_OUTFILE}[/]) in [bold]{settings_path}[/]"
    )


# --- VS Code Copilot OpenTelemetry (v3.12) --------------------------------

_VSCODE_USER_SETTINGS = (
    Path.home() / "Library" / "Application Support" / "Code" / "User" / "settings.json"
)
# VS Code settings.json uses flat dotted keys (not nested objects).
_VSCODE_OTEL_KEYS: dict[str, Any] = {
    "github.copilot.chat.otel.enabled": True,
    "github.copilot.chat.otel.otlpEndpoint": "http://localhost:4318",
    "github.copilot.chat.otel.exporterType": "http",
}


def _do_install_vscode_otel() -> None:
    """Point VS Code Copilot's OTLP exporter at Halyard's local receiver.

    Writes only the three ``github.copilot.chat.otel.*`` keys; foreign
    settings round-trip intact. Content capture is never enabled (the
    receiver's allowlist drops content regardless). Also writes the
    opt-in marker so ``halyard service`` starts the receiver. Byte-stable
    no-op when already configured.
    """
    from halyard.collectors.vscode_otel import MARKER_PATH

    settings_path = _VSCODE_USER_SETTINGS
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = _load_existing_settings(settings_path)
    existing.update(_VSCODE_OTEL_KEYS)

    new_text = json.dumps(existing, indent=2) + "\n"
    if _settings_unchanged(settings_path, new_text) and MARKER_PATH.exists():
        console.print(
            f"[yellow]VS Code Copilot OTel already configured[/] in [bold]{settings_path}[/]"
        )
        return
    if not _settings_unchanged(settings_path, new_text):
        _write_settings(settings_path, new_text)

    MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    MARKER_PATH.write_text("enabled\n", encoding="utf-8")
    console.print(
        f"[bold green]VS Code Copilot OTel configured[/] "
        f"(endpoint [bold]http://localhost:4318[/]) in [bold]{settings_path}[/]\n"
        "[dim]Restart VS Code, then ensure 'halyard service' is running to receive sessions.[/]"
    )


def _do_uninstall_vscode_otel() -> None:
    """Remove the three OTel keys and the opt-in marker (best-effort)."""
    from halyard.collectors.vscode_otel import MARKER_PATH

    settings_path = _VSCODE_USER_SETTINGS
    if settings_path.exists():
        existing: dict[str, Any] = _load_existing_settings(settings_path)
        removed = False
        for key in _VSCODE_OTEL_KEYS:
            if key in existing:
                del existing[key]
                removed = True
        if removed:
            _write_settings(settings_path, json.dumps(existing, indent=2) + "\n")

    MARKER_PATH.unlink(missing_ok=True)
    console.print(
        f"[bold green]VS Code Copilot OTel disabled[/] (keys removed from [bold]{settings_path}[/])"
    )


def _do_install_hook_cursor() -> None:
    settings_path = Path.home() / ".cursor" / "hooks.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = _load_existing_settings(settings_path)

    existing.setdefault("version", 1)
    hooks = existing.setdefault("hooks", {})
    exe = _halyard_exe()

    for event, template in _CURSOR_HOOKS.items():
        command = _hook_command(exe, template.removeprefix("halyard "))
        current = hooks.setdefault(event, [])
        # Keep foreign entries (bun/other vendors) in place; collapse
        # every prior halyard entry (any path) to one for current exe.
        kept = [e for e in current if not _is_halyard_hook_cmd(e.get("command", ""))]
        kept.append({"command": command})
        hooks[event] = kept

    new_text = json.dumps(existing, indent=2) + "\n"
    if _settings_unchanged(settings_path, new_text):
        console.print(f"[yellow]Cursor hooks already present[/] in [bold]{settings_path}[/]")
        return
    _write_settings(settings_path, new_text)
    console.print(f"[bold green]Cursor hooks installed[/] in [bold]{settings_path}[/]")


def _do_install_hook_windsurf() -> None:
    settings_path = Path.home() / ".codeium" / "windsurf" / "hooks.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = _load_existing_settings(settings_path)

    hooks = existing.setdefault("hooks", {})
    exe = _halyard_exe()

    for event, template in _WS_HOOKS.items():
        command = _hook_command(exe, template.removeprefix("halyard "))
        current = hooks.setdefault(event, [])
        # Windsurf hook entries include "show_output": false
        kept = [e for e in current if not _is_halyard_hook_cmd(e.get("command", ""))]
        kept.append({"command": command, "show_output": False})
        hooks[event] = kept

    new_text = json.dumps(existing, indent=2) + "\n"
    if _settings_unchanged(settings_path, new_text):
        console.print(f"[yellow]Windsurf hooks already present[/] in [bold]{settings_path}[/]")
        return
    _write_settings(settings_path, new_text)
    console.print(f"[bold green]Windsurf hooks installed[/] in [bold]{settings_path}[/]")


# --- MCP server auto-registration (v2.51) ---------------------------------

_MCP_SERVER_NAME = "halyard"

# client -> (label, the file that client reads its `mcpServers` map
# from). Claude Code's USER-scoped MCP servers live in ~/.claude.json,
# a different file from the ~/.claude/settings.json hooks go in.
_MCP_CLIENTS: dict[str, tuple[str, Path]] = {
    "claude": ("Claude Code", Path.home() / ".claude.json"),
    "cursor": ("Cursor", Path.home() / ".cursor" / "mcp.json"),
    "gemini": ("Gemini CLI", Path.home() / ".gemini" / "settings.json"),
    "windsurf": ("Windsurf", Path.home() / ".codeium" / "windsurf" / "mcp_config.json"),
}


def _mcp_entry(exe: str) -> dict[str, Any]:
    """The `halyard` MCP server entry — identical shape for every client."""
    return {"command": exe, "args": ["mcp"]}


def _do_install_mcp(client: str) -> None:
    """Register the read-only `halyard mcp` server in *client*'s config.

    Touches only the single ``mcpServers.halyard`` key: foreign servers
    (e.g. claude-mem) are never read or modified, and every other
    top-level key in the (often large) config is round-tripped intact.
    Re-running overwrites a stale exe path; a current entry is a
    byte-stable no-op.
    """
    label, path = _MCP_CLIENTS[client]
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = _load_existing_settings(path)

    servers = existing.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise HookWriteError(
            path,
            OSError("mcpServers is not an object"),
            message=(
                f"{path} has a non-object 'mcpServers'; refusing to overwrite it. "
                "Fix or remove that key, then re-run."
            ),
        )

    servers[_MCP_SERVER_NAME] = _mcp_entry(_halyard_exe())

    new_text = json.dumps(existing, indent=2) + "\n"
    if _settings_unchanged(path, new_text):
        console.print(f"[yellow]{label} MCP server already registered[/] in [bold]{path}[/]")
        return
    _write_settings(path, new_text)
    console.print(f"[bold green]{label} MCP server registered[/] in [bold]{path}[/]")


def _auto_install_detected_mcp() -> None:
    """Register the MCP server for every MCP client detected on PATH."""
    found: list[str] = []
    failed: list[str] = []

    for binary, (label, _path) in _MCP_CLIENTS.items():
        if shutil.which(binary):
            try:
                _do_install_mcp(binary)
                found.append(label)
            except OSError:
                failed.append(f"{label} (run halyard install-mcp-{binary})")

    if found:
        console.print(f"[bold green]Auto-registered MCP server:[/] {', '.join(found)}")
    if failed:
        console.print(f"[yellow]MCP register failed:[/] {', '.join(failed)}")


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

    existing: dict[str, Any] = _load_existing_settings(settings_path)

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
    _write_settings(settings_path, json.dumps(existing, indent=2) + "\n")
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
        ("windsurf", "Windsurf", _do_install_hook_windsurf),
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

        raise typer.Exit(code=_run_hook(record_session_start))

    @app.command(name="cc-hook", hidden=True)
    def cc_hook() -> None:
        """Process Claude Code Stop hook payload (called by Stop hook)."""
        from halyard.collectors.claude_code import handle_stop_hook

        raise typer.Exit(code=_run_hook(handle_stop_hook))

    @app.command(name="gc-session", hidden=True)
    def gc_session() -> None:
        """Record Gemini CLI session start (called by SessionStart hook)."""
        from halyard.collectors.gemini_cli import record_session_start

        raise typer.Exit(code=_run_hook(record_session_start))

    @app.command(name="gc-model", hidden=True)
    def gc_model() -> None:
        """Accumulate Gemini CLI token counts (called by AfterModel hook)."""
        from halyard.collectors.gemini_cli import record_model_usage

        raise typer.Exit(code=_run_hook(record_model_usage))

    @app.command(name="gc-hook", hidden=True)
    def gc_hook() -> None:
        """Finalise Gemini CLI session record (called by AfterAgent hook)."""
        from halyard.collectors.gemini_cli import handle_agent_stop

        raise typer.Exit(code=_run_hook(handle_agent_stop))

    @app.command(name="cursor-session", hidden=True)
    def cursor_session() -> None:
        """Record Cursor session start (called by beforeSubmitPrompt hook)."""
        from halyard.collectors.cursor import record_session_start

        raise typer.Exit(code=_run_hook(record_session_start))

    @app.command(name="cursor-hook", hidden=True)
    def cursor_hook() -> None:
        """Process Cursor stop hook payload (called by stop hook)."""
        from halyard.collectors.cursor import handle_stop_hook

        raise typer.Exit(code=_run_hook(handle_stop_hook))

    @app.command(name="windsurf-session-start", hidden=True)
    def windsurf_session_start() -> None:
        """Record Windsurf turn start (called by pre_user_prompt hook)."""
        from halyard.collectors.windsurf import read_payload, record_turn

        raise typer.Exit(code=_run_hook(lambda: record_turn(read_payload(), is_start=True)))

    @app.command(name="windsurf-session-stop", hidden=True)
    def windsurf_session_stop() -> None:
        """Record Windsurf turn stop (called by post_cascade_response hook)."""
        from halyard.collectors.windsurf import read_payload, record_turn

        raise typer.Exit(code=_run_hook(lambda: record_turn(read_payload(), is_start=False)))

    @app.command(name="install-hook-claude")
    def install_hook_claude(
        global_: bool = typer.Option(
            False,
            "--global",
            help="Install into ~/.claude/settings.json instead of .claude/settings.json.",
        ),
    ) -> None:
        """Install Claude Code hooks to auto-capture AI sessions."""
        _run_installer(lambda: _do_install_hook_claude(global_=global_))

    @app.command(name="install-hook", hidden=True)
    def install_hook(
        global_: bool = typer.Option(
            False,
            "--global",
            help="Install into ~/.claude/settings.json instead of .claude/settings.json.",
        ),
    ) -> None:
        """Deprecated alias for install-hook-claude."""
        _run_installer(lambda: _do_install_hook_claude(global_=global_))

    @app.command(name="install-hook-gemini")
    def install_hook_gemini() -> None:
        """Install Gemini CLI hooks to auto-capture AI sessions."""
        _run_installer(_do_install_hook_gemini)

    @app.command(name="install-gemini-hook", hidden=True)
    def install_gemini_hook() -> None:
        """Deprecated alias for install-hook-gemini."""
        _run_installer(_do_install_hook_gemini)

    @app.command(name="install-gemini-telemetry")
    def install_gemini_telemetry() -> None:
        """Enable Gemini's opt-in local OTLP outfile for api/tool time."""
        _run_installer(_do_install_gemini_telemetry)

    @app.command(name="install-vscode-otel")
    def install_vscode_otel() -> None:
        """Wire VS Code Copilot's OTLP exporter to Halyard's local receiver."""
        _run_installer(_do_install_vscode_otel)

    @app.command(name="uninstall-vscode-otel")
    def uninstall_vscode_otel() -> None:
        """Remove the VS Code Copilot OTel keys and stop the receiver opt-in."""
        _run_installer(_do_uninstall_vscode_otel)

    @app.command(name="install-hook-cursor")
    def install_hook_cursor() -> None:
        """Install Cursor hooks to auto-capture AI sessions."""
        _run_installer(_do_install_hook_cursor)

    @app.command(name="install-hook-windsurf")
    def install_hook_windsurf() -> None:
        """Install Windsurf hooks to auto-capture AI sessions."""
        _run_installer(_do_install_hook_windsurf)

    @app.command(name="install-cursor-hook", hidden=True)
    def install_cursor_hook() -> None:
        """Deprecated alias for install-hook-cursor."""
        _run_installer(_do_install_hook_cursor)

    @app.command(name="install-mcp-claude")
    def install_mcp_claude() -> None:
        """Register the read-only Halyard MCP server with Claude Code."""
        _run_installer(lambda: _do_install_mcp("claude"))

    @app.command(name="install-mcp-cursor")
    def install_mcp_cursor() -> None:
        """Register the read-only Halyard MCP server with Cursor."""
        _run_installer(lambda: _do_install_mcp("cursor"))

    @app.command(name="install-mcp-gemini")
    def install_mcp_gemini() -> None:
        """Register the read-only Halyard MCP server with Gemini CLI."""
        _run_installer(lambda: _do_install_mcp("gemini"))

    @app.command(name="install-mcp-windsurf")
    def install_mcp_windsurf() -> None:
        """Register the read-only Halyard MCP server with Windsurf."""
        _run_installer(lambda: _do_install_mcp("windsurf"))

    @app.command(name="install-mcp", hidden=True)
    def install_mcp() -> None:
        """Register the Halyard MCP server with every detected client."""
        _auto_install_detected_mcp()

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
