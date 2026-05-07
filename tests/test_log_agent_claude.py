from unittest.mock import MagicMock, patch
from datetime import datetime
from pathlib import Path
import pytest

from halyard.log_agent import run_claude_log_query, LogBucket, LogAgentError

@pytest.fixture
def mock_anthropic(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    with patch("anthropic.Anthropic", return_value=mock_client):
        yield mock_client

def test_run_claude_log_query_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LogAgentError, match="Missing ANTHROPIC_API_KEY"):
        run_claude_log_query("test", project_dir=Path("."), model="claude-test")

def test_run_claude_log_query_success(mock_anthropic, tmp_path):
    # Setup project dir
    (tmp_path / "ai-sessions.log").write_text("; header\n")
    (tmp_path / "time.timeclock").write_text("; clock\n")
    
    # Mock responses
    # Turn 1: Claude asks for a summary
    mock_tool_use = MagicMock()
    mock_tool_use.type = "tool_use"
    mock_tool_use.id = "call_123"
    mock_tool_use.name = "summarize_by_model"
    mock_tool_use.input = {"start_date": "2026-05-01"}
    
    response_1 = MagicMock()
    response_1.stop_reason = "tool_use"
    response_1.content = [mock_tool_use]
    
    # Turn 2: Claude gives final answer
    mock_text = MagicMock()
    mock_text.text = "You spent $10 on Claude."
    
    response_2 = MagicMock()
    response_2.stop_reason = "end_turn"
    response_2.content = [mock_text]
    
    mock_anthropic.messages.create.side_effect = [response_1, response_2]
    
    res = run_claude_log_query(
        "How much Claude?", 
        project_dir=tmp_path, 
        model="claude-test",
        now=datetime(2026, 5, 7)
    )
    
    assert res.answer == "You spent $10 on Claude."
    assert res.agent == "claude"
    assert res.cost_usd_total == 0.0 # because the log was empty in this test mock
    assert mock_anthropic.messages.create.call_count == 2
