"""v3.3 cross-collector rejection capture — Claude Code and Codex.

Spec: openspec/changes/v3.3-cross-collector-rejection/specs/detection.md
"""

from __future__ import annotations

import json
from pathlib import Path

from halyard.collectors.claude_code import _read_from_transcript
from halyard.collectors.codex_app import _parse_session_file


def test_v33_claude_code_rejection_detection(tmp_path: Path) -> None:
    # GIVEN a transcript with a user denial tool_result
    transcript = tmp_path / "transcript.jsonl"
    deny_msg = "The user doesn't want to proceed with this tool use. The tool use was rejected."
    deny_event = {
        "type": "user",
        "timestamp": "2026-05-22T10:00:00Z",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "content": deny_msg,
                    "is_error": True,
                    "tool_use_id": "toolu_123",
                }
            ],
        },
    }
    transcript.write_text(json.dumps(deny_event) + "\n", encoding="utf-8")

    # WHEN parsing the transcript
    stats = _read_from_transcript(str(transcript))

    # THEN it MUST count as BOTH a tool_error and a rejection
    assert stats.tool_errors == 1
    assert stats.rejected_suggestion_count == 1


def test_v33_claude_code_normal_error_not_rejection(tmp_path: Path) -> None:
    # GIVEN a transcript with a genuine tool error
    transcript = tmp_path / "transcript.jsonl"
    error_event = {
        "type": "user",
        "timestamp": "2026-05-22T10:00:00Z",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "content": "Fatal error: file not found",
                    "is_error": True,
                    "tool_use_id": "toolu_456",
                }
            ],
        },
    }
    transcript.write_text(json.dumps(error_event) + "\n", encoding="utf-8")

    # WHEN parsing the transcript
    stats = _read_from_transcript(str(transcript))

    # THEN it MUST count as a tool_error but NOT a rejection
    assert stats.tool_errors == 1
    assert stats.rejected_suggestion_count == 0


def test_v33_codex_rejection_detection(tmp_path: Path) -> None:
    # GIVEN a Codex rollout with a rejection marker in aggregated_output
    rollout = tmp_path / "rollout-2026-05-22T10-00-00-uuid.jsonl"
    meta = {
        "type": "session_meta",
        "payload": {"timestamp": "2026-05-22T10:00:00Z", "cwd": str(tmp_path)},
    }
    events = [
        meta,
        {
            "type": "event_msg",
            "timestamp": "2026-05-22T10:00:30Z",
            "payload": {
                "type": "exec_command_begin",
                "command": ["ls"],
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-05-22T10:01:00Z",
            "payload": {
                "type": "exec_command_end",
                "status": "failed",
                "aggregated_output": "The user doesn't want to proceed with this tool use.",
            },
        },
        # Token count event to make it a valid session
        {
            "type": "event_msg",
            "timestamp": "2026-05-22T10:02:00Z",
            "payload": {
                "type": "token_count",
                "info": {"total_token_usage": {"input_tokens": 100, "output_tokens": 50}},
            },
        },
    ]
    rollout.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")

    # WHEN importing the Codex session
    result = _parse_session_file(rollout)
    assert result is not None
    session, _ = result

    # THEN it MUST count as BOTH a tool_error and a rejection
    assert session.tool_errors == 1
    assert session.rejected_suggestion_count == 1


def test_v33_codex_rejection_in_agent_message(tmp_path: Path) -> None:
    # GIVEN a Codex rollout with a rejection marker in an agent message
    rollout = tmp_path / "rollout-2026-05-22T10-00-00-uuid.jsonl"
    meta = {
        "type": "session_meta",
        "payload": {"timestamp": "2026-05-22T10:00:00Z", "cwd": str(tmp_path)},
    }
    events = [
        meta,
        {
            "type": "event_msg",
            "timestamp": "2026-05-22T10:01:00Z",
            "payload": {
                "type": "agent_message",
                "message": (
                    "[external_agent_tool_result: error]\nThe user doesn't want to proceed..."
                ),
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-05-22T10:02:00Z",
            "payload": {
                "type": "token_count",
                "info": {"total_token_usage": {"input_tokens": 100, "output_tokens": 50}},
            },
        },
    ]
    rollout.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")

    # WHEN importing the Codex session
    result = _parse_session_file(rollout)
    assert result is not None
    session, _ = result

    # THEN it MUST count as a rejection
    assert session.rejected_suggestion_count == 1
