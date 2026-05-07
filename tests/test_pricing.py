"""Tests for the model pricing table and cost calculator."""

from __future__ import annotations

import pytest

from halyard.pricing import PRICING, calculate_cost, model_is_known


def test_unknown_model_returns_zero() -> None:
    assert calculate_cost("not-a-real-model", 1_000_000, 1_000_000) == 0.0


def test_model_is_known_true_and_false() -> None:
    assert model_is_known("claude-sonnet-4-6") is True
    assert model_is_known("made-up-model") is False


def test_sonnet_input_cost() -> None:
    # 1M input tokens at $3.00/MTok = $3.00
    cost = calculate_cost("claude-sonnet-4-6", input_tokens=1_000_000, output_tokens=0)
    assert cost == pytest.approx(3.0, abs=1e-4)


def test_sonnet_output_cost() -> None:
    # 1M output tokens at $15.00/MTok = $15.00
    cost = calculate_cost("claude-sonnet-4-6", input_tokens=0, output_tokens=1_000_000)
    assert cost == pytest.approx(15.0, abs=1e-4)


def test_haiku_mixed_cost() -> None:
    # 1M input @ $0.80 + 1M output @ $4.00 = $4.80
    cost = calculate_cost("claude-haiku-4-5", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == pytest.approx(4.80, abs=1e-4)


def test_cache_read_tokens_at_ten_percent_of_input_rate() -> None:
    # sonnet input rate $3.00/MTok; cache read = 10% = $0.30/MTok
    # 1M cache_read tokens → $0.30
    cost = calculate_cost(
        "claude-sonnet-4-6", input_tokens=0, output_tokens=0, cache_read=1_000_000
    )
    assert cost == pytest.approx(0.30, abs=1e-4)


def test_cache_write_tokens_at_125_percent_of_input_rate() -> None:
    # sonnet input rate $3.00/MTok; cache write = 125% = $3.75/MTok
    # 1M cache_write tokens → $3.75
    cost = calculate_cost(
        "claude-sonnet-4-6", input_tokens=0, output_tokens=0, cache_write=1_000_000
    )
    assert cost == pytest.approx(3.75, abs=1e-4)


def test_cache_combined_with_regular_tokens() -> None:
    # 100k input @ $3.00/MTok = $0.30
    # 50k output @ $15.00/MTok = $0.75
    # 200k cache_read @ $0.30/MTok = $0.06
    # total = $1.11
    cost = calculate_cost(
        "claude-sonnet-4-6",
        input_tokens=100_000,
        output_tokens=50_000,
        cache_read=200_000,
    )
    assert cost == pytest.approx(1.11, abs=1e-4)


def test_zero_tokens_returns_zero() -> None:
    assert calculate_cost("gpt-4o", input_tokens=0, output_tokens=0) == 0.0


def test_all_models_have_positive_rates() -> None:
    for model, (input_rate, output_rate) in PRICING.items():
        assert input_rate > 0, f"{model} has non-positive input rate"
        assert output_rate > 0, f"{model} has non-positive output rate"


def test_result_is_rounded_to_four_decimal_places() -> None:
    # 1 token of sonnet input = 3.00 / 1_000_000 = 0.000003 → rounds to 0.0
    cost = calculate_cost("claude-sonnet-4-6", input_tokens=1, output_tokens=0)
    # Result should be a float with at most 4 decimal places
    assert cost == round(cost, 4)
