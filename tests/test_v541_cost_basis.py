"""v5.41 — every cost Halyard had ever reported was $0.00.

Two independent causes, both turning *unpriced* into *free*: the bundled
rate table predated every model in use (and `calculate_cost` returns 0.0
for an unknown model), and most collectors hardcoded `cost_usd=0.0`
regardless. 437 real sessions carried a zero cost; four dashboard panels
reported it as a measurement.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from halyard.ai_log import AiSession, resolve_costs
from halyard.collectors import model_is_local
from halyard.pricing import _coerce_multiplier, calculate_cost, cost_is_known


def _session(**kw) -> AiSession:
    base = {
        "start": datetime(2026, 9, 1, 9),
        "end": datetime(2026, 9, 1, 10),
        "tool": "codex",
        "model": "gpt-5.6-sol",
        "input_tokens": 1_000_000,
        "output_tokens": 100_000,
        "cost_usd": 0.0,
    }
    base.update(kw)
    return AiSession(**base)  # type: ignore[arg-type]


# --- the rates themselves ---------------------------------------------


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        # 1M input + 100k output, hand-computed from the vendor tables.
        ("claude-opus-5", 5.00 + 2.50),  # $5/MTok in, $25/MTok out
        ("claude-sonnet-5", 2.00 + 1.00),  # $2 / $10
        ("gpt-5.6-sol", 4.00 + 2.00),  # $4 / $20
        ("gpt-5.6-terra", 2.00 + 1.20),  # $2 / $12
        ("gemini-3.6-flash", 0.75 + 0.375),  # $0.75 / $3.75
    ],
)
def test_current_models_are_priced(model: str, expected: float) -> None:
    assert calculate_cost(model, 1_000_000, 100_000) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        # Both entries carried the *previous* generation's rate. A wrong
        # price is worse than a missing one: it looks authoritative.
        ("claude-opus-4-7", 5.00 + 2.50),  # was $15/$75 (Opus 4.1's rate)
        ("claude-haiku-4-5", 1.00 + 0.50),  # was $0.80/$4.00 (Haiku 3.5's)
        ("claude-haiku-4-5-20251001", 1.00 + 0.50),
    ],
)
def test_corrected_entries_use_the_current_rate(model: str, expected: float) -> None:
    assert calculate_cost(model, 1_000_000, 100_000) == pytest.approx(expected)


def test_cache_reads_are_billed_at_a_tenth_of_input() -> None:
    """The dominant term in this user's bill: 12.7B cache-read tokens."""
    assert calculate_cost("gpt-5.6-sol", 0, 0, cache_read=1_000_000) == pytest.approx(0.40)


# --- the multiplier floor ---------------------------------------------


def test_a_zero_multiplier_is_accepted() -> None:
    """OpenAI charges nothing for cache writes.

    The old `0 < val` bound made "free" inexpressible: it fell back to the
    1.25x default and invented a charge.
    """
    assert _coerce_multiplier(0, 1.25, "gpt-5.6-sol") == 0.0


def test_a_negative_multiplier_is_still_rejected() -> None:
    assert _coerce_multiplier(-1, 1.25, "m") == 1.25


# --- local models -----------------------------------------------------


@pytest.mark.parametrize(
    "model", ["Qwen3.6-27B-MLX-4bit", "muse-glimmer:30b-mlx", "foo-gguf", "local/thing"]
)
def test_local_models_are_recognised(model: str) -> None:
    assert model_is_local(model) is True


@pytest.mark.parametrize("model", ["gpt-5.6-sol", "claude-opus-5", "", None])
def test_hosted_models_are_not_local(model: str | None) -> None:
    assert model_is_local(model) is False


def test_a_local_row_is_known_free_not_unpriced() -> None:
    """Its zero is a measurement, so it must not render as n/a.

    Checked on the model *name*, not only stored `billing`: rows written
    before v5.41 taught the collectors to classify local models still say
    "api", and re-importing a finished session is not always possible.
    """
    assert cost_is_known("muse-glimmer:30b-mlx", "api") is True


def test_an_unpriced_hosted_model_is_not_known() -> None:
    assert cost_is_known("gpt-oss-120b-medium", "api") is False


# --- read-time repricing ----------------------------------------------


def test_a_zero_cost_row_on_a_known_model_is_priced() -> None:
    """The fix that reaches the 437 rows already on disk."""
    out = resolve_costs([_session()])
    assert out[0].cost_usd == pytest.approx(6.00)  # $4 in + $2 out


def test_a_measured_cost_is_never_overwritten() -> None:
    """Junie and Claude Code report a vendor-computed figure.

    That is stronger evidence than a table lookup now, so it wins.
    """
    rows = [_session(cost_usd=1.23)]
    assert resolve_costs(rows)[0].cost_usd == pytest.approx(1.23)


def test_a_local_row_stays_at_zero() -> None:
    """Pricing without the local carve-out would start charging API rates
    for compute that ran on the user's own laptop."""
    out = resolve_costs([_session(model="Qwen3.6-27B-MLX-4bit", billing="local")])
    assert out[0].cost_usd == 0.0


def test_a_local_row_recorded_as_api_also_stays_at_zero() -> None:
    """The two observed muse-glimmer sessions predate the classifier."""
    out = resolve_costs([_session(model="muse-glimmer:30b-mlx", billing="api")])
    assert out[0].cost_usd == 0.0


def test_an_unpriced_model_stays_at_zero() -> None:
    out = resolve_costs([_session(model="gpt-oss-120b-medium")])
    assert out[0].cost_usd == 0.0
    assert cost_is_known("gpt-oss-120b-medium", "api") is False


def test_rows_needing_nothing_are_returned_unchanged() -> None:
    rows = [_session(cost_usd=5.0)]
    assert resolve_costs(rows)[0] is rows[0], "no copy when nothing changes"


def test_cache_tokens_reach_the_price() -> None:
    out = resolve_costs([_session(input_tokens=0, output_tokens=0, cache_read=1_000_000)])
    assert out[0].cost_usd == pytest.approx(0.40)


# --- the shipped table ------------------------------------------------


def test_the_shipped_table_parses_to_flat_model_keys() -> None:
    """`update-pricing` fetches this file, so a key typo ships silently.

    Model names contain dots (`gpt-5.6-sol`). An unquoted TOML key would
    parse as nested tables — `models.gpt-5` → `6-sol` — leaving the model
    unpriced with no error anywhere. Caught exactly that way in v5.41.
    """
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "pricing" / "models.toml"
    models = tomllib.loads(root.read_text(encoding="utf-8"))["models"]

    for name, entry in models.items():
        assert isinstance(entry, dict), f"{name} parsed as a nested table"
        assert "input" in entry and "output" in entry, f"{name} lacks a rate"

    for expected in ("gpt-5.6-sol", "gpt-5.6-terra", "gemini-3.6-flash", "claude-opus-5"):
        assert expected in models, f"{expected} missing from the shipped table"


def test_the_shipped_table_agrees_with_the_bundled_one() -> None:
    """The bundled dict is the offline fallback; a drift between them means
    a user's cost changes depending on whether update-pricing has run."""
    import tomllib
    from pathlib import Path

    from halyard.pricing import PRICING

    root = Path(__file__).resolve().parents[1] / "pricing" / "models.toml"
    models = tomllib.loads(root.read_text(encoding="utf-8"))["models"]

    for name, entry in models.items():
        if name in PRICING:
            assert PRICING[name] == (entry["input"], entry["output"]), f"{name} rates disagree"
