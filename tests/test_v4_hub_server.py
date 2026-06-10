"""Tests for the v4.0 Halyard Hub server and ingestion logic."""

from __future__ import annotations

import json
import time
from datetime import datetime
from http import client
from pathlib import Path

import pytest

from halyard.ai_log import AI_LOG_FILENAME, AiSession, parse_sessions
from halyard.hub_server import HubServer


@pytest.fixture()
def hub(tmp_path: Path):
    """Start a HubServer on an OS-chosen free port for testing.

    v5.19/B-port-flake: this used to hard-code 54318 ("a high port to avoid
    conflict with a real hub"), but any other process — another concurrent
    test invocation, a leftover hub, an unrelated local service — bound on
    that port made the full suite fail. ``port=0`` lets the kernel pick a
    free port and ``server.port`` reports back the bound number.
    """
    server = HubServer(project_dir=tmp_path, port=0)
    server.start()
    yield server, server.port
    server.stop()


def test_hub_ingest_direct_session(hub, tmp_path: Path):
    _, port = hub
    session = AiSession(
        start=datetime(2025, 5, 23, 10, 0, 0),
        end=datetime(2025, 5, 23, 10, 5, 0),
        tool="test-tool",
        model="test-model",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
    )

    from halyard.service import _load_or_create_token

    conn = client.HTTPConnection("127.0.0.1", port)
    payload = json.dumps({"line": session.to_log_line()})
    # v5.19/B4: /v1/ingest now requires auth.
    conn.request(
        "POST",
        "/v1/ingest",
        body=payload,
        headers={
            "Content-Type": "application/json",
            "X-Halyard-Token": _load_or_create_token(),
        },
    )
    resp = conn.getresponse()
    assert resp.status == 200

    # Wait for the async worker to write the file
    log_path = tmp_path / AI_LOG_FILENAME
    for _ in range(10):
        if log_path.exists():
            break
        time.sleep(0.5)

    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    # v4.0 FIX: parse_sessions takes the PROJECT DIR, not the file path
    sessions = list(parse_sessions(tmp_path))
    assert len(sessions) == 1, f"Log content: {content!r}"
    assert sessions[0].tool == "test-tool"


def test_hub_ingest_otlp_traces(hub, tmp_path: Path):
    server, port = hub
    # Minimal GenAI OTLP span
    trace_payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "vscode"}}]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "chat",
                                "kind": 2,
                                # May 23, 2025 (in nano)
                                "startTimeUnixNano": "1747994400000000000",
                                "endTimeUnixNano": "1747994700000000000",
                                "attributes": [
                                    {"key": "gen_ai.system", "value": {"stringValue": "openai"}},
                                    {
                                        "key": "gen_ai.usage.input_tokens",
                                        "value": {"intValue": "100"},
                                    },
                                    {
                                        "key": "gen_ai.usage.output_tokens",
                                        "value": {"intValue": "50"},
                                    },
                                    {
                                        "key": "session.id",
                                        "value": {"stringValue": "otel-session-123"},
                                    },
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    conn = client.HTTPConnection("127.0.0.1", port)
    conn.request(
        "POST",
        "/v1/traces",
        body=json.dumps(trace_payload),
        headers={"Content-Type": "application/json"},
    )
    assert conn.getresponse().status == 200

    # Force flush for testing (instead of waiting for IDLE_TTL)
    server.flush_stale(force=True)

    log_path = tmp_path / AI_LOG_FILENAME
    assert log_path.exists()
    # v4.0 FIX: parse_sessions takes the PROJECT DIR
    sessions = list(parse_sessions(tmp_path))
    assert len(sessions) == 1, f"Log content: {log_path.read_text(encoding='utf-8')!r}"
    assert sessions[0].input_tokens == 100
    assert sessions[0].output_tokens == 50
