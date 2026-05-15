"""v2.46 — the session-evidence predicate.

Integration suppression is covered by
test_cursor_collector.test_handle_stop_hook_skips_evidence_free_fire and
test_gemini_collector.test_handle_agent_stop_skips_evidence_free_fire;
the signal-present (control) path is covered by the existing
token-bearing collector tests. This file pins the predicate itself.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from halyard.ai_log import AiSession
from halyard.collectors import session_has_evidence

_START = datetime(2026, 5, 15, 10, 0, 0)


def _s(**kw: object) -> AiSession:
    base: dict[str, object] = {
        "start": _START,
        "end": _START + timedelta(minutes=1),
        "tool": "cursor",
        "model": "cursor-unknown",
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "tokens_available": False,
    }
    base.update(kw)
    return AiSession(**base)  # type: ignore[arg-type]


def test_wholly_empty_fire_has_no_evidence() -> None:
    assert session_has_evidence(_s()) is False
    assert session_has_evidence(_s(model="")) is False
    assert session_has_evidence(_s(model="gemini-unknown")) is False
    assert session_has_evidence(_s(model="default")) is False


def test_history_flag_is_evidence() -> None:
    assert session_has_evidence(_s(), history=True) is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("input_tokens", 5),
        ("output_tokens", 3),
        ("cache_read", 10),
        ("cache_write", 10),
        ("tool_calls", 1),
        ("tool_errors", 1),
        ("interaction_count", 1),
        ("user_message_count", 1),
        ("assistant_message_count", 1),
        ("prompt_count", 1),
        ("accepted_suggestion_count", 1),
        ("rejected_suggestion_count", 1),
        ("code_added", 1),
        ("code_removed", 1),
        ("files_touched_count", 1),
        ("commit_count", 1),
    ],
)
def test_any_single_signal_is_evidence(field: str, value: int) -> None:
    assert session_has_evidence(_s(**{field: value})) is True


def test_real_model_is_evidence() -> None:
    assert session_has_evidence(_s(model="gemini-2.5-pro")) is True
    assert session_has_evidence(_s(model="claude-sonnet-4-6")) is True
