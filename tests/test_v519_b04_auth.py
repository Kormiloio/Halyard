"""v5.19/B4 — hub auth + CSRF surface.

Asserts the localhost write/read endpoints now reject unauthenticated and
cross-site-CSRF requests, while a valid token (or SSE ?token= param) works.
"""

from __future__ import annotations

import json
from datetime import datetime
from http import HTTPStatus, client
from pathlib import Path

import pytest

from halyard.ai_log import AiSession
from halyard.hub_server import HubServer
from halyard.service import _load_or_create_token

_PORT = 54320


@pytest.fixture
def hub(tmp_path: Path):
    server = HubServer(project_dir=tmp_path, port=_PORT)
    server.start()
    yield server, _PORT
    server.stop()


def _ingest_body() -> str:
    s = AiSession(
        start=datetime(2026, 5, 6, 10, 0),
        end=datetime(2026, 5, 6, 10, 5),
        tool="t",
        model="m",
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.01,
    )
    return json.dumps({"line": s.to_log_line()})


def test_ingest_without_token_is_unauthorized(hub) -> None:
    _, port = hub
    conn = client.HTTPConnection("127.0.0.1", port)
    conn.request(
        "POST", "/v1/ingest", body=_ingest_body(), headers={"Content-Type": "application/json"}
    )
    assert conn.getresponse().status == HTTPStatus.UNAUTHORIZED


def test_ingest_with_token_succeeds(hub) -> None:
    _, port = hub
    conn = client.HTTPConnection("127.0.0.1", port)
    conn.request(
        "POST",
        "/v1/ingest",
        body=_ingest_body(),
        headers={
            "Content-Type": "application/json",
            "X-Halyard-Token": _load_or_create_token(),
        },
    )
    assert conn.getresponse().status == HTTPStatus.OK


def test_text_plain_csrf_is_rejected(hub) -> None:
    # The owner's repro: a cross-origin browser "simple request" uses
    # text/plain (no preflight). Even with a token it must be refused for
    # lacking application/json — closing the browser-CSRF vector.
    _, port = hub
    conn = client.HTTPConnection("127.0.0.1", port)
    conn.request(
        "POST",
        "/v1/ingest",
        body=_ingest_body(),
        headers={
            "Content-Type": "text/plain",
            "X-Halyard-Token": _load_or_create_token(),
        },
    )
    assert conn.getresponse().status == HTTPStatus.UNSUPPORTED_MEDIA_TYPE


def test_cross_site_sec_fetch_is_rejected(hub) -> None:
    _, port = hub
    conn = client.HTTPConnection("127.0.0.1", port)
    conn.request(
        "POST",
        "/v1/ingest",
        body=_ingest_body(),
        headers={
            "Content-Type": "application/json",
            "Sec-Fetch-Site": "cross-site",
            "X-Halyard-Token": _load_or_create_token(),
        },
    )
    assert conn.getresponse().status == HTTPStatus.UNSUPPORTED_MEDIA_TYPE


def test_state_requires_token(hub) -> None:
    _, port = hub
    conn = client.HTTPConnection("127.0.0.1", port)
    conn.request("GET", "/v1/state")
    assert conn.getresponse().status == HTTPStatus.UNAUTHORIZED


def test_sse_accepts_token_query_param(hub) -> None:
    # EventSource can't set headers; the dashboard passes ?token=.
    _, port = hub
    tok = _load_or_create_token()
    conn = client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", f"/v1/events?token={tok}")
    resp = conn.getresponse()
    assert resp.status == HTTPStatus.OK
    assert resp.getheader("Content-Type") == "text/event-stream"
    conn.close()


def test_sse_without_token_is_unauthorized(hub) -> None:
    _, port = hub
    conn = client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/v1/events")
    assert conn.getresponse().status == HTTPStatus.UNAUTHORIZED


def test_health_stays_open(hub) -> None:
    _, port = hub
    conn = client.HTTPConnection("127.0.0.1", port)
    conn.request("GET", "/health")
    assert conn.getresponse().status == HTTPStatus.OK
