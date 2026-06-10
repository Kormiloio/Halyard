"""v5.19 parallel-review round 4 — single finding: rate history truncates
at file renames.

The previous structural fix walked ``git log --follow --reverse`` and then
called ``git show <sha>:clients.toml`` for every commit — but pre-rename
commits store the file under its old name (e.g. ``customers.toml``), so
``git show`` returned nothing and the whole pre-rename history was
silently dropped from the audit.

The fix walks ``--follow --name-only`` newest-first so each commit reports
its own path, fetches via that path, and reverses in Python.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(args: list[str], cwd: Path, *, date: str = "2026-06-01T10:00:00") -> None:
    """Run a git command with a fixed identity + per-call date."""
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_DATE": date,
            "PATH": "/usr/bin:/bin",
        },
    )


def test_rate_history_preserves_pre_rename_commits(tmp_path: Path) -> None:
    """Reproduces the reviewer's exact scenario:

    * commit A: customers.toml — acme @ 100
    * commit B: customers.toml — acme @ 125
    * commit C: rename customers.toml → clients.toml (no content change)
    * commit D: clients.toml   — acme @ 150

    Expected rates in history: ``[100, 125, 150]`` (the rename commit
    itself contributes nothing because the rate did not change).

    Before the fix, ``git show <sha>:clients.toml`` failed for commits A
    and B (file was named customers.toml then), so only ``150`` was
    returned.
    """
    _git(["init", "-q"], tmp_path)
    # We need an initial commit so subsequent rename detection has
    # something to follow against. Use README so the first real
    # clients-toml-related commit is the customers.toml add.
    (tmp_path / "README.md").write_text("seed\n", encoding="utf-8")
    _git(["add", "README.md"], tmp_path, date="2026-01-01T10:00:00")
    _git(["commit", "-q", "-m", "seed"], tmp_path, date="2026-01-01T10:00:00")

    # A: customers.toml @ 100
    customers = tmp_path / "customers.toml"
    customers.write_text('[[client]]\nslug = "acme"\nhourly_rate = 100.0\n', encoding="utf-8")
    _git(["add", "customers.toml"], tmp_path, date="2026-02-01T10:00:00")
    _git(["commit", "-q", "-m", "add customers"], tmp_path, date="2026-02-01T10:00:00")

    # B: customers.toml @ 125
    customers.write_text('[[client]]\nslug = "acme"\nhourly_rate = 125.0\n', encoding="utf-8")
    _git(["add", "customers.toml"], tmp_path, date="2026-03-01T10:00:00")
    _git(["commit", "-q", "-m", "raise to 125"], tmp_path, date="2026-03-01T10:00:00")

    # C: rename customers.toml → clients.toml (no content change).
    _git(
        ["mv", "customers.toml", "clients.toml"],
        tmp_path,
        date="2026-04-01T10:00:00",
    )
    _git(["commit", "-q", "-m", "rename to clients.toml"], tmp_path, date="2026-04-01T10:00:00")

    # D: clients.toml @ 150
    (tmp_path / "clients.toml").write_text(
        '[[client]]\nslug = "acme"\nhourly_rate = 150.0\n', encoding="utf-8"
    )
    _git(["add", "clients.toml"], tmp_path, date="2026-05-01T10:00:00")
    _git(["commit", "-q", "-m", "raise to 150"], tmp_path, date="2026-05-01T10:00:00")

    from halyard.config_history import rate_history_from_git

    history = rate_history_from_git(tmp_path)
    rates = [c.rate for c in history if c.client_slug == "acme"]
    # Pre-rename rates 100 and 125 must both appear (regression for the
    # rename-truncation bug); 150 is the post-rename value.
    assert rates == [100.0, 125.0, 150.0], f"expected [100, 125, 150], got {rates}"


def test_rate_history_unchanged_for_repo_without_rename(tmp_path: Path) -> None:
    """Sanity: the no-rename happy path still works end-to-end.

    Tightens the contract: with one slug and two distinct rates and no
    rename, history should contain exactly those two rates in order.
    """
    _git(["init", "-q"], tmp_path)
    clients = tmp_path / "clients.toml"
    clients.write_text('[[client]]\nslug = "acme"\nhourly_rate = 100.0\n', encoding="utf-8")
    _git(["add", "clients.toml"], tmp_path, date="2026-02-01T10:00:00")
    _git(["commit", "-q", "-m", "init"], tmp_path, date="2026-02-01T10:00:00")

    clients.write_text('[[client]]\nslug = "acme"\nhourly_rate = 150.0\n', encoding="utf-8")
    _git(["add", "clients.toml"], tmp_path, date="2026-03-01T10:00:00")
    _git(["commit", "-q", "-m", "raise"], tmp_path, date="2026-03-01T10:00:00")

    from halyard.config_history import rate_history_from_git

    rates = [c.rate for c in rate_history_from_git(tmp_path) if c.client_slug == "acme"]
    assert rates == [100.0, 150.0]
