"""Regression tests for blocker B09 — git argument injection via session ref.

``numstat_summary`` builds ``git diff --numstat <sha_at_start> HEAD`` from a
ref that originates in attacker-influenceable session-state JSON. Without a
literal ``--`` separator AND hex validation, a ref like ``--output=/path``
makes git write its diff to an arbitrary file (clobber); ``-O<file>`` and
``--ext-diff`` widen the impact.

The fix (v5.16/B09):
  1. ``is_valid_git_ref`` rejects anything that is not a bare hex object id.
  2. ``numstat_summary`` validates the ref and appends ``--`` before invoking
     git, so a hostile value can never be parsed as an option.
  3. The two collector call sites (cursor, claude_code) pre-validate too.

These tests prove the malicious input is now neutralised AND that a benign hex
ref still produces the expected line counts (guard against over-restriction).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from halyard.git_context import is_valid_git_ref, numstat_delta, numstat_summary

# ---------------------------------------------------------------------------
# is_valid_git_ref — the validation primitive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ref",
    [
        "abc123",
        "DEADBEEF",
        "0" * 40,
        "a1b2",  # minimum 4 chars
        "0123456789abcdefABCDEF0123456789abcdef01",  # full 40-char SHA
    ],
)
def test_valid_refs_accepted(ref: str) -> None:
    assert is_valid_git_ref(ref) is True


@pytest.mark.parametrize(
    "ref",
    [
        None,
        "",
        "abc",  # too short (<4)
        "g" * 8,  # non-hex
        "0" * 41,  # too long (>40)
        "--output=/tmp/pwned",  # the headline injection
        "-O/tmp/pwned",
        "--ext-diff",
        "abc123 --output=/tmp/pwned",  # embedded option
        "../../etc/passwd",
        "HEAD",  # symbolic refs are not bare hex — rejected by design
        "main",
    ],
)
def test_malicious_or_symbolic_refs_rejected(ref: str | None) -> None:
    assert is_valid_git_ref(ref) is False


# ---------------------------------------------------------------------------
# numstat_summary — argv hardening (mock-based, asserts exact argv shape)
# ---------------------------------------------------------------------------


def _run_ok(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_numstat_summary_appends_double_dash_for_valid_ref(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run", return_value=_run_ok("3\t1\tfile.py\n")) as m:
        result = numstat_summary(tmp_path, "deadbeef")
    assert result == (3, 1, 1)
    argv = m.call_args.args[0]
    # The ref is interpolated, and a literal "--" terminates option parsing.
    assert "deadbeef" in argv
    assert argv[-1] == "--"
    # "--" comes AFTER the ref so the ref is still treated as a revision.
    assert argv.index("deadbeef") < argv.index("--")


def test_numstat_summary_skips_git_for_injection_ref(tmp_path: Path) -> None:
    # A hostile ref must never reach subprocess.run at all.
    with patch("halyard.git_context.subprocess.run") as m:
        assert numstat_summary(tmp_path, "--output=/tmp/pwned") is None
        assert numstat_delta(tmp_path, "--output=/tmp/pwned") is None
    m.assert_not_called()


def test_numstat_summary_skips_git_for_short_ref(tmp_path: Path) -> None:
    with patch("halyard.git_context.subprocess.run") as m:
        assert numstat_summary(tmp_path, "abc") is None
    m.assert_not_called()


# ---------------------------------------------------------------------------
# End-to-end with a real repo — proves NO arbitrary file is written
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def real_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.test")
    _git(repo, "config", "user.name", "T")
    (repo / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def test_malicious_ref_does_not_clobber_file(real_repo: Path, tmp_path: Path) -> None:
    """The headline exploit: a ref of --output=<path> must NOT create that file."""
    target = tmp_path / "pwned.diff"
    assert not target.exists()

    # Make HEAD differ from the start sha so a diff would be produced if run.
    (real_repo / "a.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    _git(real_repo, "add", "a.txt")
    _git(real_repo, "commit", "-q", "-m", "change")

    malicious = f"--output={target}"
    assert numstat_summary(real_repo, malicious) is None
    # The fix must prevent git from ever writing the attacker's file.
    assert not target.exists(), "argument injection wrote an arbitrary file"


def test_benign_ref_still_counts_lines(real_repo: Path) -> None:
    """Guard against over-restriction: a real hex SHA still yields a delta."""
    start_sha = subprocess.run(
        ["git", "-C", str(real_repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert is_valid_git_ref(start_sha)

    (real_repo / "a.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    _git(real_repo, "add", "a.txt")
    _git(real_repo, "commit", "-q", "-m", "add two lines")

    summary = numstat_summary(real_repo, start_sha)
    assert summary is not None
    added, removed, files = summary
    assert added == 2
    assert removed == 0
    assert files == 1

    # numstat_delta delegates and stays consistent.
    assert numstat_delta(real_repo, start_sha) == (2, 0)


def test_short_hex_ref_still_works(real_repo: Path) -> None:
    """A short (abbreviated) hex SHA is a valid ref and must not be rejected."""
    short_sha = subprocess.run(
        ["git", "-C", str(real_repo), "rev-parse", "--short=8", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert is_valid_git_ref(short_sha)

    (real_repo / "a.txt").write_text("one\n", encoding="utf-8")
    _git(real_repo, "add", "a.txt")
    _git(real_repo, "commit", "-q", "-m", "shrink")

    summary = numstat_summary(real_repo, short_sha)
    assert summary is not None
    added, removed, _files = summary
    assert added == 0
    assert removed == 1
