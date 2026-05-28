"""v5.3 — concurrency + observability hardening.

Covers the three review items:
  #1 readers take a shared lock so they never see a torn line mid-write,
  #2 silent fallbacks are recorded to ~/.halyard/diagnostic.log,
  #3 a Hub slower than the client timeout degrades to a local write.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path

import pytest

from halyard import ai_log
from halyard.ai_log import (
    AI_LOG_FILENAME,
    HEADER,
    AiSession,
    append_session,
    read_locked_file,
)
from halyard.hub_server import HubServer

# --------------------------------------------------------------------------- #
# #1 — reader shared-lock regression
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX flock semantics")
def test_read_lock_waits_for_exclusive_writer(tmp_path: Path) -> None:
    """``read_locked_file`` must block while another process holds LOCK_EX.

    Uses a real subprocess (not a thread) so the shared lock is exercised
    via the OS flock, not the in-process thread lock. The holder keeps the
    exclusive lock for ~0.8s; the reader therefore cannot enter until it is
    released. The assertion is a *lower* bound on the wait — coverage/trace
    instrumentation only inflates it, so it never flakes downward.
    """
    log = tmp_path / AI_LOG_FILENAME
    log.write_text(HEADER, encoding="utf-8")

    script = textwrap.dedent(
        f"""
        import fcntl, time
        with open({str(log)!r}, "a") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            print("locked", flush=True)
            time.sleep(0.8)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        """
    )
    holder = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"

        start = time.monotonic()
        with read_locked_file(log) as fh:
            fh.read()
        waited = time.monotonic() - start

        assert waited > 0.3, f"reader did not wait for the exclusive lock ({waited:.3f}s)"
    finally:
        holder.wait(timeout=5)


# --------------------------------------------------------------------------- #
# #2 — diagnostic log
# --------------------------------------------------------------------------- #


def test_log_diagnostic_writes_one_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    diag = tmp_path / "diagnostic.log"
    monkeypatch.setattr(ai_log, "_HALYARD_DIAG_LOG", diag)

    ai_log.log_diagnostic("something degraded", tool="git", project="acme:auth")

    content = diag.read_text(encoding="utf-8")
    assert "something degraded" in content
    assert "[git]" in content
    assert "[acme:auth]" in content
    # One event => one line.
    assert content.count("\n") == 1


def test_log_diagnostic_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Point the log at an unwritable location; the call must swallow the error.
    monkeypatch.setattr(ai_log, "_HALYARD_DIAG_LOG", Path("/proc/nonexistent/diag.log"))
    ai_log.log_diagnostic("should not raise")


# --------------------------------------------------------------------------- #
# #3 — slow Hub falls back to a local write + diagnostic
# --------------------------------------------------------------------------- #


def test_hub_timeout_falls_back_to_local_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diag = tmp_path / "diagnostic.log"
    monkeypatch.setattr(ai_log, "_HALYARD_DIAG_LOG", diag)

    server = HubServer(project_dir=tmp_path, port=54319)
    handler = server._handler()
    base_do_post = handler.do_POST

    def slow_do_post(self: object) -> None:
        time.sleep(0.3)  # exceed the 150ms client timeout
        base_do_post(self)

    handler.do_POST = slow_do_post  # type: ignore[method-assign]
    monkeypatch.setattr(server, "_handler", lambda: handler)
    server.start()

    monkeypatch.setenv("HALYARD_HUB_PORT", str(server.port))
    monkeypatch.setenv("HALYARD_HUB_HOST", "127.0.0.1")

    session = AiSession(
        start=datetime(2026, 5, 23, 10, 0, 0),
        end=datetime(2026, 5, 23, 10, 5, 0),
        tool="slow-hub-tool",
        model="test-model",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
    )

    try:
        append_session(tmp_path, session)

        log_path = tmp_path / AI_LOG_FILENAME
        assert log_path.exists()
        assert "slow-hub-tool" in log_path.read_text(encoding="utf-8")

        diag_content = diag.read_text(encoding="utf-8")
        assert "hub_client: request failed" in diag_content
        assert "timed out" in diag_content.lower()
    finally:
        server.stop()
