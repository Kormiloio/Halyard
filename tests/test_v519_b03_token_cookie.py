"""v5.19/B3 — the dashboard only hands the token cookie to a request that
already presents the token (launch-URL ?token=, header, or cookie).

Previously every GET set the cookie, so a co-located local user could `curl`
the page and harvest the token — which (post-B4) grants full write access.

v5.19/B3-page (parallel-review follow-up): the page *itself* is gated too.
The original B3 fix only stopped the Set-Cookie leak; the HTML body still
rendered the full ledger (costs, projects, branches, home-directory paths)
for any unauthenticated GET. The dashboard now returns 401 unless the
request carries the token.
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
    tmp_path: Path,
    path: str,
    extra_headers: dict[str, str] | None = None,
    method: str = "GET",
) -> tuple[int, str | None, bytes]:
    handler_cls = _handler_for(tmp_path, token=_VALID_TOKEN)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_port
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()
    headers = {"Host": f"127.0.0.1:{port}"}
    if extra_headers:
        headers.update(extra_headers)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, headers=headers)
    resp = conn.getresponse()
    body = resp.read()
    set_cookie = resp.getheader("Set-Cookie")
    status = resp.status
    conn.close()
    t.join(timeout=2)
    server.server_close()
    return status, set_cookie, body


# ---------------------------------------------------------------------------
# B3-page: unauthenticated GET must NOT render the dashboard body.
# ---------------------------------------------------------------------------


def test_unauthenticated_get_returns_401(tmp_path: Path) -> None:
    _init_project(tmp_path)
    status, set_cookie, body = _one_get(tmp_path, "/")
    assert status == 401
    assert set_cookie is None  # token NOT handed to an unauthenticated client
    # The 401 body is a fixed terse hint; no dashboard markup.
    assert b"<html" not in body.lower()
    assert b"unauthorized" in body.lower()


def test_unauthenticated_head_returns_401(tmp_path: Path) -> None:
    _init_project(tmp_path)
    status, set_cookie, body = _one_get(tmp_path, "/", method="HEAD")
    assert status == 401
    assert set_cookie is None
    # HEAD never carries a body regardless of status.
    assert body == b""


def test_get_with_launch_url_token_renders_and_sets_cookie(tmp_path: Path) -> None:
    _init_project(tmp_path)
    status, set_cookie, body = _one_get(tmp_path, f"/?token={_VALID_TOKEN}")
    assert status == 200
    assert set_cookie is not None
    assert _VALID_TOKEN in set_cookie
    assert b"<html" in body.lower()


def test_get_with_valid_cookie_renders_and_refreshes_cookie(tmp_path: Path) -> None:
    _init_project(tmp_path)
    status, set_cookie, body = _one_get(
        tmp_path, "/", extra_headers={"Cookie": f"halyard_token={_VALID_TOKEN}"}
    )
    assert status == 200
    assert set_cookie is not None
    assert b"<html" in body.lower()


def test_get_with_valid_header_renders(tmp_path: Path) -> None:
    _init_project(tmp_path)
    status, _set_cookie, body = _one_get(
        tmp_path, "/", extra_headers={"X-Halyard-Token": _VALID_TOKEN}
    )
    assert status == 200
    assert b"<html" in body.lower()


def test_get_with_wrong_token_returns_401(tmp_path: Path) -> None:
    _init_project(tmp_path)
    status, set_cookie, body = _one_get(tmp_path, "/?token=" + ("b" * 64))
    assert status == 401
    assert set_cookie is None
    assert b"<html" not in body.lower()
