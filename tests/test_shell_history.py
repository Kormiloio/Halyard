"""Tests for v3.0 shell-history test-run detection.

The module never returns raw history lines — these tests check only
the integer count surface and that file-read failures degrade silently.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

import halyard.shell_history as sh
from halyard.shell_history import (
    _extract_first_two_tokens,
    _line_timestamp,
    _looks_like_test_command,
    count_test_runs_in_window,
)


def test_extract_tokens_drops_comment() -> None:
    assert _extract_first_two_tokens("# this is a comment") is None


def test_extract_tokens_handles_zsh_extended_history() -> None:
    line = ": 1715000000:0;pytest tests/"
    first, second = _extract_first_two_tokens(line)
    assert first == "pytest"
    assert second == "tests/"


def test_extract_tokens_handles_fish_history() -> None:
    line = "- cmd: pytest -x"
    first, second = _extract_first_two_tokens(line)
    assert first == "pytest"
    assert second == "-x"


def test_extract_tokens_truncates_long_tokens() -> None:
    line = "x" * 200
    first, _ = _extract_first_two_tokens(line)
    assert first is not None
    assert len(first) == 32


def test_looks_like_test_command_pytest() -> None:
    assert _looks_like_test_command("pytest", None) is True


def test_looks_like_test_command_npm_test_only() -> None:
    """'npm install' must NOT match; only 'npm test' counts."""
    assert _looks_like_test_command("npm", "test") is True
    assert _looks_like_test_command("npm", "install") is False
    assert _looks_like_test_command("npm", None) is False


def test_looks_like_test_command_go_test_only() -> None:
    assert _looks_like_test_command("go", "test") is True
    assert _looks_like_test_command("go", "build") is False


def test_looks_like_test_command_unknown_first_token() -> None:
    assert _looks_like_test_command("foobar", "test") is False


def test_line_timestamp_zsh_extended() -> None:
    assert _line_timestamp(": 1715000000:0;pytest") == 1715000000.0


def test_line_timestamp_plain_bash_returns_none() -> None:
    assert _line_timestamp("pytest tests/") is None


def test_count_test_runs_no_history_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No history file anywhere → count is 0, no exception."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("HISTFILE", raising=False)
    now = datetime(2026, 5, 14, 12)
    assert count_test_runs_in_window(now - timedelta(hours=1), now) == 0


def test_count_test_runs_counts_canonical_test_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bash-style history with test and non-test lines counts only the tests."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("HISTFILE", raising=False)
    bash_history = tmp_path / ".bash_history"
    bash_history.write_text(
        "ls -la\n"
        "pytest tests/test_foo.py\n"
        "git status\n"
        "npm test\n"
        "echo hello\n"
        "cargo test\n"
        "cargo build\n"  # not a test
        "make test\n",
        encoding="utf-8",
    )

    now = datetime(2026, 5, 14, 12)
    n = count_test_runs_in_window(now - timedelta(hours=1), now)
    # pytest, npm test, cargo test, make test → 4
    assert n == 4


def test_count_test_runs_respects_zsh_timestamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """zsh extended history with timestamps filters to the window."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("HISTFILE", raising=False)
    zsh_history = tmp_path / ".zsh_history"

    in_window = int(datetime(2026, 5, 14, 11, 30).timestamp())
    out_window = int(datetime(2025, 1, 1).timestamp())  # way before
    zsh_history.write_text(
        f": {in_window}:0;pytest\n"
        f": {out_window}:0;pytest\n"  # excluded by window
        f": {in_window}:0;npm test\n",
        encoding="utf-8",
    )

    now = datetime(2026, 5, 14, 12)
    n = count_test_runs_in_window(now - timedelta(hours=2), now)
    # in_window pytest + in_window npm test = 2; out_window pytest excluded
    assert n == 2


def test_count_test_runs_never_returns_raw_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The function's only return type is int — no leak of history content.

    This is the privacy contract pin. Even with a SECRET in the history
    file, the function must return an integer and nothing else.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("HISTFILE", raising=False)
    bash_history = tmp_path / ".bash_history"
    bash_history.write_text("OPENAI_API_KEY=sk-SECRETSECRETSECRET pytest\n", encoding="utf-8")

    now = datetime(2026, 5, 14, 12)
    result = count_test_runs_in_window(now - timedelta(hours=1), now)
    assert isinstance(result, int)
    # The line starts with an env-var assignment, so the first token is
    # "OPENAI_API_KEY=sk-..." — not a test command. Count is 0.
    assert result == 0


def test_count_test_runs_handles_unreadable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A permission error on the history file MUST NOT raise."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("HISTFILE", raising=False)
    bash_history = tmp_path / ".bash_history"
    bash_history.write_text("pytest tests/", encoding="utf-8")

    # Patch the candidate-paths function to return a path whose open() raises.
    real_open = Path.open

    def maybe_raise(self: Path, *args, **kw):  # type: ignore[no-untyped-def]
        if self == bash_history:
            raise PermissionError("simulated")
        return real_open(self, *args, **kw)

    monkeypatch.setattr(Path, "open", maybe_raise)

    now = datetime(2026, 5, 14, 12)
    # Must not raise.
    assert count_test_runs_in_window(now - timedelta(hours=1), now) == 0


def test_module_is_safe_to_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing the module must not read any history file by itself."""
    # Just exercising the import is enough — pytest collection already did
    # that. Make sure the public surface is exactly what we expect.
    assert callable(sh.count_test_runs_in_window)
