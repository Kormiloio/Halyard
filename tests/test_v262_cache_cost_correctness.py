"""v2.62 — cache-aware cost correctness.

The v2.62 audit (see openspec/changes/v2.62-cache-cost-correctness/
design.md) found NO live double-count: claude_code/cursor receive
Anthropic-schema input that is natively exclusive of cache, and
gemini_cli/codex_app already subtract the cached subset before
constructing the session. These tests *lock* that invariant via the
shared ``normalise_input`` seam so a future collector/schema change
cannot silently reintroduce the double-count.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from halyard.collectors import normalise_input
from halyard.collectors.codex_app import _parse_session_file
from halyard.collectors.gemini_cli import (
    handle_agent_stop,
    record_model_usage,
    record_session_start,
)
from halyard.model_breakdown import ModelSeg, cost_of, encode
from halyard.pricing import calculate_cost

# Spec scenario numbers (proposal.md / specs scenario):
# 1,022,341 reported input, 838,991 of it cached -> 183,350 fresh.
_GROSS_INPUT = 1_022_341
_CACHED = 838_991
_FRESH = 183_350


# ---------------------------------------------------------------------------
# normalise_input — the single token contract
# ---------------------------------------------------------------------------


def test_normalise_input_subtracts_cache_when_inclusive() -> None:
    assert normalise_input(_GROSS_INPUT, _CACHED, 0, cache_inclusive=True) == _FRESH


def test_normalise_input_also_subtracts_cache_write() -> None:
    # "+ cache_write where applicable" — a gross count that bundled both
    # read and creation must yield fresh-only input.
    assert normalise_input(1000, 300, 200, cache_inclusive=True) == 500


def test_normalise_input_floors_at_zero() -> None:
    # A degenerate payload where cached >= reported input must never
    # produce negative fresh input.
    assert normalise_input(100, 500, 0, cache_inclusive=True) == 0


def test_normalise_input_noop_when_exclusive() -> None:
    # claude_code / cursor: Anthropic schema is already exclusive.
    # The helper must be a provable no-op — byte-identical pre-v2.62.
    for raw, cr, cw in [(0, 0, 0), (183_350, 838_991, 12_000), (42, 0, 7)]:
        assert normalise_input(raw, cr, cw, cache_inclusive=False) == raw


# ---------------------------------------------------------------------------
# Double-count regression (pricing)
# ---------------------------------------------------------------------------


def test_no_double_count_vs_buggy_gross_pricing() -> None:
    """Fresh input billed at 1.0x + cache_read at the cache multiplier
    must be strictly less than the buggy path that bills the *gross*
    input at 1.0x AND the same cached tokens again at 0.10x."""
    model = "gemini-2.5-pro"
    fresh = normalise_input(_GROSS_INPUT, _CACHED, 0, cache_inclusive=True)

    correct = calculate_cost(model, fresh, 1000, cache_read=_CACHED)
    buggy_double = calculate_cost(model, _GROSS_INPUT, 1000, cache_read=_CACHED)

    assert fresh == _FRESH
    assert correct < buggy_double
    # The overcharge is exactly the cached tokens billed a second time
    # at full input rate.
    only_fresh = calculate_cost(model, fresh, 1000)
    cache_term = calculate_cost(model, 0, 0, cache_read=_CACHED)
    assert correct == pytest.approx(only_fresh + cache_term, abs=1e-4)


# ---------------------------------------------------------------------------
# cache_write structurally unavailable for Gemini/Codex (None, not 0)
# ---------------------------------------------------------------------------


def _patch_gemini_stdin(payload: dict) -> patch:  # type: ignore[type-arg]
    return patch(
        "halyard.collectors.gemini_cli.sys.stdin.read",
        return_value=json.dumps(payload),
    )


def _halyard_project(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "halyard.toml").write_text("[project]\nslug = 'test'\n", encoding="utf-8")
    (path / "ai-sessions.log").write_text(
        "; Halyard AI session log\n"
        "; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd>\n",
        encoding="utf-8",
    )
    return path


def _recent_ts(minutes_ago: int = 20) -> str:
    return (datetime.now() - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%S")


def test_gemini_gross_input_normalised_and_cache_write_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _halyard_project(tmp_path / "p")
    state_file = tmp_path / "gc-session"
    monkeypatch.setattr("halyard.collectors.gemini_cli._GC_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.gemini_cli.read_active_project", lambda: None)
    # Force the hook-state fallback path (no history file).
    monkeypatch.setattr("halyard.collectors.gemini_cli.find_session_file", lambda _sid: None)

    start = {
        "session_id": "s1",
        "cwd": str(project),
        "hook_event_name": "SessionStart",
        "timestamp": _recent_ts(),
    }
    with _patch_gemini_stdin(start):
        record_session_start()

    model_payload = {
        "hook_event_name": "AfterModel",
        "llm_request": {"model": "gemini-2.5-pro"},
        "llm_response": {
            "usageMetadata": {
                "promptTokenCount": _GROSS_INPUT,
                "candidatesTokenCount": 1000,
                "cachedContentTokenCount": _CACHED,
                "totalTokenCount": _GROSS_INPUT + 1000,
            }
        },
    }
    with _patch_gemini_stdin(model_payload):
        record_model_usage()

    with _patch_gemini_stdin({"hook_event_name": "AfterAgent", "cwd": str(project)}):
        handle_agent_stop()

    from halyard.ai_log import parse_sessions

    sessions = parse_sessions(project)
    assert len(sessions) == 1
    s = sessions[0]
    assert s.input_tokens == _FRESH  # gross 1,022,341 normalised to fresh
    assert s.cache_read == _CACHED
    # Gemini exposes no cache-creation field — unavailable is NOT zero.
    assert s.cache_write is None


def test_codex_gross_input_normalised_and_cache_write_none(tmp_path: Path) -> None:
    uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    events = [
        {
            "timestamp": "2026-05-06T19:40:47.921Z",
            "type": "session_meta",
            "payload": {
                "id": uuid,
                "timestamp": "2026-05-06T19:40:14.799Z",
                "cwd": "/some/project",
            },
        },
        {
            "timestamp": "2026-05-06T19:40:50.000Z",
            "type": "turn_context",
            "payload": {"cwd": "/some/project", "model": "gpt-4o"},
        },
        {
            "timestamp": "2026-05-06T19:41:02.787Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": _GROSS_INPUT,
                        "cached_input_tokens": _CACHED,
                        "output_tokens": 1000,
                    }
                },
            },
        },
    ]
    path = tmp_path / f"rollout-2026-05-06T19-40-14-{uuid}.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

    result = _parse_session_file(path)
    assert result is not None
    session, _cwd = result
    assert session.input_tokens == _FRESH  # gross normalised to fresh
    assert session.cache_read == _CACHED
    # Codex total_token_usage has no cache-creation field.
    assert session.cache_write is None


# ---------------------------------------------------------------------------
# Composes with v2.61 multi-model attribution
# ---------------------------------------------------------------------------


def test_composes_with_multimodel_each_segment_priced_with_cache() -> None:
    """A usage-form breakdown costs each segment with the corrected
    cache semantics independently (Σ per-model), never the gross."""
    segs = [
        ModelSeg("gemini-2.5-pro", _FRESH, 1000, _CACHED, 0),
        ModelSeg("gemini-2.5-flash", 5000, 800, 2000, 0),
    ]
    token = encode(segs)
    summed = cost_of(token)
    expected = float(
        sum(
            calculate_cost(s.model, s.input_tokens, s.output_tokens, s.cache_read, s.cache_write)
            for s in segs
        )
    )
    assert summed == pytest.approx(expected, abs=1e-9)

    # And the first segment uses fresh input — not the gross 1,022,341.
    gross_variant = calculate_cost("gemini-2.5-pro", _GROSS_INPUT, 1000, _CACHED, 0)
    fresh_variant = calculate_cost("gemini-2.5-pro", _FRESH, 1000, _CACHED, 0)
    assert fresh_variant < gross_variant
