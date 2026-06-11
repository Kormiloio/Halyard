"""v5.19 regression — Hub must serve on platforms without socket.AF_UNIX.

The v5.19/B4 peer-cred listener left two bare ``socket.AF_UNIX`` attribute
accesses in the TCP request path (`_host_ok` and the ingest auth check). On
Windows the attribute does not exist, so EVERY Hub request raised
AttributeError and the client saw RemoteDisconnected — the whole Windows CI
matrix was red from 2026-06-06 until this guard. Simulate the platform by
deleting the attribute and flipping the availability flag, then exercise a
real TCP request end to end.
"""

from __future__ import annotations

import json
import socket
from datetime import datetime
from http.client import HTTPConnection
from pathlib import Path

import pytest

import halyard.hub_server as hub_server_mod
from halyard.ai_log import AiSession
from halyard.hub_server import HubServer
from halyard.peercred import peer_uid


@pytest.fixture()
def windowslike(monkeypatch: pytest.MonkeyPatch) -> None:
    """A platform with no AF_UNIX support (Windows CI)."""
    monkeypatch.setattr(hub_server_mod, "_AF_UNIX_AVAILABLE", False)
    monkeypatch.delattr(socket, "AF_UNIX", raising=False)


def test_hub_serves_tcp_requests_without_af_unix(windowslike: None, tmp_path: Path) -> None:
    server = HubServer(project_dir=tmp_path, port=0)
    server.start()
    try:
        conn = HTTPConnection("127.0.0.1", server.port, timeout=5)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        # The exact status is not the point — pre-fix, the handler thread
        # died on AttributeError and the client got RemoteDisconnected
        # before any response at all.
        assert resp.status in (200, 401, 403)

        session = AiSession(
            start=datetime(2026, 6, 10, 10, 0, 0),
            end=datetime(2026, 6, 10, 10, 5, 0),
            tool="test-tool",
            model="test-model",
            input_tokens=10,
            output_tokens=20,
            cost_usd=0.0,
        )
        conn.request(
            "POST",
            "/v1/ingest",
            body=json.dumps({"line": session.to_log_line()}),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{server.port}"},
        )
        resp2 = conn.getresponse()
        assert resp2.status in (200, 401, 403)
        conn.close()
    finally:
        server.stop()


def test_peer_uid_returns_none_without_af_unix(
    windowslike: None,
) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        assert peer_uid(s) is None
    finally:
        s.close()
