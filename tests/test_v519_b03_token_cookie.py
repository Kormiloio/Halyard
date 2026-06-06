"""v5.19/B3 — the dashboard only hands the token cookie to a request that
already presents the token (launch-URL ?token=, header, or cookie).

Previously every GET set the cookie, so a co-located local user could `curl`
the page and harvest the token — which (post-B4) grants full write access.
"""

from __future__ import annotations

import http.client
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME, HEADER
from halyard.dashboard import _handler_for

_VALID_TOKEN = "a" * 64


def _init_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (tmp_path / "time.timeclock").write_text("; time\n", encoding="utf-8")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")


def _one_get(
    tmp_path: Path, path: str, extra_headers: dict[str, str] | None = None
) -> tuple[int, str | None]:
    handler_cls = _handler_for(tmp_path, token=_VALID_TOKEN)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_port
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()
    headers = {"Host": f"127.0.0.1:{port}"}
    if extra_headers:
        headers.update(extra_headers)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    resp.read()
    set_cookie = resp.getheader("Set-Cookie")
    status = resp.status
    conn.close()
    t.join(timeout=2)
    server.server_close()
    return status, set_cookie


def test_unauthenticated_get_does_not_leak_token(tmp_path: Path) -> None:
    _init_project(tmp_path)
    status, set_cookie = _one_get(tmp_path, "/")
    assert status == 200
    assert set_cookie is None  # token NOT handed to an unauthenticated client


def test_get_with_launch_url_token_sets_cookie(tmp_path: Path) -> None:
    _init_project(tmp_path)
    status, set_cookie = _one_get(tmp_path, f"/?token={_VALID_TOKEN}")
    assert status == 200
    assert set_cookie is not None
    assert _VALID_TOKEN in set_cookie


def test_get_with_valid_cookie_refreshes_cookie(tmp_path: Path) -> None:
    _init_project(tmp_path)
    status, set_cookie = _one_get(
        tmp_path, "/", extra_headers={"Cookie": f"halyard_token={_VALID_TOKEN}"}
    )
    assert status == 200
    assert set_cookie is not None


def test_get_with_wrong_token_does_not_set_cookie(tmp_path: Path) -> None:
    _init_project(tmp_path)
    status, set_cookie = _one_get(tmp_path, "/?token=" + ("b" * 64))
    assert status == 200
    assert set_cookie is None
