"""Loopback client helpers for the Halyard Hub."""

from __future__ import annotations

import http.client
import json
import os
import socket
from pathlib import Path
from typing import Any

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 4318
_TIMEOUT = 0.15


def _hub_disabled() -> bool:
    return os.environ.get("HALYARD_DISABLE_HUB", "").lower() in {"1", "true", "yes"}


def _hub_host() -> str:
    return os.environ.get("HALYARD_HUB_HOST", _DEFAULT_HOST)


def _hub_port() -> int:
    try:
        return int(os.environ.get("HALYARD_HUB_PORT", str(_DEFAULT_PORT)))
    except ValueError:
        return _DEFAULT_PORT


def hub_port() -> int:
    """Return the configured Hub port (honors HALYARD_HUB_PORT, default 4318)."""
    return _hub_port()


def hub_url() -> str:
    """Return the configured Hub base URL (honors HALYARD_HUB_HOST/PORT)."""
    return f"http://{_hub_host()}:{_hub_port()}"


class _UnixHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection over an AF_UNIX stream socket (v5.19/B4)."""

    def __init__(self, sock_path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self._sock_path = sock_path

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self._sock_path)
        self.sock = s


def _unix_socket_path() -> Path | None:
    """The Hub's AF_UNIX socket for the configured port, or None when the
    socket path doesn't apply (Windows, or an explicit remote host override)."""
    if not hasattr(socket, "AF_UNIX") or os.environ.get("HALYARD_HUB_HOST"):
        return None
    from halyard.hub_server import hub_socket_path

    return hub_socket_path(_hub_port())


def _send(
    conn: http.client.HTTPConnection,
    method: str,
    path: str,
    body: bytes | None,
    headers: dict[str, str],
) -> tuple[int, dict[str, Any]] | None:
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode()
        conn.close()
    except (OSError, http.client.HTTPException, UnicodeDecodeError) as exc:
        # Best-effort loopback call on hot paths (session append, collision
        # check): a down/half-open Hub or a malformed response must degrade to
        # "unavailable" so the caller falls back to a direct local write.
        from halyard.ai_log import log_diagnostic

        log_diagnostic(f"hub_client: request failed ({method} {path}): {exc}")
        return None

    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        data = {}
    return resp.status, data


def _request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    token: bool = False,
) -> tuple[int, dict[str, Any]] | None:
    if _hub_disabled():
        return None

    body = None if payload is None else json.dumps(payload).encode()
    json_headers: dict[str, str] = {"Content-Type": "application/json"} if body is not None else {}

    # v5.19/B4: prefer the AF_UNIX socket — a same-user process authenticates by
    # OS peer-credential, no token needed. Only fall back to TCP+token on a
    # connection failure (a real HTTP response, even non-200, is returned).
    sock_path = _unix_socket_path()
    if sock_path is not None and sock_path.exists():
        unix_conn = _UnixHTTPConnection(str(sock_path), _TIMEOUT)
        result = _send(unix_conn, method, path, body, json_headers)
        if result is not None:
            return result

    headers = dict(json_headers)
    if token:
        from halyard.service import _load_or_create_token

        headers["X-Halyard-Token"] = _load_or_create_token()
    return _send(
        http.client.HTTPConnection(_hub_host(), _hub_port(), timeout=_TIMEOUT),
        method,
        path,
        body,
        headers,
    )


def ping() -> bool:
    """Return True if the Hub answers on /health."""
    response = _request("GET", "/health")
    return response is not None and response[0] == 200


def ingest_line(line: str) -> bool:
    """Send a canonical session line to the Hub. Return True on success."""
    # v5.19/B4: /v1/ingest now requires auth — send the token (a same-user
    # process can read the 0o600 token file; another user cannot).
    response = _request("POST", "/v1/ingest", payload={"line": line}, token=True)
    return response is not None and response[0] == 200


def check_collisions(remote: str, branch: str) -> list[dict[str, Any]] | None:
    """Return recent collisions on remote/branch, or None if the Hub is down."""
    from urllib.parse import urlencode

    query = urlencode({"remote": remote, "branch": branch})
    response = _request("GET", f"/v1/collisions?{query}", token=True)  # v5.19/B4
    if response is None:
        return None
    status, data = response
    if status != 200:
        return None
    collisions = data.get("collisions")
    return collisions if isinstance(collisions, list) else None


def read_state() -> dict[str, Any] | None:
    response = _request("GET", "/v1/state", token=True)  # v5.19/B4
    if response is None:
        return None
    status, data = response
    return data if status == 200 else None


def start_timer(project_dir: Path, project: str) -> dict[str, Any] | None:
    response = _request(
        "POST",
        "/v1/state/timer",
        payload={"action": "start", "project": project, "project_dir": str(project_dir)},
        token=True,
    )
    if response is None:
        return None
    status, data = response
    if status == 200:
        return data
    if status == 409:
        return {"error": "already_running", "project": data.get("project")}
    return _hub_error(status, data)


def stop_timer(project_dir: Path) -> dict[str, Any] | None:
    response = _request(
        "POST",
        "/v1/state/timer",
        payload={"action": "stop", "project_dir": str(project_dir)},
        token=True,
    )
    if response is None:
        return None
    status, data = response
    if status == 200:
        return data
    return _hub_error(status, data)


def _hub_error(status: int, data: dict[str, Any]) -> dict[str, Any]:
    """Marker for 'Hub reachable but rejected the write'.

    Distinct from a ``None`` (Hub unreachable) so state-mutating callers can
    refuse to write divergent local state behind a live Hub's back.
    """
    return {"_hub_error": status, "detail": data.get("error")}


def update_presence(
    action: str,
    *,
    project: str | None = None,
    timeclock: Path | None = None,
    now: str | None = None,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {"action": action}
    if project is not None:
        payload["project"] = project
    if timeclock is not None:
        payload["timeclock"] = str(timeclock)
    if now is not None:
        payload["now"] = now

    response = _request("POST", "/v1/state/presence", payload=payload, token=True)
    if response is None:
        return None
    status, data = response
    if status == 200:
        return data
    return _hub_error(status, data)
