"""Tests for the local (provider-neutral) log agent inference layer."""

from __future__ import annotations

from halyard.log_agent import _infer_branch, _infer_filters, _infer_period, _infer_tool

# ---------------------------------------------------------------------------
# Period inference
# ---------------------------------------------------------------------------


def test_infer_period_today() -> None:
    assert _infer_period("what did I spend today") == "today"


def test_infer_period_week() -> None:
    assert _infer_period("show me this week's sessions") == "week"


def test_infer_period_month() -> None:
    assert _infer_period("summarize this month") == "month"


def test_infer_period_all_time() -> None:
    assert _infer_period("all time spend") == "all"


def test_infer_period_none_for_unrecognised() -> None:
    assert _infer_period("how much did auth-migration cost") is None


# ---------------------------------------------------------------------------
# Branch inference — correct matches
# ---------------------------------------------------------------------------


def test_infer_branch_explicit_branch_keyword() -> None:
    assert _infer_branch("cost on branch main") == "main"


def test_infer_branch_bare_branch_keyword() -> None:
    assert _infer_branch("branch auth-migration sessions") == "auth-migration"


def test_infer_branch_quoted_branch_name() -> None:
    result = _infer_branch('cost on branch "feature/login"')
    assert result == "feature/login"


# ---------------------------------------------------------------------------
# Branch inference — false-positive regression cases
# ---------------------------------------------------------------------------


def test_infer_branch_no_false_positive_on_tool_name() -> None:
    # "on cursor" should NOT infer branch="cursor"
    assert _infer_branch("what did I spend on cursor") is None


def test_infer_branch_no_false_positive_on_preposition() -> None:
    # "working on the project" should NOT infer branch="the"
    assert _infer_branch("working on the auth project") is None


def test_infer_branch_no_false_positive_on_model() -> None:
    # "cost on models" should NOT infer branch="models"
    assert _infer_branch("cost on models this week") is None


def test_infer_branch_no_false_positive_on_project() -> None:
    # "spend on acme:auth" should NOT infer a branch
    assert _infer_branch("what did I spend on acme:auth") is None


# ---------------------------------------------------------------------------
# Tool inference
# ---------------------------------------------------------------------------


def test_infer_tool_cursor() -> None:
    assert _infer_tool("show me cursor sessions") == "cursor"


def test_infer_tool_claude_code() -> None:
    assert _infer_tool("claude code sessions this month") == "claude-code"


def test_infer_tool_gemini() -> None:
    assert _infer_tool("gemini spend today") == "gemini-cli"


def test_infer_tool_none_for_generic_query() -> None:
    assert _infer_tool("what did I spend this month") is None


# ---------------------------------------------------------------------------
# Combined filter inference
# ---------------------------------------------------------------------------


def test_infer_filters_branch_and_tool_combined() -> None:
    filters = _infer_filters("cursor sessions on branch main")
    assert filters.tool == "cursor"
    assert filters.branch == "main"


def test_infer_filters_branch_and_tool_independent() -> None:
    # Branch name that doesn't overlap with any tool alias
    filters = _infer_filters("cost on branch auth-migration")
    assert filters.branch == "auth-migration"
    assert filters.tool is None
