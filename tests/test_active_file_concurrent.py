"""Gaps 2 & 3: Active file concurrency and partial-read safety.

Gap 2: Two concurrent writes — a reader never sees a partial slug.
Gap 3: Truncated write → read_active_project() returns None.
"""

from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path

import pytest

from halyard.ai_log import read_active_project

# ---------------------------------------------------------------------------
# Gap 2: Concurrent write simulation
# ---------------------------------------------------------------------------


def _write_active(home: Path, slug: str, *, delay: float = 0.0) -> None:
    """Simulate the dashboard's atomic active-file write (tmp → rename).

    Uses a per-call unique tmp filename so concurrent writers never collide on
    the same .tmp path.  The .halyard/ directory is created before any write
    so the rename never hits a FileNotFoundError.
    """
    halyard_dir = home / ".halyard"
    halyard_dir.mkdir(parents=True, exist_ok=True)
    active = halyard_dir / "active"
    # Unique per-call tmp name prevents cross-thread clobber
    tmp = halyard_dir / f"active.{uuid.uuid4().hex}.tmp"

    content = f"timeclock=/some/path\nslug={slug}\nstarted=2026-05-08 10:00:00\n"
    tmp.write_text(content)
    if delay:
        time.sleep(delay)
    tmp.replace(active)


def test_concurrent_write_reader_never_sees_partial_slug(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Two threads atomically writing different slugs; reader always gets a complete slug.

    Because writes use tmp-then-rename, any read will see either:
      - no file (before first write)
      - a complete previous slug
      - a complete new slug
    Never a partial or corrupted slug.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    slug_a = "acme:auth-migration"
    slug_b = "globex:reports"

    # Seed the file so the reader has a valid starting state
    _write_active(tmp_path, slug_a)

    results: list[str | None] = []
    corrupt_slugs: list[str] = []
    writer_errors: list[str] = []
    stop_event = threading.Event()

    def reader_thread() -> None:
        while not stop_event.is_set():
            val = read_active_project()
            results.append(val)
            if val is not None and val not in (slug_a, slug_b):
                corrupt_slugs.append(f"Unexpected slug: {val!r}")

    def writer_a() -> None:
        try:
            for _ in range(20):
                _write_active(tmp_path, slug_a)
        except Exception as exc:
            writer_errors.append(f"writer_a: {exc}")

    def writer_b() -> None:
        try:
            for _ in range(20):
                _write_active(tmp_path, slug_b)
        except Exception as exc:
            writer_errors.append(f"writer_b: {exc}")

    reader = threading.Thread(target=reader_thread)
    wa = threading.Thread(target=writer_a)
    wb = threading.Thread(target=writer_b)

    reader.start()
    wa.start()
    wb.start()

    wa.join()
    wb.join()
    stop_event.set()
    reader.join()

    # Writer threads must not have raised any exceptions
    assert not writer_errors, f"Writer thread errors: {writer_errors}"
    # No corrupt/partial slugs should have been observed
    assert not corrupt_slugs, f"Corrupt reads detected: {corrupt_slugs}"
    # At least some reads should have occurred
    assert len(results) > 0


# ---------------------------------------------------------------------------
# Gap 3: Partial active file read
# ---------------------------------------------------------------------------


def test_partial_active_file_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A truncated write (no slug= line) must return None, not a malformed slug."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    active = tmp_path / ".halyard" / "active"
    active.parent.mkdir(parents=True, exist_ok=True)
    # Simulate a truncated write — only partial content, no slug= line yet
    active.write_text("timeclock=/some/path\nslug")  # truncated mid-key

    assert read_active_project() is None


def test_empty_active_file_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An empty active file (zero-byte truncation) must return None."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    active = tmp_path / ".halyard" / "active"
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_text("")

    assert read_active_project() is None


def test_active_file_with_only_other_fields_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An active file with no slug= line returns None (partial write scenario)."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    active = tmp_path / ".halyard" / "active"
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_text("timeclock=/some/path\nstarted=2026-05-08 10:00:00\n")

    assert read_active_project() is None
