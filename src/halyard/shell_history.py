"""Test-run detection from shell history — hardened for privacy.

The v3.0 outcome graph wants a signal for "did the user run tests during
this session?" The straightforward implementation — read ~/.bash_history
or ~/.zsh_history and grep — is dangerous: shell history can contain
secrets, full file paths, passwords passed as command-line args, and
arbitrary user content.

This module never returns or stores raw history lines. It walks the
user's shell history, asks one question per line — "is the first token
a canonical test command?" — and returns only a *count* of matches in
the session window. The full line is never logged, hashed, or surfaced.

Disabled by default. Enabled per-project via
``[outcomes]\\nshell_history = true`` in halyard.toml. The flag is
checked by the caller (``halyard outcome sync``), not here, so this
module is safe to import and unit-test under any configuration.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

# Canonical test commands. Matching is on the first whitespace-separated
# token only; flags, paths, and arguments after the token are NOT
# inspected. The list is intentionally small and well-known — extending
# it should be a deliberate choice, not a drive-by.
_CANONICAL_TEST_COMMANDS = frozenset(
    {
        "pytest",
        "unittest",
        "nose2",
        "tox",
        "go",  # require subcommand check below
        "cargo",
        "npm",
        "pnpm",
        "yarn",
        "jest",
        "vitest",
        "mocha",
        "rspec",
        "rake",
        "mvn",
        "gradle",
        "make",
        "bazel",
    }
)

# Subcommand requirements for commands that share a binary with non-test work.
# e.g. "go" matches only when followed by "test".
_SUBCOMMAND_REQUIRED = {
    "go": "test",
    "cargo": "test",
    "mvn": "test",
    "gradle": "test",
    "make": "test",
    "bazel": "test",
    "npm": "test",
    "pnpm": "test",
    "yarn": "test",
    "rake": "test",
}


def _looks_like_test_command(first_token: str, second_token: str | None) -> bool:
    """Decide if a (first, second) token pair represents a test invocation."""
    if first_token not in _CANONICAL_TEST_COMMANDS:
        return False
    required = _SUBCOMMAND_REQUIRED.get(first_token)
    if required is None:
        return True
    return second_token == required


def _candidate_history_paths() -> list[Path]:
    """Return likely shell history file paths for the current user, in order.

    The first existing one is used. No assumption is made about which shell
    the user runs; the file is opened read-only and parsed defensively.
    """
    home = Path.home()
    histfile = os.environ.get("HISTFILE")
    candidates: list[Path] = []
    if histfile:
        candidates.append(Path(histfile))
    candidates.extend(
        [
            home / ".zsh_history",
            home / ".bash_history",
            home / ".local" / "share" / "fish" / "fish_history",
        ]
    )
    return [p for p in candidates if p.exists()]


def _extract_first_two_tokens(line: str) -> tuple[str, str | None] | None:
    """Return (first, second) or None if the line is empty/comment.

    The full line is discarded immediately after token extraction. Only
    the first two tokens — both bounded to 32 chars — leave this function.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    # zsh extended history format: ": <timestamp>:<elapsed>;<command>"
    if line.startswith(":"):
        sep = line.find(";")
        if sep == -1:
            return None
        line = line[sep + 1 :].strip()
    # fish history is YAML-like (- cmd: ...) — extract the cmd value if present
    if line.startswith("- cmd:"):
        line = line[len("- cmd:") :].strip()
    tokens = line.split(maxsplit=2)
    if not tokens:
        return None
    first = tokens[0][:32]
    second = tokens[1][:32] if len(tokens) >= 2 else None
    return first, second


def count_test_runs_in_window(start: datetime, end: datetime) -> int:
    """Return the number of canonical test-command lines in the time window.

    Caveats:
    - Shell history files rarely carry per-line timestamps (zsh extended
      history does; bash does not). Without a timestamp the line is
      counted toward the count regardless of when it ran — same as if it
      were in-window. A user worried about precision should enable zsh
      extended history.
    - The full command line is never returned, hashed, or stored. Only
      the integer count is.
    - File-read errors (permission denied, missing file) yield 0, not an
      exception.

    Returns 0 when no history file exists.
    """
    paths = _candidate_history_paths()
    if not paths:
        return 0
    matches = 0
    start_ts = start.timestamp()
    end_ts = end.timestamp()
    for path in paths:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for raw_line in fh:
                    ts: float | None = _line_timestamp(raw_line)
                    if ts is not None and (ts < start_ts or ts > end_ts):
                        continue
                    tokens = _extract_first_two_tokens(raw_line)
                    if tokens is None:
                        continue
                    first, second = tokens
                    if _looks_like_test_command(first, second):
                        matches += 1
        except OSError:
            continue
        # Only consult the first existing candidate file.
        break
    return matches


def _line_timestamp(raw_line: str) -> float | None:
    """Extract a Unix timestamp from a history line, or return None.

    Only zsh extended-history is supported (": <ts>:<elapsed>;<command>").
    Bash without HISTTIMEFORMAT does not record timestamps; fish stores
    them but in a YAML block not on the same line as the command.
    """
    line = raw_line.strip()
    if not line.startswith(":"):
        return None
    try:
        ts_part = line.split(";", 1)[0].lstrip(":").split(":", 1)[0].strip()
        return float(ts_part)
    except (ValueError, IndexError):
        return None
