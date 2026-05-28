"""v4.3 Real-Time Dashboard behavior."""

from __future__ import annotations

import json
from datetime import datetime
from http import client
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.dashboard import render_dashboard
from halyard.hub_server import HubServer
from halyard.service import _load_or_create_token


def _init_project(project_dir: Path) -> None:
    (project_dir / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (project_dir / "time.timeclock").write_text("; time\n", encoding="utf-8")
    (project_dir / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")


@pytest.fixture()
def hub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    active = home / ".halyard" / "active"
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", active)
    monkeypatch.setattr("halyard.orchestration._reports_mod._HALYARD_ACTIVE", active)

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _init_project(project_dir)

    server = HubServer(project_dir=project_dir, port=0)
    server.start()
    assert server._server is not None
    yield server, server._server.server_port, project_dir
    server.stop()


def test_dashboard_uses_fragment_patching_not_page_reload(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 23, 10, 0),
            end=datetime(2026, 5, 23, 10, 5),
            tool="codex",
            model="gpt-5",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.001,
            project="acme:auth",
        ),
    )

    html = render_dashboard(tmp_path)

    assert "new EventSource(" in html
    # URL is derived from hub_client.hub_url() (honors HALYARD_HUB_HOST/PORT),
    # defaulting to the loopback Hub address.
    assert "http://127.0.0.1:4318/v1/events" in html
    assert "window.location.reload" not in html
    assert 'data-hub-fragment="timer"' in html
    assert 'data-hub-fragment="sessions"' in html
    assert 'data-hub-fragment="collisions"' in html
    assert "fetch(window.location.href" in html


def test_dashboard_renders_collisions_panel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HALYARD_DISABLE_HUB", "1")  # force local log writes
    _init_project(tmp_path)
    for tool, start, end in [
        ("claude-code", (10, 0), (10, 10)),
        ("cursor", (10, 5), (10, 15)),  # overlaps claude-code on the same branch
    ]:
        append_session(
            tmp_path,
            AiSession(
                start=datetime(2026, 5, 23, *start),
                end=datetime(2026, 5, 23, *end),
                tool=tool,
                model="m",
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.0,
                project="acme:web",
                remote="kormilo/halyard",
                branch="feat/hub",
            ),
        )

    html = render_dashboard(tmp_path)

    assert 'data-hub-fragment="collisions"' in html
    assert "Collisions" in html
    assert "feat/hub" in html
    assert "claude-code" in html
    assert "cursor" in html
    # v5.6: partial refresh swaps the metrics/grid regions in place.
    assert "cur.innerHTML = next.innerHTML" in html


def test_event_stream_delivers_emitted_event(hub) -> None:
    server, port, _ = hub
    conn = client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/v1/events")
    resp = conn.getresponse()

    assert resp.status == 200
    assert resp.getheader("Content-Type") == "text/event-stream"

    server.emit("session_ingested", {"project": "acme:auth"})

    seen = ""
    for _ in range(8):
        line = resp.fp.readline().decode()
        seen += line
        if "session_ingested" in seen:
            break

    conn.close()
    assert "session_ingested" in seen
    assert '"project": "acme:auth"' in seen


def test_timer_mutation_emits_timer_updated(hub) -> None:
    server, port, project_dir = hub
    server.emit = MagicMock()
    token = _load_or_create_token()

    conn = client.HTTPConnection("127.0.0.1", port)
    conn.request(
        "POST",
        "/v1/state/timer",
        body=json.dumps(
            {"action": "start", "project": "acme:auth", "project_dir": str(project_dir)}
        ),
        headers={"Content-Type": "application/json", "X-Halyard-Token": token},
    )
    resp = conn.getresponse()

    assert resp.status == 200
    event_names = [call.args[0] for call in server.emit.call_args_list]
    assert "timer_started" in event_names
    assert "timer_updated" in event_names
