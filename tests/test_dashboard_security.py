"""Tests for dashboard token authentication (v2.16 C2).

Covers tasks 5.1-5.5:
    5.1 POST without token -> 401
    5.2 POST with wrong Host -> 400
    5.3 POST with cross-origin Referer -> 403  (H-1 regression)
    5.4 POST with valid token + correct Host -> succeeds (not 4xx)
    5.5 POST with Content-Length > 8192 -> 413
"""

from __future__ import annotations

import http.client
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from halyard.ai_log import AI_LOG_FILENAME, HEADER
from halyard.dashboard import _handler_for

_VALID_TOKEN = "a" * 64  # 64-char hex string


def _init_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (tmp_path / "time.timeclock").write_text("; time\n", encoding="utf-8")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")


def _make_server(tmp_path: Path, token: str = _VALID_TOKEN) -> tuple[ThreadingHTTPServer, int]:
    """Spin up a real ThreadingHTTPServer bound on a free port."""
    handler_cls = _handler_for(tmp_path, token=token)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    return server, server.server_port


def _one_post(
    server: ThreadingHTTPServer,
    port: int,
    path: str = "/api/start",
    body: bytes = b"project=acme/auth",
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    """Fire a single POST and return (status_code, response_body)."""
    results: list[tuple[int, bytes]] = []

    def _serve_one() -> None:
        server.handle_request()

    t = threading.Thread(target=_serve_one, daemon=True)
    t.start()

    headers: dict[str, str] = {
        "Content-Length": str(len(body)),
        "Content-Type": "application/x-www-form-urlencoded",
        "Host": f"127.0.0.1:{port}",
    }
    if extra_headers:
        headers.update(extra_headers)

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    resp_body = resp.read()
    results.append((resp.status, resp_body))
    conn.close()
    t.join(timeout=2)
    server.server_close()
    return results[0]


# ---------------------------------------------------------------------------
# 5.1: POST without token → 401
# ---------------------------------------------------------------------------


def test_post_without_token_returns_401(tmp_path: Path) -> None:
    _init_project(tmp_path)
    server, port = _make_server(tmp_path)
    status, body = _one_post(server, port)
    assert status == 401
    assert b"token" in body.lower()


# ---------------------------------------------------------------------------
# 5.2: POST with valid token but wrong Host → 400
# ---------------------------------------------------------------------------


def test_post_wrong_host_returns_400(tmp_path: Path) -> None:
    _init_project(tmp_path)
    server, port = _make_server(tmp_path)
    cookie = f"halyard_token={_VALID_TOKEN}"
    status, body = _one_post(
        server,
        port,
        extra_headers={
            "Cookie": cookie,
            "Host": "localhost:9999",  # wrong host
        },
    )
    assert status == 400
    assert b"Host" in body or b"host" in body or b"invalid" in body.lower()


# ---------------------------------------------------------------------------
# 5.3: POST with valid token, correct Host, but cross-origin Referer → 403
# ---------------------------------------------------------------------------


def test_post_cross_origin_referer_returns_403(tmp_path: Path) -> None:
    _init_project(tmp_path)
    server, port = _make_server(tmp_path)
    cookie = f"halyard_token={_VALID_TOKEN}"
    status, body = _one_post(
        server,
        port,
        extra_headers={
            "Cookie": cookie,
            "Referer": "http://evil.example.com/page",
        },
    )
    assert status == 403
    assert b"origin" in body.lower() or b"cross" in body.lower()


# ---------------------------------------------------------------------------
# 5.4: POST with valid token + correct Host → succeeds (not a 4xx)
# ---------------------------------------------------------------------------


def test_post_valid_token_and_host_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import halyard.reports

    # Redirect the active timer file so the test doesn't write to real ~/.halyard/
    fake_active = tmp_path / ".halyard" / "active"
    fake_active.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(halyard.reports, "_HALYARD_ACTIVE", fake_active)

    _init_project(tmp_path)
    server, port = _make_server(tmp_path)
    cookie = f"halyard_token={_VALID_TOKEN}"
    status, _body = _one_post(
        server,
        port,
        extra_headers={"Cookie": cookie},
    )
    # Should redirect (302) or 200 — not any 4xx rejection
    assert status < 400, f"Expected success, got {status}"


# ---------------------------------------------------------------------------
# 5.5: POST with Content-Length > 8192 → 413
# ---------------------------------------------------------------------------


def test_post_oversized_body_returns_413(tmp_path: Path) -> None:
    _init_project(tmp_path)
    server, port = _make_server(tmp_path)
    cookie = f"halyard_token={_VALID_TOKEN}"
    # Send Content-Length header claiming >8192 bytes (the actual body size
    # doesn't matter — the server rejects before reading)
    big_body = b"x" * 8193
    status, body = _one_post(
        server,
        port,
        body=big_body,
        extra_headers={"Cookie": cookie},
    )
    assert status == 413
    assert b"large" in body.lower() or b"413" in body or b"body" in body.lower()


# ---------------------------------------------------------------------------
# Regression: X-Halyard-Token header also works (alternative to cookie)
# ---------------------------------------------------------------------------


def test_post_x_halyard_token_header_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import halyard.reports

    fake_active = tmp_path / ".halyard" / "active"
    fake_active.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(halyard.reports, "_HALYARD_ACTIVE", fake_active)

    _init_project(tmp_path)
    server, port = _make_server(tmp_path)
    status, _body = _one_post(
        server,
        port,
        extra_headers={"X-Halyard-Token": _VALID_TOKEN},
    )
    assert status < 400, f"X-Halyard-Token should be accepted, got {status}"
