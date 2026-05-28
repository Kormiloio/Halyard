"""v4.1 Polyglot Proof: direct ingestion and public spec command."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from http import client
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.ai_log import _FIELDS, AI_LOG_FILENAME, AiSession, parse_sessions
from halyard.cli import app
from halyard.hub_server import HubServer


@pytest.fixture()
def hub(tmp_path: Path):
    server = HubServer(project_dir=tmp_path, port=0)
    server.start()
    assert server._server is not None
    yield server, server._server.server_port
    server.stop()


def _post_ingest(port: int, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    conn = client.HTTPConnection("127.0.0.1", port)
    conn.request(
        "POST",
        "/v1/ingest",
        body=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    resp = conn.getresponse()
    body = resp.read().decode()
    return resp.status, json.loads(body or "{}")


def _wait_for_sessions(project_dir: Path, expected: int) -> list[AiSession]:
    for _ in range(20):
        sessions = list(parse_sessions(project_dir))
        if len(sessions) == expected:
            return sessions
        time.sleep(0.1)
    return list(parse_sessions(project_dir))


def test_hub_ingest_accepts_structured_fields(hub, tmp_path: Path) -> None:
    _, port = hub

    status, body = _post_ingest(
        port,
        {
            "fields": {
                "start": "2026-05-23T10:00:00",
                "end": "2026-05-23T10:05:00",
                "tool": "external-tool",
                "model": "model-x",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.01,
                "project": "acme:auth",
                "tags": ["polyglot"],
            }
        },
    )

    assert status == 200
    assert body == {}
    sessions = _wait_for_sessions(tmp_path, 1)
    assert sessions[0].tool == "external-tool"
    assert sessions[0].project == "acme:auth"
    assert sessions[0].tags == ["polyglot"]


def test_hub_ingest_rejects_missing_required_structured_field(hub, tmp_path: Path) -> None:
    _, port = hub

    status, body = _post_ingest(
        port,
        {
            "fields": {
                "end": "2026-05-23T10:05:00",
                "tool": "external-tool",
                "model": "model-x",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.01,
            }
        },
    )

    assert status == 400
    assert "start" in str(body["error"])
    assert not (tmp_path / AI_LOG_FILENAME).exists()


def test_hub_ingest_rejects_unknown_structured_field(hub, tmp_path: Path) -> None:
    _, port = hub

    status, body = _post_ingest(
        port,
        {
            "fields": {
                "start": "2026-05-23T10:00:00",
                "end": "2026-05-23T10:05:00",
                "tool": "external-tool",
                "model": "model-x",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.01,
                "prompt": "must not be accepted",
            }
        },
    )

    assert status == 400
    assert "unknown field" in str(body["error"])
    assert not (tmp_path / AI_LOG_FILENAME).exists()


def test_hub_ingest_rejects_invalid_raw_line(hub, tmp_path: Path) -> None:
    _, port = hub

    status, body = _post_ingest(port, {"line": "not a session"})

    assert status == 400
    assert "expected session line" in str(body["error"])
    assert not (tmp_path / AI_LOG_FILENAME).exists()


def test_hub_ingest_still_accepts_raw_line(hub, tmp_path: Path) -> None:
    _, port = hub
    session = AiSession(
        start=datetime(2026, 5, 23, 10, 0, 0),
        end=datetime(2026, 5, 23, 10, 5, 0),
        tool="shell-tool",
        model="model-y",
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.001,
    )

    status, body = _post_ingest(port, {"line": session.to_log_line()})

    assert status == 200
    assert body == {}
    sessions = _wait_for_sessions(tmp_path, 1)
    assert sessions[0].tool == "shell-tool"


def test_spec_command_includes_all_registered_optional_fields() -> None:
    result = CliRunner().invoke(app, ["spec"])

    assert result.exit_code == 0
    assert "s <start> <end> <tool> <model>" in result.output
    assert "a <session_hash> key=value" in result.output
    for field in _FIELDS:
        assert f"`{field.key}`" in result.output


def test_reference_shell_emitter_exists_without_python_dependency() -> None:
    script = Path("samples/emit-session.sh")

    assert script.exists()
    text = script.read_text(encoding="utf-8")
    assert os.access(script, os.X_OK)
    assert "curl" in text
    assert "python" not in text.lower()
