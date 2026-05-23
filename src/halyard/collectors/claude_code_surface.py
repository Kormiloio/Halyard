"""Heuristic Claude Code surface detection.

This module is intentionally isolated so the surface detection logic can
be tested and replaced independently of the main Claude Code collector.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterable

# Known desktop bundle identifiers observed in Anthropic desktop launches.
# The actual value is best confirmed by a Phase-0 spike before the feature
# lands; these fallback patterns are intentionally conservative.
_DESKTOP_BUNDLE_PREFIXES = (
    "com.anthropic.claude",
    "com.anthropic.claude-code",
    "com.anthropic.Claude",
)

_TERMINAL_PROGRAMS = {
    "apple_terminal",
    "iterm.app",
    "wezterm",
    "alacritty",
    "kitty",
    "tmux",
    "screen",
    "xterm",
    "st",
    "eterm",
    "rxvt",
}

_IDE_PROGRAMS = {"vscode", "jetbrains"}

_DESKTOP_PROCESS_MARKERS = ("claude", "anthropic")


def detect_surface() -> str | None:
    """Return an advisory Claude Code client surface label.

    The return value is one of:
      - "cli"
      - "desktop"
      - "ide"
      - "unknown"
      - None when detection is not attempted or the environment is unusable.
    """
    bundle_id = (
        os.environ.get("__CFBundleIdentifier", "")  # noqa: SIM112
        or os.environ.get("CFBundleIdentifier", "")  # noqa: SIM112
    )
    if bundle_id and _is_desktop_bundle(bundle_id):
        return "desktop"

    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    if term_program == "vscode":
        return "ide"
    if term_program in _IDE_PROGRAMS:
        return "ide"

    if term_program and _is_terminal_program(term_program):
        if _parent_process_chain_contains_desktop():
            return "desktop"
        return "cli"

    if _stdin_is_tty():
        return "cli"

    return "unknown"


def _is_desktop_bundle(bundle_id: str) -> bool:
    normalized = bundle_id.lower()
    return any(normalized.startswith(prefix.lower()) for prefix in _DESKTOP_BUNDLE_PREFIXES)


def _is_terminal_program(term_program: str) -> bool:
    return term_program in _TERMINAL_PROGRAMS or any(
        term_program.startswith(prefix) for prefix in _TERMINAL_PROGRAMS
    )


def _stdin_is_tty() -> bool:
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def _parent_process_chain_contains_desktop() -> bool:
    try:
        ppid = os.getppid()
    except Exception:
        return False

    for parent in _parent_command_names(ppid):
        normalized = parent.lower()
        if any(marker in normalized for marker in _DESKTOP_PROCESS_MARKERS):
            return True
    return False


def _parent_command_names(pid: int) -> Iterable[str]:
    while pid and pid != 1:
        try:
            completed = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm="],
                capture_output=True,
                text=True,
                check=True,
                timeout=0.1,
            )
            command = completed.stdout.strip()
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            PermissionError,
            subprocess.TimeoutExpired,
        ):
            return
        if not command:
            return
        yield command
        try:
            # Walk the ancestor chain by reading the next parent PID.
            parent_info = subprocess.run(
                ["ps", "-p", str(pid), "-o", "ppid="],
                capture_output=True,
                text=True,
                check=True,
                timeout=0.1,
            )
            next_pid = int(parent_info.stdout.strip())
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            PermissionError,
            subprocess.TimeoutExpired,
            ValueError,
        ):
            return
        if next_pid == pid:
            return
        pid = next_pid
