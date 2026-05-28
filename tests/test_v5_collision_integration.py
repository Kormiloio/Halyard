"""Integration tests for v5.0 Duplicate-Effort Detection."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from http import client
from pathlib import Path

import pytest

from halyard.ai_log import AiSession
from halyard.hub_server import HubServer


@pytest.fixture()
def hub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Initialize a Halyard project in tmp_path
    (tmp_path / "halyard.toml").write_text("[project]\nslug='test-proj'", encoding="utf-8")
    (tmp_path / "projects.toml").write_text("[[project]]\nslug='test-proj'", encoding="utf-8")
    (tmp_path / "ai-sessions.log").write_text("", encoding="utf-8")

    # Mock DB path so tests don't touch the real user cache
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")

    test_port = 54318
    server = HubServer(project_dir=tmp_path, port=test_port)
    server.start()
    yield server, test_port
    server.stop()


def test_collision_detection_on_ingestion(hub, tmp_path: Path):
    server, port = hub

    # 1. Ingest an initial session on branch 'feat/hub'
    s1 = AiSession(
        start=datetime.now() - timedelta(minutes=10),
        end=datetime.now() - timedelta(minutes=5),
        tool="tool-1",
        model="model-1",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,  # FIXED
        remote="kormilo/halyard",
        branch="feat/hub",
    )

    conn = client.HTTPConnection("127.0.0.1", port)
    conn.request(
        "POST",
        "/v1/ingest",
        body=json.dumps({"line": s1.to_log_line()}),
        headers={"Content-Type": "application/json"},
    )
    assert conn.getresponse().status == 200

    # Wait for write and cache sync
    from halyard.db import get_recent_branch_activity

    for _ in range(20):
        if get_recent_branch_activity("kormilo/halyard", "feat/hub"):
            break
        time.sleep(0.1)

    # 2. Ingest a SECOND session on the SAME branch
    s2 = AiSession(
        start=datetime.now() - timedelta(minutes=2),
        end=datetime.now(),
        tool="tool-2",
        model="model-1",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,  # FIXED
        remote="kormilo/halyard",
        branch="feat/hub",
    )

    # We mock 'emit' to verify it's called with collision_detected
    from unittest.mock import MagicMock

    server.emit = MagicMock()

    conn.request(
        "POST",
        "/v1/ingest",
        body=json.dumps({"line": s2.to_log_line()}),
        headers={"Content-Type": "application/json"},
    )
    assert conn.getresponse().status == 200

    # Verify collision was detected and emitted
    collision_calls = [
        c for c in server.emit.call_args_list if c.args and c.args[0] == "collision_detected"
    ]
    assert len(collision_calls) >= 1
    payload = collision_calls[0].args[1]
    assert payload["branch"] == "feat/hub"
    assert payload["remote"] == "kormilo/halyard"
    assert payload["collision_count"] == 1


def test_cli_collision_warning_ping(hub, tmp_path: Path):
    _server, port = hub

    # 1. Manually add a session to the log (and sync to DB via Hub start)
    s1 = AiSession(
        start=datetime.now() - timedelta(minutes=10),
        end=datetime.now() - timedelta(minutes=5),
        tool="tool-1",
        model="model-1",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,  # FIXED
        remote="kormilo/halyard",
        branch="feat/hub",
    )
    # We must ingest it so it's in the cache for the GET /v1/collisions check
    conn = client.HTTPConnection("127.0.0.1", port)
    conn.request(
        "POST",
        "/v1/ingest",
        body=json.dumps({"line": s1.to_log_line()}),
        headers={"Content-Type": "application/json"},
    )
    conn.getresponse()

    # Wait for write and cache sync
    from halyard.db import get_recent_branch_activity

    for _ in range(20):
        if get_recent_branch_activity("kormilo/halyard", "feat/hub"):
            break
        time.sleep(0.1)

    # 2. Check the collisions endpoint directly
    conn.request("GET", "/v1/collisions?remote=kormilo/halyard&branch=feat/hub")
    resp = conn.getresponse()
    assert resp.status == 200
    data = json.loads(resp.read())
    assert len(data["collisions"]) >= 1
    assert data["collisions"][0]["tool"] == "tool-1"


# ---------------------------------------------------------------------------
# Task 3.3 / 4.2: the CLI warning (used by `start` and `status`) fires on reuse.
# ---------------------------------------------------------------------------


def test_cli_collision_warning_fires_on_branch_reuse(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from halyard import cli_session, git_context, hub_client

    monkeypatch.setattr(git_context, "current_branch", lambda p: "feat/hub")
    monkeypatch.setattr(git_context, "current_remote", lambda p: "kormilo/halyard")
    monkeypatch.setattr(
        hub_client, "check_collisions", lambda r, b: [{"tool": "cursor", "seconds_ago": 120}]
    )

    cli_session._maybe_warn_collision(Path("."))

    out = capsys.readouterr().out
    assert "feat/hub" in out
    assert "cursor" in out
    assert "Overlap detected" in out


def test_cli_collision_warning_silent_when_clean(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from halyard import cli_session, git_context, hub_client

    monkeypatch.setattr(git_context, "current_branch", lambda p: "feat/hub")
    monkeypatch.setattr(git_context, "current_remote", lambda p: "kormilo/halyard")
    monkeypatch.setattr(hub_client, "check_collisions", lambda r, b: [])

    cli_session._maybe_warn_collision(Path("."))

    assert capsys.readouterr().out == ""
