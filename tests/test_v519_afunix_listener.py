"""v5.19/B4 — the Hub's AF_UNIX ingest listener (peer-cred auth)."""

from __future__ import annotations

import json
import socket
import time
from datetime import datetime
from http import HTTPStatus, client
from pathlib import Path

import pytest

from halyard.ai_log import AI_LOG_FILENAME, AiSession
from halyard.hub_server import _AF_UNIX_AVAILABLE, HubServer, hub_socket_path

pytestmark = pytest.mark.skipif(not _AF_UNIX_AVAILABLE, reason="AF_UNIX only (POSIX)")

_PORT = 54331


class _UnixConn(client.HTTPConnection):
    def __init__(self, sock_path: str) -> None:
        super().__init__("localhost", timeout=5)
        self._p = sock_path

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self._p)
        self.sock = s


@pytest.fixture
def hub(tmp_path: Path):
    server = HubServer(project_dir=tmp_path, port=_PORT)
    server.start()
    yield server, tmp_path
    server.stop()


def _line() -> str:
    s = AiSession(
        start=datetime(2026, 5, 6, 10, 0),
        end=datetime(2026, 5, 6, 10, 5),
        tool="t",
        model="m",
        input_tokens=1,
        output_tokens=1,
        cost_usd=0.01,
    )
    return json.dumps({"line": s.to_log_line()})


def test_socket_created_0o600_and_removed_on_stop(tmp_path: Path) -> None:
    server = HubServer(project_dir=tmp_path, port=_PORT)
    server.start()
    sp = hub_socket_path(_PORT)
    try:
        assert sp.exists()
        assert (sp.stat().st_mode & 0o777) == 0o600
    finally:
        server.stop()
    assert not sp.exists()


def test_ingest_over_socket_needs_no_token(hub) -> None:
    _, project_dir = hub
    conn = _UnixConn(str(hub_socket_path(_PORT)))
    # No X-Halyard-Token — same-user peer-cred must authorize.
    conn.request("POST", "/v1/ingest", body=_line(), headers={"Content-Type": "application/json"})
    assert conn.getresponse().status == HTTPStatus.OK
    conn.close()

    log = project_dir / AI_LOG_FILENAME
    for _ in range(30):
        if log.exists() and " m " in log.read_text(encoding="utf-8"):
            break
        time.sleep(0.1)
    assert " m " in log.read_text(encoding="utf-8")


def test_socket_still_enforces_content_type(hub) -> None:
    # CSRF Content-Type guard applies on the socket too (cheap, harmless).
    conn = _UnixConn(str(hub_socket_path(_PORT)))
    conn.request("POST", "/v1/ingest", body=_line(), headers={"Content-Type": "text/plain"})
    assert conn.getresponse().status == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    conn.close()
