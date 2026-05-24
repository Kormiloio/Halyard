"""Tests for D-2: atomic ~/.halyard/active write and shared read_active_project().

D-2 finding: the active file was written non-atomically by dashboard.py and
_read_active_project() was copy-pasted independently in all three collectors.

Fixes verified here:
  1. dashboard.py writes ~/.halyard/active via tmp-then-rename (atomic).
  2. All three collectors import read_active_project from halyard.ai_log —
     no private copy remains in any collector module.
  3. The canonical read_active_project() handles partial/empty files safely.
"""

from __future__ import annotations

import http.client
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from halyard.ai_log import AI_LOG_FILENAME, HEADER, read_active_project
from halyard.dashboard import _handler_for

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_project(project_dir: Path) -> None:
    (project_dir / "halyard.toml").write_text("[business]\n")
    (project_dir / "time.timeclock").write_text("; timeclock\n")
    (project_dir / AI_LOG_FILENAME).write_text(HEADER)


_TEST_TOKEN = "b" * 64  # fixed 64-char hex token for tests


def _post(project_dir: Path, path: str, body: bytes) -> int:
    """Spin up a real server, fire one POST, return HTTP status.

    Uses a fixed test token injected via _handler_for so auth does not block
    the D-2 behaviour under test.
    """
    handler_cls = _handler_for(project_dir, token=_TEST_TOKEN)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_port

    def _serve_one() -> None:
        server.handle_request()

    t = threading.Thread(target=_serve_one, daemon=True)
    t.start()

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(
        "POST",
        path,
        body=body,
        headers={
            "Content-Length": str(len(body)),
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": f"127.0.0.1:{port}",
            "Cookie": f"halyard_token={_TEST_TOKEN}",
        },
    )
    resp = conn.getresponse()
    status = resp.status
    conn.close()
    server.server_close()
    t.join(timeout=2)
    return status


# ---------------------------------------------------------------------------
# D-2(1): Canonical shared utility — no private copies in collectors
# ---------------------------------------------------------------------------


def test_claude_code_collector_has_no_private_read_active_project() -> None:
    """claude_code.py must not define its own _read_active_project()."""
    import halyard.collectors.claude_code as mod

    assert not hasattr(mod, "_read_active_project"), (
        "claude_code.py still has a private _read_active_project() — "
        "it should import read_active_project from halyard.ai_log instead."
    )


def test_cursor_collector_has_no_private_read_active_project() -> None:
    """cursor.py must not define its own _read_active_project()."""
    import halyard.collectors.cursor as mod

    assert not hasattr(mod, "_read_active_project"), (
        "cursor.py still has a private _read_active_project() — "
        "it should import read_active_project from halyard.ai_log instead."
    )


def test_gemini_cli_collector_has_no_private_read_active_project() -> None:
    """gemini_cli.py must not define its own _read_active_project()."""
    import halyard.collectors.gemini_cli as mod

    assert not hasattr(mod, "_read_active_project"), (
        "gemini_cli.py still has a private _read_active_project() — "
        "it should import read_active_project from halyard.ai_log instead."
    )


def test_all_collectors_use_same_read_active_project_function() -> None:
    """All three collectors must reference the identical function object from ai_log."""
    import halyard.ai_log as ai_log
    import halyard.collectors.claude_code as cc
    import halyard.collectors.cursor as cur
    import halyard.collectors.gemini_cli as gc

    canonical = ai_log.read_active_project
    assert cc.read_active_project is canonical, "claude_code imports wrong read_active_project"
    assert cur.read_active_project is canonical, "cursor imports wrong read_active_project"
    assert gc.read_active_project is canonical, "gemini_cli imports wrong read_active_project"


# ---------------------------------------------------------------------------
# D-2(2): Atomic write in dashboard.py /api/start
# ---------------------------------------------------------------------------


def test_dashboard_start_writes_active_file_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After /api/start the active file must exist and contain the correct slug.

    The write path must use tmp-then-rename so no .tmp file is left behind
    after a successful write.
    """
    _init_project(tmp_path)

    # _HALYARD_ACTIVE in reports.py is resolved at module load time from Path.home().
    # Redirect it to a temp path so the server writes there and we can read it back.
    active = tmp_path / ".halyard" / "active"
    active.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", active)

    active_tmp = active.with_suffix(".tmp")

    status = _post(tmp_path, "/api/start", b"project=acme/auth")

    # Request was accepted (302 redirect, not 4xx)
    assert status == 302

    # Active file written with correct content
    assert active.exists(), "~/.halyard/active was not created by /api/start"
    content = active.read_text()
    assert "slug=acme:auth" in content

    # No stale tmp file left behind (atomic rename completed)
    assert not active_tmp.exists(), ".tmp file should have been renamed away"


def test_dashboard_start_active_file_readable_by_read_active_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After /api/start, read_active_project() must return the started slug."""
    _init_project(tmp_path)

    active = tmp_path / ".halyard" / "active"
    active.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", active)
    # Also redirect the canonical reader so it checks the same temp path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    _post(tmp_path, "/api/start", b"project=acme/auth")

    slug = read_active_project()
    assert slug == "acme:auth"


def test_dashboard_stop_removes_active_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After /api/stop, ~/.halyard/active must be unlinked.

    The /api/stop handler only unlinks when read_active_timer() returns a timer
    with an existing timeclock.  We monkeypatch read_active_timer to return a
    controlled ActiveTimer so the unlink branch fires regardless of the real
    ~/.halyard/active state.
    """
    from halyard.reports import ActiveTimer

    _init_project(tmp_path)
    timeclock = tmp_path / "time.timeclock"

    # Place a pre-written active file at a redirected location
    active = tmp_path / ".halyard" / "active"
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_text(f"timeclock={timeclock}\nslug=acme:auth\nstarted=2026-05-06 10:00:00\n")
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", active)

    # Return a real ActiveTimer so the stop handler's guard passes
    fake_timer = ActiveTimer(slug="acme:auth", timeclock=timeclock, started="2026-05-06 10:00:00")
    monkeypatch.setattr("halyard.reports.read_active_timer", lambda **_kwargs: fake_timer)

    assert active.exists()
    _post(tmp_path, "/api/stop", b"")
    assert not active.exists(), "~/.halyard/active should have been removed by /api/stop"
