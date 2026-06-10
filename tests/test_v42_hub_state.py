"""v4.2 Hub-managed active state."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from http import client
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.ai_log import read_active_project
from halyard.auto_timer import auto_timer_activity, auto_timer_close_if_stale
from halyard.cli import app
from halyard.hub_server import HubServer
from halyard.orchestration import start_timer, stop_timer
from halyard.reports import read_active_timer
from halyard.service import _load_or_create_token


@pytest.fixture()
def hub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    active = home / ".halyard" / "active"
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", active)
    monkeypatch.setattr("halyard.orchestration._reports_mod._HALYARD_ACTIVE", active)
    monkeypatch.setattr("halyard.auto_timer._AUTO_TIMER_FILE", home / ".halyard" / "auto-timer")

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (project_dir / "time.timeclock").write_text("; timeclock\n", encoding="utf-8")
    # v5.19/B5-followup: the hub now rejects /v1/state/timer requests whose
    # supplied project_dir is not in the registry. Register the fixture dir.
    monkeypatch.setattr("halyard.registry.read_registry", lambda: [project_dir])

    server = HubServer(project_dir=project_dir, port=0)
    server.start()
    assert server._server is not None
    port = server._server.server_port
    monkeypatch.setenv("HALYARD_HUB_PORT", str(port))
    yield server, port, project_dir, home
    server.stop()


def _post_state_timer(
    port: int,
    payload: dict[str, object],
    *,
    token: bool = True,
) -> tuple[int, dict[str, object]]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Halyard-Token"] = _load_or_create_token()
    conn = client.HTTPConnection("127.0.0.1", port)
    conn.request("POST", "/v1/state/timer", body=json.dumps(payload), headers=headers)
    resp = conn.getresponse()
    body = resp.read().decode()
    return resp.status, json.loads(body or "{}")


def _get_state(port: int) -> dict[str, object]:
    conn = client.HTTPConnection("127.0.0.1", port)
    # v5.19/B4: /v1/state now requires auth (it leaks home/project paths).
    conn.request("GET", "/v1/state", headers={"X-Halyard-Token": _load_or_create_token()})
    resp = conn.getresponse()
    assert resp.status == 200
    return json.loads(resp.read().decode())


def test_state_timer_mutation_requires_token(hub) -> None:
    _, port, _, _ = hub

    status, body = _post_state_timer(
        port,
        {"action": "start", "project": "acme:auth"},
        token=False,
    )

    assert status == 401
    assert "token" in str(body["error"])
    assert _get_state(port)["project"] is None


def test_hub_start_updates_state_and_mirrors_active_file(hub) -> None:
    _, port, project_dir, home = hub

    status, body = _post_state_timer(
        port,
        {"action": "start", "project": "acme:auth", "project_dir": str(project_dir)},
    )

    assert status == 200
    assert body["project"] == "acme:auth"
    assert body["timeclock"] == str(project_dir / "time.timeclock")
    assert "i " in (project_dir / "time.timeclock").read_text(encoding="utf-8")
    assert "slug=acme:auth" in (home / ".halyard" / "active").read_text(encoding="utf-8")


def test_library_timer_calls_delegate_to_hub_then_stop(hub) -> None:
    _, port, project_dir, home = hub

    timer = start_timer(project_dir, "acme:auth")

    assert timer.slug == "acme:auth"
    assert read_active_project() == "acme:auth"
    assert read_active_timer() is not None
    assert _get_state(port)["project"] == "acme:auth"

    result = stop_timer(project_dir)

    assert result.was_running is True
    assert result.slug == "acme:auth"
    assert _get_state(port)["project"] is None
    assert not (home / ".halyard" / "active").exists()
    assert "o " in (project_dir / "time.timeclock").read_text(encoding="utf-8")


def test_status_json_reads_active_timer_from_hub(hub) -> None:
    _, _, project_dir, _ = hub
    start_timer(project_dir, "acme:auth")

    result = CliRunner().invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["active"] is True
    assert payload["slug"] == "acme:auth"


def test_auto_timer_presence_is_hub_driven(hub) -> None:
    _, port, project_dir, _ = hub
    timeclock = project_dir / "time.timeclock"
    t0 = datetime(2026, 5, 23, 10, 0, 0)

    auto_timer_activity("acme:web", timeclock, now=t0)

    state = _get_state(port)
    assert state["auto_project"] == "acme:web"
    assert state["last_presence"] == t0.isoformat()
    assert "i 2026-05-23 10:00:00 acme:web  ;auto" in timeclock.read_text(encoding="utf-8")

    closed = auto_timer_close_if_stale(now=t0 + timedelta(minutes=31))

    assert closed is True
    assert _get_state(port)["auto_project"] is None
    assert "o 2026-05-23 10:00:00" in timeclock.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Hub reachable-but-errored: never fall back to a divergent local write.
# (A None from hub_client means "unreachable" → local fallback is still fine;
# these tests cover the distinct "_hub_error" marker path.)
# ---------------------------------------------------------------------------


def test_start_timer_surfaces_hub_error_without_local_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard import hub_client
    from halyard.orchestration import HubStateError, start_timer

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "time.timeclock").write_text("; tc\n", encoding="utf-8")
    active = tmp_path / "active"
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", active)
    monkeypatch.setattr("halyard.orchestration._reports_mod._HALYARD_ACTIVE", active)
    monkeypatch.setattr(
        hub_client, "start_timer", lambda *a, **k: {"_hub_error": 500, "detail": "boom"}
    )

    with pytest.raises(HubStateError):
        start_timer(project_dir, "acme:auth")

    assert not active.exists()
    assert (project_dir / "time.timeclock").read_text(encoding="utf-8") == "; tc\n"


def test_stop_timer_hub_error_is_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from halyard import hub_client
    from halyard.orchestration import stop_timer

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    tc = project_dir / "time.timeclock"
    tc.write_text("i 2026-05-23 10:00:00 acme:auth\n", encoding="utf-8")
    monkeypatch.setattr(hub_client, "stop_timer", lambda *a, **k: {"_hub_error": 500})

    result = stop_timer(project_dir)

    assert result.was_running is False
    assert tc.read_text(encoding="utf-8") == "i 2026-05-23 10:00:00 acme:auth\n"


def test_auto_timer_activity_hub_error_no_local_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard import hub_client
    from halyard.auto_timer import auto_timer_activity

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    tc = project_dir / "time.timeclock"
    tc.write_text("; tc\n", encoding="utf-8")
    auto_file = tmp_path / "auto-timer"
    monkeypatch.setattr("halyard.auto_timer._AUTO_TIMER_FILE", auto_file)
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", tmp_path / "active")
    monkeypatch.setattr(hub_client, "update_presence", lambda *a, **k: {"_hub_error": 500})

    auto_timer_activity("acme:auth", tc)

    assert not auto_file.exists()
    assert tc.read_text(encoding="utf-8") == "; tc\n"
