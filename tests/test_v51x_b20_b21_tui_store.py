"""Regression tests for v5.1x TUI store blockers B20 and B21.

B20 (branch filter reads dead legacy tag): ``branches()`` and
``filter(branch=...)`` scanned the legacy ``branch:`` TAG, but current
collectors write the branch as the ``session.branch`` FIELD. The fix
reads the field so the ``b`` selector and branch filter actually work.

B21 (live-tail uses platform encoding): ``read_new_lines()`` opened the
log with the platform default encoding while the writer uses
``encoding="utf-8"``. On a non-UTF-8 locale a non-ASCII session would
mis-decode or raise ``UnicodeDecodeError`` out of the awatch worker,
silently killing live updates. The fix opens utf-8 / ``newline=""`` and
degrades gracefully on a decode error.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from halyard.ai_log import HEADER, AiSession, append_session
from halyard.tui.store import SessionStore


def _session(
    *,
    start: datetime | None = None,
    project: str = "acme:auth",
    branch: str | None = None,
    tags: list[str] | None = None,
) -> AiSession:
    start_time = start or datetime(2026, 5, 7, 10)
    return AiSession(
        start=start_time,
        end=start_time + timedelta(minutes=5),
        tool="claude-code",
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=50,
        cost_usd=1.25,
        project=project,
        tokens_available=True,
        tags=tags or [],
        branch=branch,
    )


# ---------------------------------------------------------------------------
# B20 — branch filter / selector reads the session.branch FIELD
# ---------------------------------------------------------------------------


def test_b20_branches_reads_field_not_tag(tmp_path: Path) -> None:
    """branches() surfaces the session.branch field (the buggy case)."""
    store = SessionStore(tmp_path / "ai-sessions.log")
    store.sessions = [
        _session(start=datetime(2026, 5, 7, 12), branch="feature"),
        _session(start=datetime(2026, 5, 7, 10), branch="main"),
    ]

    # Before the fix this returned [] because no session carried a
    # legacy `branch:` tag, so the `b` selector said "No branch tags found".
    assert store.branches() == ["feature", "main"]


def test_b20_filter_matches_branch_field(tmp_path: Path) -> None:
    """filter(branch=...) matches the field, not the dead tag."""
    store = SessionStore(tmp_path / "ai-sessions.log")
    store.sessions = [
        _session(project="acme:auth", branch="main"),
        _session(project="acme:feature", branch="feature"),
    ]

    result = store.filter(time_window="all", branch="main")

    assert len(result) == 1
    assert result[0].project == "acme:auth"


def test_b20_filter_excludes_other_branches(tmp_path: Path) -> None:
    """A branch filter must drop sessions on a different branch."""
    store = SessionStore(tmp_path / "ai-sessions.log")
    store.sessions = [
        _session(branch="main"),
        _session(branch="feature"),
        _session(branch=None),
    ]

    assert store.filter(time_window="all", branch="feature") == [store.sessions[1]]


def test_b20_branches_ignores_unrelated_tags(tmp_path: Path) -> None:
    """Non-branch tags (pr:, client:) must not leak into the branch list."""
    store = SessionStore(tmp_path / "ai-sessions.log")
    store.sessions = [
        _session(tags=["pr:42", "client:acme"], branch="main"),
        _session(tags=["pr:7"], branch=None),
    ]

    assert store.branches() == ["main"]


def test_b20_benign_no_filter_returns_all(tmp_path: Path) -> None:
    """Guard against over-restriction: branch=None keeps every session."""
    store = SessionStore(tmp_path / "ai-sessions.log")
    store.sessions = [
        _session(branch="main"),
        _session(branch="feature"),
        _session(branch=None),
    ]

    assert len(store.filter(time_window="all", branch=None)) == 3


# ---------------------------------------------------------------------------
# B21 — live-tail decodes utf-8 and degrades gracefully on bad bytes
# ---------------------------------------------------------------------------


def _seed_log(log_path: Path) -> SessionStore:
    log_path.write_text(HEADER + "\n", encoding="utf-8")
    store = SessionStore(log_path)
    store.load()
    return store


def test_b21_reads_non_ascii_branch_as_utf8(tmp_path: Path) -> None:
    """A non-ASCII session appended after load is read back intact.

    The writer encodes utf-8; read_new_lines() must too, regardless of
    the platform default locale (the buggy case would mis-decode the
    multibyte branch name).
    """
    log_path = tmp_path / "ai-sessions.log"
    store = _seed_log(log_path)

    append_session(log_path.parent, _session(branch="feature-café", project="prøject:x"))

    new = store.read_new_lines()

    assert len(new) == 1
    assert new[0].branch == "feature-café"
    assert new[0].project == "prøject:x"


def test_b21_decode_error_degrades_instead_of_crashing(tmp_path: Path) -> None:
    """A line of invalid utf-8 bytes must not escape read_new_lines().

    Before the fix a UnicodeDecodeError propagated out of the awatch
    worker and silently killed live updates. Now it degrades to "no new
    lines" so the watch loop survives.
    """
    log_path = tmp_path / "ai-sessions.log"
    store = _seed_log(log_path)

    # Append raw bytes that are not valid utf-8 (lone 0xFF / 0xFE).
    with log_path.open("ab") as handle:
        handle.write(b"\xff\xfe garbage not utf-8\n")

    # Must return cleanly rather than raising UnicodeDecodeError.
    assert store.read_new_lines() == []


def test_b21_recovers_valid_lines_after_truncation(tmp_path: Path) -> None:
    """Benign tailing still works: a normal appended session is picked up."""
    log_path = tmp_path / "ai-sessions.log"
    store = _seed_log(log_path)

    append_session(log_path.parent, _session(project="acme:auth", branch="main"))

    new = store.read_new_lines()

    assert len(new) == 1
    assert new[0].project == "acme:auth"
    assert new[0].branch == "main"
