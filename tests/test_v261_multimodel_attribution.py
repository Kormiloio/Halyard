"""v2.61 — multi-model session attribution (cost correctness)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session, parse_sessions
from halyard.model_breakdown import (
    ModelSeg,
    cost_of,
    encode,
    iter_model_usage,
    parse,
    primary_model,
)
from halyard.pricing import calculate_cost

_NOW = datetime.now()


def _proj(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (p / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")
    return p


def _s(model: str, *, breakdown: str | None = None, cost: float = 1.0) -> AiSession:
    return AiSession(
        start=_NOW - timedelta(minutes=5),
        end=_NOW,
        tool="claude-code",
        model=model,
        input_tokens=100,
        output_tokens=50,
        cost_usd=cost,
        project="kormilo:halyard",
        model_breakdown=breakdown,
        tokens_available=True,
    )


# --- encoding -------------------------------------------------------------


def test_encode_parse_round_trip() -> None:
    segs = [
        ModelSeg("claude-opus-4-7", 1000, 200, 5000, 0),
        ModelSeg("claude-haiku-4-5", 30, 8, 0, 0),
    ]
    token = encode(segs)
    assert parse(token) == segs


def test_legacy_count_form_is_not_usage() -> None:
    # Pre-v2.61 'model:3|other:1' must NOT be read as usage → None,
    # so callers fall back to the safe single-model path.
    assert parse("claude-opus-4-7:3|claude-haiku-4-5:1") is None


def test_truncated_segment_bails_safely() -> None:
    assert parse("claude-opus-4-7:1000/200/5000/0|claude-hai") is None
    assert parse("") is None
    assert parse(None) is None


# --- cost = Σ per model ---------------------------------------------------


def test_cost_of_sums_per_model() -> None:
    token = encode(
        [
            ModelSeg("claude-opus-4-7", 1000, 200, 0, 0),
            ModelSeg("claude-haiku-4-5", 4000, 900, 0, 0),
        ]
    )
    expected = calculate_cost("claude-opus-4-7", 1000, 200, 0, 0) + calculate_cost(
        "claude-haiku-4-5", 4000, 900, 0, 0
    )
    assert cost_of(token) == pytest.approx(expected)


def test_cost_of_none_for_non_usage() -> None:
    assert cost_of("claude:3|haiku:1") is None
    assert cost_of(None) is None


# --- iter_model_usage -----------------------------------------------------


def test_iter_single_model_is_passthrough() -> None:
    s = _s("claude-opus-4-7", cost=3.14)
    rows = iter_model_usage(s)
    assert rows == [("claude-opus-4-7", 100, 50, 0, 0, 3.14)]


def test_iter_multi_model_splits() -> None:
    token = encode(
        [
            ModelSeg("claude-opus-4-7", 1000, 200, 0, 0),
            ModelSeg("claude-haiku-4-5", 40, 9, 0, 0),
        ]
    )
    s = _s("claude-opus-4-7", breakdown=token)
    rows = {r[0]: r for r in iter_model_usage(s)}
    assert set(rows) == {"claude-opus-4-7", "claude-haiku-4-5"}
    assert rows["claude-opus-4-7"][1:5] == (1000, 200, 0, 0)


def test_primary_model_is_costliest() -> None:
    segs = [
        ModelSeg("claude-haiku-4-5", 10, 2, 0, 0),
        ModelSeg("claude-opus-4-7", 5000, 1200, 0, 0),
    ]
    assert primary_model(segs) == "claude-opus-4-7"


# --- rollup attribution ---------------------------------------------------


def test_usage_model_buckets_attribute_per_model(tmp_path: Path) -> None:
    from halyard.usage import build_usage_analytics

    token = encode(
        [
            ModelSeg("claude-opus-4-7", 1000, 200, 0, 0),
            ModelSeg("claude-haiku-4-5", 40, 9, 0, 0),
        ]
    )
    s = _s("claude-opus-4-7", breakdown=token, cost=(cost_of(token) or 0.0))
    ua = build_usage_analytics([s], range_key="all", now=_NOW)
    models = {b.model for b in ua.by_model}
    assert models == {"claude-opus-4-7", "claude-haiku-4-5"}  # not one row


def test_single_model_bucket_unchanged(tmp_path: Path) -> None:
    from halyard.usage import build_usage_analytics

    s = _s("claude-opus-4-7", cost=2.0)
    ua = build_usage_analytics([s], range_key="all", now=_NOW)
    assert [b.model for b in ua.by_model] == ["claude-opus-4-7"]
    assert ua.by_model[0].cost_usd == pytest.approx(2.0)


def test_mcp_cost_by_model_splits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from halyard import mcp_server

    proj = _proj(tmp_path / "p")
    token = encode(
        [
            ModelSeg("claude-opus-4-7", 1000, 200, 0, 0),
            ModelSeg("claude-haiku-4-5", 40, 9, 0, 0),
        ]
    )
    append_session(proj, _s("claude-opus-4-7", breakdown=token, cost=(cost_of(token) or 0.0)))
    monkeypatch.setattr(mcp_server, "aggregate_session_dirs", lambda: [proj])
    rows = {r["model"] for r in mcp_server._cost_by_model("all")}
    assert rows == {"claude-opus-4-7", "claude-haiku-4-5"}


# --- log round-trip incl. long (no 128-char truncation) -------------------


def test_long_breakdown_round_trips(tmp_path: Path) -> None:
    proj = _proj(tmp_path / "p")
    token = encode(
        [
            ModelSeg("gemini-3-flash-preview", 1004686, 11254, 822925, 0),
            ModelSeg("gemini-3.1-pro-preview", 228932, 3375, 116420, 0),
            ModelSeg("gemini-3.1-flash-lite", 18550, 154, 0, 0),
            ModelSeg("gemini-3.1-flash-thinking", 44210, 9981, 12000, 0),
        ]
    )
    assert len(token) > 128  # the old _safe_field 128-cap would truncate
    s = _s("gemini-3-flash-preview", breakdown=token, cost=(cost_of(token) or 0.0))
    append_session(proj, s)
    got = parse_sessions(proj)[0]
    assert got.model_breakdown == token
    assert parse(got.model_breakdown) is not None  # survived intact
