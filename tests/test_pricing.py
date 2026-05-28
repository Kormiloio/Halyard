"""Tests for the model pricing table and cost calculator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import halyard.pricing as pricing_mod
from halyard.pricing import (
    PRICING,
    PricingFetchError,
    calculate_cost,
    load_pricing_table,
    model_is_known,
    pricing_table_age_days,
    update_pricing,
)


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


# ---------------------------------------------------------------------------
# load_pricing_table — merged table tests
# ---------------------------------------------------------------------------


def _reset_cache() -> None:
    pricing_mod._merged_table = None


def test_load_pricing_table_no_local_file(tmp_path: Path) -> None:
    _reset_cache()
    with patch.object(pricing_mod, "_LOCAL_PRICING_FILE", tmp_path / "pricing.toml"):
        table = load_pricing_table()
    assert table == PRICING
    _reset_cache()


def test_load_pricing_table_local_overrides_bundled(tmp_path: Path) -> None:
    _reset_cache()
    local = tmp_path / "pricing.toml"
    local.write_text("[models.claude-sonnet-4-6]\ninput = 1.00\noutput = 5.00\n", encoding="utf-8")
    with patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local):
        table = load_pricing_table()
    assert table["claude-sonnet-4-6"] == (1.00, 5.00)
    # Other bundled models still present
    assert "gpt-4o" in table
    _reset_cache()


def test_load_pricing_table_local_adds_new_model(tmp_path: Path) -> None:
    _reset_cache()
    local = tmp_path / "pricing.toml"
    local.write_text("[models.brand-new-model]\ninput = 0.50\noutput = 2.00\n", encoding="utf-8")
    with patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local):
        table = load_pricing_table()
    assert "brand-new-model" in table
    assert table["brand-new-model"] == (0.50, 2.00)
    _reset_cache()


def test_load_pricing_table_corrupted_local_falls_back(tmp_path: Path) -> None:
    _reset_cache()
    local = tmp_path / "pricing.toml"
    local.write_text("not valid toml ][[[", encoding="utf-8")
    with patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local):
        table = load_pricing_table()
    assert table == PRICING
    _reset_cache()


def test_model_is_known_with_local_file(tmp_path: Path) -> None:
    _reset_cache()
    local = tmp_path / "pricing.toml"
    local.write_text("[models.local-only-model]\ninput = 1.00\noutput = 4.00\n", encoding="utf-8")
    with patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local):
        assert model_is_known("local-only-model") is True
    _reset_cache()


# ---------------------------------------------------------------------------
# pricing_table_age_days
# ---------------------------------------------------------------------------


def test_pricing_table_age_days_absent(tmp_path: Path) -> None:
    with patch.object(pricing_mod, "_LOCAL_PRICING_FILE", tmp_path / "pricing.toml"):
        assert pricing_table_age_days() is None


def test_pricing_table_age_days_fresh(tmp_path: Path) -> None:
    local = tmp_path / "pricing.toml"
    local.write_text("[models]\n", encoding="utf-8")
    with patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local):
        age = pricing_table_age_days()
    assert age is not None
    assert age == 0  # just created


# ---------------------------------------------------------------------------
# update_pricing
# ---------------------------------------------------------------------------

_VALID_TOML = """\
[models.model-a]
input = 1.00
output = 4.00

[models.model-b]
input = 2.00
output = 8.00

