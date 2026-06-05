"""v5.16 — untrusted-input hardening regression tests.

Each test maps to a launch blocker from
``docs/reviews/2026-06-pre-release-audit.md``.
"""

from __future__ import annotations

from datetime import datetime

from halyard.ai_log import AiSession, _parse_line
from halyard.usage import sum_spend

_START = "2026-05-15T09:00:00"
_END = "2026-05-15T10:00:00"


def _line(cost: str, *, extra: str = "") -> str:
    base = f"s {_START} {_END} claude-code claude-sonnet-4-6 100 50 {cost}"
    return f"{base} {extra}".strip()


# ---------------------------------------------------------------------------
# B1 — non-finite cost/credits floats
# ---------------------------------------------------------------------------


def test_b1_inf_cost_line_rejected() -> None:
    # inf would raise decimal.InvalidOperation downstream in sum_spend.
    assert _parse_line(_line("inf")) is None
    assert _parse_line(_line("Infinity")) is None
    # 1e400 overflows float() to +inf.
    assert _parse_line(_line("1e400")) is None


def test_b1_nan_cost_line_rejected() -> None:
    # nan silently poisons every total to NaN (worse than a crash).
    assert _parse_line(_line("nan")) is None
    assert _parse_line(_line("NaN")) is None


def test_b1_negative_cost_still_rejected() -> None:
    # Pre-existing guard must remain.
    assert _parse_line(_line("-1.0")) is None


def test_b1_finite_cost_still_parses() -> None:
    # Don't over-restrict: a normal finite cost must still parse.
    s = _parse_line(_line("0.1234"))
    assert s is not None
    assert s.cost_usd == 0.1234


def test_b1_non_finite_credits_field_skipped() -> None:
    # A non-finite FLOAT_4 field (credits) is skipped, not admitted; the
    # session itself (finite cost) still parses.
    s = _parse_line(_line("0.5", extra="credits=inf"))
    assert s is not None
    assert s.credits is None  # skipped, left at default
    # A finite credits value still works.
    s2 = _parse_line(_line("0.5", extra="credits=2.5"))
    assert s2 is not None
    assert s2.credits == 2.5


def _sess(cost: float) -> AiSession:
    return AiSession(
        start=datetime(2026, 5, 15, 9, 0),
        end=datetime(2026, 5, 15, 10, 0),
        tool="claude-code",
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=50,
        cost_usd=cost,
    )


def test_b1_sum_spend_backstop_skips_non_finite() -> None:
    # Defense-in-depth: a non-finite cost arriving via the cache or direct
    # construction (bypassing the parser) must not crash or poison the total.
    inf_total = sum_spend([_sess(float("inf")), _sess(5.0)])
    assert inf_total == 5.0  # inf skipped, finite counted

    nan_total = sum_spend([_sess(float("nan")), _sess(5.0)])
    assert nan_total == 5.0  # nan skipped, not propagated

    # All non-finite -> 0.0, no exception.
    assert sum_spend([_sess(float("inf")), _sess(float("nan"))]) == 0.0


# ---------------------------------------------------------------------------
# B19 — Rich markup injection via mcp_server_names
# ---------------------------------------------------------------------------


def _mcp_sess(names: str, count: int) -> AiSession:
    s = _sess(0.5)
    s.mcp_servers_used = count
    s.mcp_server_names = names
    return s


def test_b19_non_allowlisted_names_filtered_out() -> None:
    from halyard.leverage import summarize_mcp

    # A hand-edited log smuggles a Rich-markup payload as a "server name".
    now = datetime(2026, 5, 15, 12, 0)
    roll = summarize_mcp([_mcp_sess("x[/notopened]", 2)], now)
    assert roll is not None
    # The malicious name is not on the allowlist -> never reaches `named`.
    assert roll.named == ()
    assert all("[" not in n for n in roll.named)


def test_b19_render_phrase_has_no_unescaped_markup() -> None:
    from rich.markup import escape

    from halyard.leverage import render_mcp_phrase, summarize_mcp

    now = datetime(2026, 5, 15, 12, 0)
    roll = summarize_mcp([_mcp_sess("x[/notopened],github", 2)], now)
    assert roll is not None
    phrase = render_mcp_phrase(roll)
    # The TUI escapes this before Text.from_markup; escaping must round-trip
    # without raising and must neutralize any stray bracket.
    escaped = escape(phrase)
    from rich.text import Text

    Text.from_markup(escaped)  # must not raise MarkupError

    # An allowlisted name still renders.
    roll2 = summarize_mcp([_mcp_sess("github", 1)], now)
    assert roll2 is not None
    assert "github" in render_mcp_phrase(roll2)
