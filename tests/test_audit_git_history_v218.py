"""Test backfill for audit git-history path (v2.18 tasks 8.1-8.4)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from halyard.config_history import rate_history_from_git

_CLIENTS_V1 = """\
[[client]]
slug = "acme"
name = "Acme Corp"
hourly_rate = 100.0
"""

_CLIENTS_V2 = """\
[[client]]
slug = "acme"
name = "Acme Corp"
hourly_rate = 150.0
"""


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _make_git_repo(tmp_path: Path) -> Path:
    """Create a temp git repo with two commits to clients.toml."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    # First commit: rate = 100
    (repo / "clients.toml").write_text(_CLIENTS_V1, encoding="utf-8")
    _git(repo, "add", "clients.toml")
    _git(repo, "commit", "-m", "initial rate 100")

    # Second commit: rate = 150
    (repo / "clients.toml").write_text(_CLIENTS_V2, encoding="utf-8")
    _git(repo, "add", "clients.toml")
    _git(repo, "commit", "-m", "raise rate to 150")

    return repo


# ---------------------------------------------------------------------------
# 8.1-8.2: Fixture git repo with two rate commits
# ---------------------------------------------------------------------------


def test_rate_history_from_git_two_changes(tmp_path: Path) -> None:
    repo = _make_git_repo(tmp_path)
    changes = rate_history_from_git(repo)

    # We expect at least one rate change detected from git log
    assert len(changes) >= 1
    rates = [c.rate for c in changes]
    # Either 100 or 150 must appear (depending on diff direction)
    assert any(r in (100.0, 150.0) for r in rates)
    # All changes reference "acme"
    assert all(c.client_slug == "acme" for c in changes)
    assert all(c.source.startswith("git:") for c in changes)


# ---------------------------------------------------------------------------
# 8.3: Repo without clients.toml history — returns empty list
# ---------------------------------------------------------------------------


def test_rate_history_no_clients_toml(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    # No clients.toml ever committed
    changes = rate_history_from_git(repo)
    assert changes == []


# ---------------------------------------------------------------------------
# 8.4: No `git` in PATH — returns empty list, no error
# ---------------------------------------------------------------------------


def test_rate_history_no_git_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate git not being available by making subprocess.run raise FileNotFoundError
    original_run = subprocess.run

    def _no_git(cmd: list[str], **kwargs: object) -> object:
        if cmd[0] == "git":
            raise FileNotFoundError("git not found")
        return original_run(cmd, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("subprocess.run", _no_git)

    changes = rate_history_from_git(tmp_path)
    assert changes == []
