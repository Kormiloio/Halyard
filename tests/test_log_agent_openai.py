"""Tests for the OpenAI-compatible provider in halyard.log_agent."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from halyard.log_agent import LogAgentError, _validate_base_url, run_openai_log_query

_BASE_URL = "https://api.openai.com/v1"
_LOCAL_URL = "http://localhost:11434/v1"
_NOW = datetime(2025, 1, 15, 12, 0, 0)


# ---------------------------------------------------------------------------
# Package import guard
# ---------------------------------------------------------------------------


def test_run_openai_log_query_no_package(tmp_path: Path) -> None:
    with (
        patch.dict(sys.modules, {"openai": None}),
        pytest.raises(LogAgentError, match="pip install halyard\\[openai\\]"),
    ):
        run_openai_log_query(
            "what did I spend",
            project_dir=tmp_path,
            model="gpt-4o",
            base_url=_BASE_URL,
            now=_NOW,
        )


# ---------------------------------------------------------------------------
# API key checks
# ---------------------------------------------------------------------------


def test_run_openai_log_query_no_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    mock_openai = MagicMock()
    with (
        patch.dict(sys.modules, {"openai": mock_openai}),
        pytest.raises(LogAgentError, match="OPENAI_API_KEY not set"),
    ):
        run_openai_log_query(
            "what did I spend",
            project_dir=tmp_path,
            model="gpt-4o",
            base_url=_BASE_URL,
            now=_NOW,
        )


def test_run_openai_log_query_local_no_key_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / "ai-sessions.log").write_text("")

    # Build a mock openai module that returns a plain-text answer directly
    mock_openai = MagicMock()
    mock_openai.OpenAIError = Exception
    mock_openai.BadRequestError = type("BadRequestError", (Exception,), {})

    tool_call = SimpleNamespace(
        function=SimpleNamespace(name="read_sessions", arguments=json.dumps({})),
        id="call_1",
    )
    tool_choice_msg = SimpleNamespace(
        tool_calls=[tool_call],
        content=None,
    )
    final_msg = SimpleNamespace(
        tool_calls=None,
        content="No sessions found.",
    )
    mock_openai.OpenAI.return_value.chat.completions.create.side_effect = [
        SimpleNamespace(choices=[SimpleNamespace(message=tool_choice_msg)]),
        SimpleNamespace(choices=[SimpleNamespace(message=final_msg)]),
    ]

    with patch.dict(sys.modules, {"openai": mock_openai}):
        result = run_openai_log_query(
            "what did I spend",
            project_dir=tmp_path,
            model="llama3.3",
            base_url=_LOCAL_URL,
            now=_NOW,
        )

    assert result.agent == "openai"
    assert result.answer == "No sessions found."


# ---------------------------------------------------------------------------
# Success path — tool dispatch and response normalisation
# ---------------------------------------------------------------------------


def test_run_openai_log_query_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    (tmp_path / "ai-sessions.log").write_text("")

    mock_openai = MagicMock()
    mock_openai.OpenAIError = Exception
    mock_openai.BadRequestError = type("BadRequestError", (Exception,), {})

    tool_call = SimpleNamespace(
        function=SimpleNamespace(name="summarize_by_project", arguments=json.dumps({})),
        id="call_42",
    )
    tool_choice_msg = SimpleNamespace(tool_calls=[tool_call], content=None)
    final_msg = SimpleNamespace(tool_calls=None, content="Total spend: $0.00")

    mock_openai.OpenAI.return_value.chat.completions.create.side_effect = [
        SimpleNamespace(choices=[SimpleNamespace(message=tool_choice_msg)]),
        SimpleNamespace(choices=[SimpleNamespace(message=final_msg)]),
    ]

    with patch.dict(sys.modules, {"openai": mock_openai}):
        result = run_openai_log_query(
            "summarize this month",
            project_dir=tmp_path,
            model="gpt-4o",
            base_url=_BASE_URL,
            now=_NOW,
        )

    assert result.agent == "openai"
    assert result.answer == "Total spend: $0.00"
    # Verify the second call included a tool result message
    calls = mock_openai.OpenAI.return_value.chat.completions.create.call_args_list
    second_messages = calls[1].kwargs["messages"]
    roles = [
        m["role"] if isinstance(m, dict) else getattr(m, "role", None) for m in second_messages
    ]
    assert "tool" in roles


# ---------------------------------------------------------------------------
# Model does not support function calling
# ---------------------------------------------------------------------------


def test_run_openai_log_query_no_tool_support(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    bad_request_cls = type("BadRequestError", (Exception,), {})
    mock_openai = MagicMock()
    mock_openai.OpenAIError = Exception
    mock_openai.BadRequestError = bad_request_cls
    mock_openai.OpenAI.return_value.chat.completions.create.side_effect = bad_request_cls(
        "tool_use not supported"
    )

    with (
        patch.dict(sys.modules, {"openai": mock_openai}),
        pytest.raises(LogAgentError, match="does not support tool use"),
    ):
        run_openai_log_query(
            "what did I spend",
            project_dir=tmp_path,
            model="some-model",
            base_url=_BASE_URL,
            now=_NOW,
        )


# ---------------------------------------------------------------------------
# H-2: _validate_base_url — reject non-HTTPS / non-localhost URLs
# ---------------------------------------------------------------------------


def test_validate_base_url_accepts_https() -> None:
    assert _validate_base_url("https://api.openai.com/v1") == "https://api.openai.com/v1"


def test_validate_base_url_accepts_localhost_http() -> None:
    assert _validate_base_url("http://localhost:11434/v1") == "http://localhost:11434/v1"


def test_validate_base_url_accepts_127_0_0_1() -> None:
    assert _validate_base_url("http://127.0.0.1:8080/v1") == "http://127.0.0.1:8080/v1"


def test_validate_base_url_accepts_ipv6_loopback() -> None:
    # IPv6 loopback must be bracket-enclosed in URLs per RFC 2732
    assert _validate_base_url("http://[::1]:11434/v1") == "http://[::1]:11434/v1"


def test_validate_base_url_rejects_plain_http_remote() -> None:
    with pytest.raises(LogAgentError, match="must be HTTPS or a localhost HTTP URL"):
        _validate_base_url("http://attacker.example.com/v1")


def test_validate_base_url_rejects_file_scheme() -> None:
    with pytest.raises(LogAgentError, match="must be HTTPS or a localhost HTTP URL"):
        _validate_base_url("file:///etc/passwd")


def test_validate_base_url_rejects_data_scheme() -> None:
    with pytest.raises(LogAgentError, match="must be HTTPS or a localhost HTTP URL"):
        _validate_base_url("data:text/plain,malicious")


def test_run_openai_log_query_rejects_malicious_base_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_openai_log_query must reject a non-localhost HTTP base_url before any network call."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    mock_openai = MagicMock()
    with (
        patch.dict(sys.modules, {"openai": mock_openai}),
        pytest.raises(LogAgentError, match="must be HTTPS or a localhost HTTP URL"),
    ):
        run_openai_log_query(
            "what did I spend",
            project_dir=tmp_path,
            model="gpt-4o",
            base_url="http://attacker.example.com/v1",
            now=_NOW,
        )
    # Confirm no network call was made
    mock_openai.OpenAI.assert_not_called()
