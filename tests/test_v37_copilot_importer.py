"""Tests for the GitHub Copilot (VS Code) session importer."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from halyard.ai_log import AI_LOG_FILENAME, parse_sessions
from halyard.collectors.copilot import import_copilot_sessions


@pytest.fixture
def mock_vscode_storage(tmp_path: Path) -> Path:
    storage = tmp_path / "vscode-storage"
    storage.mkdir()

    # Setup Halyard project
    project_dir = tmp_path / "halyard"
    project_dir.mkdir()
    (project_dir / "halyard.toml").write_text('[project]\nslug = "acme:halyard"')
    (project_dir / AI_LOG_FILENAME).write_text("")

    # Project 1: Halyard
    ws1 = storage / "ws1-id"
    ws1.mkdir()
    (ws1 / "workspace.json").write_text(json.dumps({"folder": project_dir.as_uri()}))

    # Session for WS1
    chat_dir = ws1 / "chatSessions"
    chat_dir.mkdir()
    session_id = "session-123"
    (chat_dir / f"{session_id}.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "kind": 0,
                        "v": {
                            "creationDate": 1779548400000,  # 2026-05-23T15:00:00Z
                            "sessionId": session_id,
                            "requests": [],
                        },
                    }
                ),
                json.dumps(
                    {
                        "kind": 2,
                        "k": ["requests"],
                        "v": [
                            {
                                "requestId": "r1",
                                "timestamp": 1779548460000,
                                "response": [
                                    {"kind": "message"},
                                    {"kind": "toolInvocationSerialized"},
                                ],
                            }
                        ],
                    }
                ),
                json.dumps(
                    {
                        "kind": 1,
                        "k": ["requests", 0, "completionTokens"],
                        "v": 500,
                    }
                ),
            ]
        )
    )

    # Edit manifest for WS1
    edit_dir = ws1 / "chatEditingSessions" / session_id
    edit_dir.mkdir(parents=True)
    (edit_dir / "state.json").write_text(
        json.dumps(
            {
                "initialFileContents": [
                    [f"{project_dir.as_uri()}/src/app.py", "hash1"],
                    [f"{project_dir.as_uri()}/tests/test_app.py", "hash2"],
                ]
            }
        )
    )

    return storage


def test_import_copilot_sessions_extracts_metadata(
    mock_vscode_storage: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "halyard"

    # 2. Mock paths
    monkeypatch.setattr("halyard.collectors.copilot._VSCODE_STORAGE_DIR", mock_vscode_storage)
    monkeypatch.setattr("halyard.collectors.copilot._IMPORTED_STATE_FILE", tmp_path / "imported")

    # 3. Import
    sessions = import_copilot_sessions(project_dir=project_dir)

    assert len(sessions) == 1
    s = sessions[0]
    assert s.tool == "github-copilot"
    assert s.output_tokens == 500
    assert s.assistant_message_count == 1
    assert s.user_message_count == 1
    assert s.tool_calls == 1
    assert s.files_touched_count == 2
    assert s.project == "acme:halyard"
    assert s.session_id == "session-123"

    assert isinstance(s.start, datetime)
    assert isinstance(s.end, datetime)

    # 4. Verify log written
    logged = parse_sessions(project_dir)
    assert len(logged) == 1
    assert logged[0].session_id == "session-123"


def test_import_copilot_sessions_idempotency(
    mock_vscode_storage: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "halyard"

    monkeypatch.setattr("halyard.collectors.copilot._VSCODE_STORAGE_DIR", mock_vscode_storage)
    monkeypatch.setattr("halyard.collectors.copilot._IMPORTED_STATE_FILE", tmp_path / "imported")

    # Import twice
    import_copilot_sessions(project_dir=project_dir)
    sessions2 = import_copilot_sessions(project_dir=project_dir)

    assert len(sessions2) == 0


def test_import_copilot_sessions_skips_privacy_content(
    mock_vscode_storage: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Add a session with sensitive text
    ws1 = mock_vscode_storage / "ws1-id"
    (ws1 / "chatSessions" / "secret.jsonl").write_text(
        json.dumps(
            {
                "kind": 2,
                "k": ["requests"],
                "v": [
                    {
                        "requestId": "r2",
                        "timestamp": 1779549000000,
                        "response": [
                            {"kind": "message", "value": "SECRET_KEY=12345"},
                            {"kind": "thinking", "value": "thought"},
                        ],
                    }
                ],
            }
        )
        + "\n"
        + json.dumps(
            {
                "kind": 1,
                "k": ["requests", 0, "completionTokens"],
                "v": 10,
            }
        )
    )

    project_dir = tmp_path / "halyard"

    monkeypatch.setattr("halyard.collectors.copilot._VSCODE_STORAGE_DIR", mock_vscode_storage)
    monkeypatch.setattr("halyard.collectors.copilot._IMPORTED_STATE_FILE", tmp_path / "imported")

    import_copilot_sessions(project_dir=project_dir)

    log_content = (project_dir / AI_LOG_FILENAME).read_text()
    assert "SECRET_KEY" not in log_content
    assert "thought" not in log_content
    assert "10" in log_content