[models.model-c]
input = 0.50
output = 2.00
"""


def test_update_pricing_success(tmp_path: Path) -> None:
    _reset_cache()
    local = tmp_path / "pricing.toml"

    mock_resp = MagicMock()
    mock_resp.read.return_value = _VALID_TOML.encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.geturl.return_value = pricing_mod._REMOTE_URL

    with (
        patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local),
        patch("urllib.request.urlopen", return_value=mock_resp),
    ):
        new_count, updated_count = update_pricing()

    assert local.exists()
    assert new_count == 3  # all three are new relative to bundled PRICING
    assert updated_count == 0
    _reset_cache()


def test_update_pricing_network_error(tmp_path: Path) -> None:
    import urllib.error

    local = tmp_path / "pricing.toml"
    with (
        patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local),
        patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")),
        pytest.raises(PricingFetchError, match="could not fetch"),
    ):
        update_pricing()

    assert not local.exists()


def test_update_pricing_validation_too_few_models(tmp_path: Path) -> None:
    local = tmp_path / "pricing.toml"
    toml = "[models.only-one]\ninput = 1.0\noutput = 4.0\n"

    mock_resp = MagicMock()
    mock_resp.read.return_value = toml.encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.geturl.return_value = pricing_mod._REMOTE_URL

    with (
        patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local),
        patch("urllib.request.urlopen", return_value=mock_resp),
        pytest.raises(PricingFetchError, match="only 1 model"),
    ):
        update_pricing()

    assert not local.exists()


def test_update_pricing_validation_non_positive_price(tmp_path: Path) -> None:
    local = tmp_path / "pricing.toml"
    toml = (
        "[models.a]\ninput = -1.0\noutput = 4.0\n"
        "[models.b]\ninput = 1.0\noutput = 4.0\n"
        "[models.c]\ninput = 1.0\noutput = 4.0\n"
    )

    mock_resp = MagicMock()
    mock_resp.read.return_value = toml.encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.geturl.return_value = pricing_mod._REMOTE_URL

    with (
        patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local),
        patch("urllib.request.urlopen", return_value=mock_resp),
        pytest.raises(PricingFetchError),
    ):
        update_pricing()

    assert not local.exists()


def test_update_pricing_missing_models_table(tmp_path: Path) -> None:
    local = tmp_path / "pricing.toml"
    toml = "some_key = 'value'\n"

    mock_resp = MagicMock()
    mock_resp.read.return_value = toml.encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.geturl.return_value = pricing_mod._REMOTE_URL

    with (
        patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local),
        patch("urllib.request.urlopen", return_value=mock_resp),
        pytest.raises(PricingFetchError, match="missing \\[models\\]"),
    ):
        update_pricing()


def test_update_pricing_atomic_replaces_existing(tmp_path: Path) -> None:
    _reset_cache()
    local = tmp_path / "pricing.toml"
    local.write_text("[models.old-model]\ninput = 9.0\noutput = 36.0\n", encoding="utf-8")
    original_content = local.read_text(encoding="utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = _VALID_TOML.encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.geturl.return_value = pricing_mod._REMOTE_URL

    with (
        patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local),
        patch("urllib.request.urlopen", return_value=mock_resp),
    ):
        update_pricing()

    assert local.read_text(encoding="utf-8") == _VALID_TOML
    assert local.read_text(encoding="utf-8") != original_content
    _reset_cache()


# ---------------------------------------------------------------------------
# v2.38 — Review hardening regressions
# ---------------------------------------------------------------------------


def test_cost_is_decimal_deterministic() -> None:
    """Same inputs → identical cost regardless of accumulation order."""
    _reset_cache()
    a = calculate_cost("gemini-3-flash", input_tokens=333_333, output_tokens=777_777)
    b = calculate_cost("gemini-3-flash", input_tokens=333_333, output_tokens=777_777)
    assert a == b
    # Quantized to exactly 4 decimal places, ROUND_HALF_UP.
    assert a == round(a, 4)
    _reset_cache()


def test_local_pricing_oserror_warns(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _reset_cache()
    local = tmp_path / "pricing.toml"
    local.write_text("[models.x]\ninput=1\noutput=2\n", encoding="utf-8")
    with (
        patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local),
        patch.object(pricing_mod.Path, "read_text", side_effect=OSError("boom")),
    ):
        table = load_pricing_table()
    assert table == PRICING
    assert "using bundled prices" in capsys.readouterr().err
    _reset_cache()


def test_local_multiplier_ceiling_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _reset_cache()
    local = tmp_path / "pricing.toml"
    local.write_text(
        "[models.claude-sonnet-4-6]\ninput=3.0\noutput=15.0\ncache_write_multiplier = 100000\n",
        encoding="utf-8",
    )
    with patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local):
        cost = calculate_cost("claude-sonnet-4-6", 0, 0, cache_write=1_000_000)
    # Falls back to default 1.25 multiplier → $3.75, not an inflated number.
    assert cost == pytest.approx(3.75, abs=1e-4)
    assert "invalid multiplier" in capsys.readouterr().err
    _reset_cache()


def test_update_pricing_rejects_oversized_multiplier(tmp_path: Path) -> None:
    _reset_cache()
    bad = (
        "[models.a]\ninput=1\noutput=2\n[models.b]\ninput=1\noutput=2\n"
        "[models.c]\ninput=1\noutput=2\ncache_read_multiplier = 999\n"
    )
    mock_resp = MagicMock()
    mock_resp.read.return_value = bad.encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.geturl.return_value = pricing_mod._REMOTE_URL
    with (
        patch.object(pricing_mod, "_LOCAL_PRICING_FILE", tmp_path / "p.toml"),
        patch("urllib.request.urlopen", return_value=mock_resp),
        pytest.raises(PricingFetchError, match="invalid cache_read_multiplier"),
    ):
        update_pricing()
    _reset_cache()
