"""v5.43 — inventory panels showed one calendar month and called it everything.

The user asked three times why a project was missing from the dashboard.
Attribution was correct the whole time: the session was recorded 2026-08-27
and the report is scoped to the current calendar month, so on 2026-09-06 it
was filtered out. A month is the right window for money and the wrong one
for "which projects exist".

Also: the Models table's Share was a fraction of *cost*, which read 0% for
every row while costs were broken and still drops local and unpriced models
out of the comparison.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from halyard.ai_log import AiSession
from halyard.dashboard import _model_table
from halyard.reports import CostBucket, build_ai_report

NOW = datetime(2026, 9, 6, 12)


def _session(*, month: int, day: int, project: str, model: str = "gpt-5.6-sol") -> AiSession:
    return AiSession(
        start=datetime(2026, month, day, 9),
        end=datetime(2026, month, day, 10),
        tool="codex",
        model=model,
        input_tokens=1000,
        output_tokens=100,
        cost_usd=0.0,
        project=project,
    )


# --- the window -------------------------------------------------------


def test_the_month_report_drops_last_months_work() -> None:
    """The behaviour that hid the project — asserted so it is not a surprise."""
    sessions = [
        _session(month=8, day=27, project="kormilo:mycelium"),
        _session(month=9, day=5, project="git/Nautilus"),
    ]
    month = build_ai_report(Path("."), sessions=sessions, now=NOW)

    slugs = {b.label for b in month.by_project}
    assert "git/Nautilus" in slugs
    assert "kormilo:mycelium" not in slugs, "August work is outside the month window"


def test_the_inventory_report_keeps_it() -> None:
    """`all_time=True` is what the roster and Mix panels now read."""
    sessions = [
        _session(month=8, day=27, project="kormilo:mycelium"),
        _session(month=9, day=5, project="git/Nautilus"),
    ]
    inv = build_ai_report(Path("."), all_time=True, sessions=sessions, now=NOW)

    slugs = {b.label for b in inv.by_project}
    assert {"git/Nautilus", "kormilo:mycelium"} <= slugs


def test_a_month_boundary_does_not_empty_the_inventory() -> None:
    """On the 1st, the month report is nearly empty; inventory is not."""
    sessions = [_session(month=8, day=15, project="a:b") for _ in range(5)]
    first_of_month = datetime(2026, 9, 1, 0, 30)
    path = Path(".")

    assert build_ai_report(path, sessions=sessions, now=first_of_month).by_project == []
    assert build_ai_report(path, all_time=True, sessions=sessions, now=first_of_month).by_project


# --- the share metric -------------------------------------------------


def _bucket(label: str, tokens: int, **kw) -> CostBucket:
    return CostBucket(
        label=label, cost_usd=kw.pop("cost", 0.0), sessions=1, work_tokens=tokens, **kw
    )


def test_share_is_token_share_not_cost_share() -> None:
    """Two models, equal cost, very different work: share must split by work."""
    html = _model_table([_bucket("big", 900, cost=1.0), _bucket("small", 100, cost=1.0)])

    assert ">90%<" in html or "90%" in html
    assert "10%" in html


def test_an_unpriced_model_still_gets_a_share() -> None:
    """Cost share dropped these out of the comparison entirely."""
    html = _model_table([_bucket("free", 500, priced=False), _bucket("paid", 500, cost=9.0)])

    assert html.count("<span>50%</span>") == 2, "both rows share equally by work"
    assert "n/a" in html, "cost is still unknown for the unpriced one"


def test_a_zero_token_model_is_zero_percent_not_na() -> None:
    """Antigravity reports no tokens. Zero work is a fact, not a gap —
    unlike an unknown *cost*, which is what n/a is reserved for."""
    html = _model_table([_bucket("antigravity", 0, priced=False), _bucket("real", 100, cost=1.0)])

    assert "0%" in html


# --- the cost cell has four states ------------------------------------


def test_a_priced_api_model_shows_dollars() -> None:
    assert "$7.50" in _model_table([_bucket("m", 100, cost=7.5)])


def test_an_unpriced_model_shows_na() -> None:
    assert "n/a" in _model_table([_bucket("m", 100, priced=False)])


def test_a_credits_model_says_credits_not_zero() -> None:
    """`sum_spend` counts only billing == "api", so a Codex bucket sums to
    0.00. Printed beside 17.4M tokens that reads as free."""
    html = _model_table([_bucket("gpt-5.6-sol", 17_400_000, api_billed=False)])

    assert "credits" in html
    assert "$0.00" not in html


def test_a_local_model_shows_a_real_zero() -> None:
    """A local zero is a measurement (v5.41), not a subscription. Labelling
    an MLX model "billed to a subscription" would be wrong."""
    html = _model_table([_bucket("Qwen-MLX", 500, api_billed=False, local=True)])

    assert "$0.00" in html
    assert "credits" not in html
