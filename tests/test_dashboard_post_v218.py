"""Test backfill for v2.12 dashboard POST endpoints (v2.18 tasks 6.1-6.3)."""

from __future__ import annotations

import http.client
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from halyard.ai_log import AI_LOG_FILENAME, HEADER
from halyard.dashboard import _handler_for

_TOKEN = "b" * 64


@pytest.fixture(autouse=True)
def _isolate_active_timer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the global active-timer state file so tests don't pollute ~/.halyard/active."""
    fake_active = tmp_path / ".halyard" / "active"
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", fake_active)
    monkeypatch.setattr("halyard.orchestration._reports_mod._HALYARD_ACTIVE", fake_active)


def _init_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\nname = 'Test'\n")
    (tmp_path / "time.timeclock").write_text("; time\n")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER)


def _make_server(tmp_path: Path) -> tuple[ThreadingHTTPServer, int]:
    handler_cls = _handler_for(tmp_path, token=_TOKEN)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    return server, server.server_port


def _post(
    server: ThreadingHTTPServer,
    port: int,
    path: str,
    body: bytes,
    extra_headers: dict[str, str] | None = None,
) -> int:
    results: list[int] = []

    def _serve() -> None:
        server.handle_request()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    headers = {
        "Content-Length": str(len(body)),
        "Content-Type": "application/x-www-form-urlencoded",
        "Host": f"127.0.0.1:{port}",
        "X-Halyard-Token": _TOKEN,
    }
    if extra_headers:
        headers.update(extra_headers)

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    resp.read()
    results.append(resp.status)
    conn.close()
    t.join(timeout=2)
    server.server_close()
    return results[0]


# ---------------------------------------------------------------------------
# 6.1: POST /api/start with valid auth writes timeclock entry
# ---------------------------------------------------------------------------


def test_api_start_writes_timeclock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path)
    server, port = _make_server(tmp_path)

    status = _post(server, port, "/api/start", b"project=acme/auth")

    # Server redirects to / after success
    assert status in (302, 200, 303)
    tc = (tmp_path / "time.timeclock").read_text()
    assert "acme:auth" in tc


def test_api_start_converts_slash_to_colon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path)
    server, port = _make_server(tmp_path)

    _post(server, port, "/api/start", b"project=client/project")

    tc = (tmp_path / "time.timeclock").read_text()
    assert "client:project" in tc


# ---------------------------------------------------------------------------
# 6.2: POST /api/stop with valid auth invokes stop_timer (runs backfill)
# ---------------------------------------------------------------------------


def test_api_stop_closes_timeclock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path)

    # Open a timer first — write both the timeclock entry and the active-timer state file
    tc_path = tmp_path / "time.timeclock"
    tc_path.write_text("; time\ni 2026-05-01 09:00:00 acme:auth\n")
    active_path = tmp_path / ".halyard" / "active"
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(f"timeclock={tc_path}\nslug=acme:auth\nstarted=2026-05-01 09:00:00\n")

    server, port = _make_server(tmp_path)
    status = _post(server, port, "/api/stop", b"")

    assert status in (302, 200, 303)
    tc = tc_path.read_text()
    # An "o" clock-out line should have been appended
    assert "o " in tc


# ---------------------------------------------------------------------------
# 6.3: Slug validation — no-slash slugs are silently ignored
# ---------------------------------------------------------------------------


def test_api_start_noslash_slug_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A project slug without a slash does not start a timer."""
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path)
    server, port = _make_server(tmp_path)

    tc_before = (tmp_path / "time.timeclock").read_text()
    _post(server, port, "/api/start", b"project=noslug")
    tc_after = (tmp_path / "time.timeclock").read_text()

    # No new timeclock entry should have been written
    assert tc_before == tc_after


def test_api_start_leading_slash_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A project slug starting with / does not start a timer."""
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path)
    server, port = _make_server(tmp_path)

    tc_before = (tmp_path / "time.timeclock").read_text()
    _post(server, port, "/api/start", b"project=/leading/path")
    tc_after = (tmp_path / "time.timeclock").read_text()

    assert tc_before == tc_after
