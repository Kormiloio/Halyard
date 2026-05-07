"""Model pricing table and cost calculator.

Prices are USD per million tokens, snapshotted 2026-05.
Run `halyard update-pricing` (v2) to refresh from the live table.
"""

from __future__ import annotations

# (input_per_mtok, output_per_mtok)
PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-4-7": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-haiku-4-5": (0.80, 4.00),
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "o3": (10.00, 40.00),
    "o4-mini": (1.10, 4.40),
    # Google Gemini
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-3-pro": (1.25, 5.00),
    "gemini-3-flash": (0.075, 0.30),
    # DeepSeek
    "deepseek-v3": (0.27, 1.10),
    "deepseek-r1": (0.55, 2.19),
    # xAI Grok
    "grok-3": (3.00, 15.00),
    "grok-3-mini": (0.30, 0.50),
    # Mistral
    "mistral-large-latest": (2.00, 6.00),
    "mistral-small-latest": (0.10, 0.30),
}

# Anthropic prompt cache pricing multipliers (relative to input rate)
_CACHE_READ_MULTIPLIER = 0.10  # cache reads = 10% of input price
_CACHE_WRITE_MULTIPLIER = 1.25  # cache writes = 125% of input price


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_write: int = 0,
) -> float:
    """Return cost in USD. Returns 0.0 for unknown models."""
    if model not in PRICING:
        return 0.0
    input_rate, output_rate = PRICING[model]
    cost = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
    if cache_read:
        cost += (cache_read * input_rate * _CACHE_READ_MULTIPLIER) / 1_000_000
    if cache_write:
        cost += (cache_write * input_rate * _CACHE_WRITE_MULTIPLIER) / 1_000_000
    return round(cost, 4)


def model_is_known(model: str) -> bool:
    return model in PRICING
