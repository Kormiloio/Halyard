"""Tests for v2.29 platform-guard and _raw_hash fixes."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

from halyard.ai_log import AiSession, parse_sessions, session_hash

# ---------------------------------------------------------------------------
# fcntl platform guard
# ---------------------------------------------------------------------------


def test_locked_file_posix_uses_flock(tmp_path: Path) -> None:
    """On POSIX, locked_file acquires an flock (smoke-test: no error)."""
    if sys.platform == "win32":
        pytest.skip("POSIX-only test")
    from halyard.ai_log import locked_file

    path = tmp_path / "test.log"
    with locked_file(path, "w") as f:
        f.write("hello")
    assert path.read_text(encoding="utf-8") == "hello"


def test_locked_file_with_noop_lock_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When the lock backend is a no-op (unknown platform), writes still succeed."""
    import halyard.ai_log as ai_log_mod

    monkeypatch.setattr(ai_log_mod, "_acquire_lock", lambda _fd: None)
    monkeypatch.setattr(ai_log_mod, "_release_lock", lambda _fd: None)
    from halyard.ai_log import locked_file

    path = tmp_path / "test.log"
    with locked_file(path, "w") as f:
        f.write("noop-lock")
    assert path.read_text(encoding="utf-8") == "noop-lock"


def test_locked_file_releases_on_exception(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If the caller raises inside the with block, the lock is still released."""
    import halyard.ai_log as ai_log_mod

    acquired: list[int] = []
    released: list[int] = []
    monkeypatch.setattr(ai_log_mod, "_acquire_lock", lambda fd: acquired.append(fd))
    monkeypatch.setattr(ai_log_mod, "_release_lock", lambda fd: released.append(fd))
    from halyard.ai_log import locked_file

    path = tmp_path / "test.log"
    with pytest.raises(RuntimeError, match="boom"), locked_file(path, "w"):
        raise RuntimeError("boom")

    assert len(acquired) == 1
    assert acquired == released


def test_lock_backend_is_bound() -> None:
    """The acquire/release helpers are bound to callables at import time."""
    import halyard.ai_log as ai_log_mod

    assert callable(ai_log_mod._acquire_lock)
    assert callable(ai_log_mod._release_lock)


# ---------------------------------------------------------------------------
# AiSession._raw_hash — set at parse time, stable across amendment folding
# ---------------------------------------------------------------------------


_S_LINE = (
    "s 2026-05-09T10:00:00 2026-05-09T10:30:00 claude-code claude-sonnet-4-6 "
    "1000 200 0.0030 project=myproj"
)
_A_LINE_TPL = (
    "a {hash} pr_ref=myorg/myrepo#42 pr_state=merged outcome_resolved_at=2026-05-09T11:00:00"
)


def _write_log(log_dir: Path, lines: list[str]) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "ai-sessions.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_raw_hash_set_on_parse(tmp_path: Path) -> None:
    """_raw_hash matches the hash of the original s-line."""
    _write_log(tmp_path, [_S_LINE])
    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 1
    expected = session_hash(_S_LINE)
    assert sessions[0]._raw_hash == expected


def test_raw_hash_stable_after_amendment(tmp_path: Path) -> None:
    """_raw_hash is the hash of the original s-line even after an amendment is folded in."""
    original_hash = session_hash(_S_LINE)
    a_line = _A_LINE_TPL.format(hash=original_hash)
    _write_log(tmp_path, [_S_LINE, a_line])
    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 1
    # Amendment was folded: pr_ref should be updated
    assert sessions[0].pr_ref == "myorg/myrepo#42"
    # But _raw_hash must still be the original s-line hash
    assert sessions[0]._raw_hash == original_hash


def test_raw_hash_none_for_synthetic_session() -> None:
    """AiSession created directly (not via parse_sessions) has _raw_hash=None."""
    session = AiSession(
        start=datetime(2026, 5, 9, 10, 0),
        end=datetime(2026, 5, 9, 10, 30),
        tool="claude-code",
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=20,
        cost_usd=0.001,
    )
    assert session._raw_hash is None
