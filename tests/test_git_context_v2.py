"""Tests for git_context v2.24 additions: head_sha, commits_in_window, numstat_delta."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

import halyard.git_context as git_context_mod
from halyard.git_context import commits_in_window, head_sha, numstat_delta

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE = type("R", (), {})


def _run_ok(stdout: str, returncode: int = 0):  # type: ignore[no-untyped-def]
    r = _FAKE()
    r.stdout = stdout
    r.returncode = returncode
    return r


# ---------------------------------------------------------------------------
# head_sha
# ---------------------------------------------------------------------------


def test_head_sha_returns_12_char_sha(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run", return_value=_run_ok("abc123def456\n")):
        assert head_sha(tmp_path) == "abc123def456"


def test_head_sha_strips_whitespace(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run", return_value=_run_ok("  deadbeef1234  \n")):
        assert head_sha(tmp_path) == "deadbeef1234"


def test_head_sha_returns_none_on_empty_stdout(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run", return_value=_run_ok("")):
        assert head_sha(tmp_path) is None


def test_head_sha_returns_none_on_nonzero_exit(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run", return_value=_run_ok("", returncode=128)):
        assert head_sha(tmp_path) is None


def test_head_sha_returns_none_on_oserror(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run", side_effect=OSError):
        assert head_sha(tmp_path) is None


def test_head_sha_returns_none_on_timeout(tmp_path: Path) -> None:
    with patch(
        "halyard.git_context.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="git", timeout=2),
    ):
        assert head_sha(tmp_path) is None


def test_head_sha_returns_none_on_file_not_found(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run", side_effect=FileNotFoundError):
        assert head_sha(tmp_path) is None


# ---------------------------------------------------------------------------
# commits_in_window
# ---------------------------------------------------------------------------

_START = datetime(2026, 5, 1, 10, 0)
_END = datetime(2026, 5, 1, 11, 0)


def test_commits_in_window_counts_lines(tmp_path: Path) -> None:
    output = "abc1234 first commit\ndef5678 second commit\n"
    with patch("halyard.git_context.subprocess.run", return_value=_run_ok(output)):
        assert commits_in_window(tmp_path, _START, _END) == 2


def test_commits_in_window_empty_output(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run", return_value=_run_ok("")):
        assert commits_in_window(tmp_path, _START, _END) == 0


def test_commits_in_window_ignores_blank_lines(tmp_path: Path) -> None:
    output = "abc1234 commit\n\n  \n"
    with patch("halyard.git_context.subprocess.run", return_value=_run_ok(output)):
        assert commits_in_window(tmp_path, _START, _END) == 1


def test_commits_in_window_returns_none_on_nonzero_exit(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run", return_value=_run_ok("", returncode=128)):
        assert commits_in_window(tmp_path, _START, _END) is None


def test_commits_in_window_returns_none_on_oserror(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run", side_effect=OSError):
        assert commits_in_window(tmp_path, _START, _END) is None


def test_commits_in_window_returns_none_on_timeout(tmp_path: Path) -> None:
    with patch(
        "halyard.git_context.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="git", timeout=2),
    ):
        assert commits_in_window(tmp_path, _START, _END) is None


def test_commits_in_window_returns_none_on_file_not_found(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run", side_effect=FileNotFoundError):
        assert commits_in_window(tmp_path, _START, _END) is None


def test_commits_in_window_passes_since_until_flags(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs):  # type: ignore[no-untyped-def]
        captured.append(cmd)
        return _run_ok("abc commit\n")

    with patch("halyard.git_context.subprocess.run", side_effect=fake_run):
        commits_in_window(tmp_path, _START, _END)

    assert any("--since" in arg for arg in captured[0])
    assert any("--until" in arg for arg in captured[0])
    assert "--oneline" in captured[0]


# ---------------------------------------------------------------------------
# numstat_delta
# ---------------------------------------------------------------------------


def test_numstat_delta_sums_added_removed(tmp_path: Path) -> None:
    output = "10\t3\tsrc/foo.py\n5\t1\tsrc/bar.py\n"
    with patch("halyard.git_context.subprocess.run", return_value=_run_ok(output)):
        result = numstat_delta(tmp_path, "abc123")
        assert result == (15, 4)


def test_numstat_delta_skips_binary_files(tmp_path: Path) -> None:
    output = "10\t2\tsrc/foo.py\n-\t-\tassets/image.png\n"
    with patch("halyard.git_context.subprocess.run", return_value=_run_ok(output)):
        result = numstat_delta(tmp_path, "abc123")
        assert result == (10, 2)


def test_numstat_delta_empty_diff(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run", return_value=_run_ok("")):
        result = numstat_delta(tmp_path, "abc123")
        assert result == (0, 0)


def test_numstat_delta_returns_none_on_nonzero_exit(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run", return_value=_run_ok("", returncode=128)):
        assert numstat_delta(tmp_path, "abc123") is None


def test_numstat_delta_returns_none_on_oserror(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run", side_effect=OSError):
        assert numstat_delta(tmp_path, "abc123") is None


def test_numstat_delta_returns_none_on_timeout(tmp_path: Path) -> None:
    with patch(
        "halyard.git_context.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="git", timeout=2),
    ):
        assert numstat_delta(tmp_path, "abc123") is None


def test_numstat_delta_returns_none_on_file_not_found(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run", side_effect=FileNotFoundError):
        assert numstat_delta(tmp_path, "abc123") is None


# ---------------------------------------------------------------------------
# TOML injection safety — _write_repos_config with hostile keys/values
# ---------------------------------------------------------------------------


def test_write_repos_config_hostile_key_roundtrips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A remote URL with TOML-hostile characters in the key must round-trip."""
    from halyard.git_context import _load_repos_config, _write_repos_config

    config_path = tmp_path / "repos.toml"
    monkeypatch.setattr(git_context_mod, "_REPOS_CONFIG", config_path)

    hostile_key = 'github.com/org/repo"]\n[evil'
    mapping = {hostile_key: "myproject"}
    _write_repos_config(mapping)
    loaded = _load_repos_config()
    assert loaded.get(hostile_key) == "myproject"


def test_write_repos_config_hostile_value_roundtrips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project slug with backslash/quote characters round-trips without TOML error."""
    from halyard.git_context import _load_repos_config, _write_repos_config

    config_path = tmp_path / "repos.toml"
    monkeypatch.setattr(git_context_mod, "_REPOS_CONFIG", config_path)

    hostile_value = "proj\\ninjected = true"
    mapping = {"github.com/org/repo": hostile_value}
    _write_repos_config(mapping)
    loaded = _load_repos_config()
    assert loaded.get("github.com/org/repo") == hostile_value
