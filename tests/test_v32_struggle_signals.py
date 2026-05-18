"""v3.2 struggle signals — surface-only over already-captured fields.

Spec: openspec/changes/v3.2-struggle-signals/specs/struggle-signals.md
"""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timedelta

from halyard.ai_log import AiSession
from halyard.dashboard import _leverage_panel
from halyard.invoicing import _render_pr_refs_subsection
from halyard.leverage import (
    render_rejection_phrase,
    struggle_signals,
    summarize_struggle,
)
from halyard.outcomes import outcome_report
from halyard.tui.widgets.leverage_pane import LeveragePane

_NOW = datetime(2026, 5, 18, 12)


def _s(
    *,
    tool_calls: int | None = None,
    tool_errors: int | None = None,
    accepted: int | None = None,
    rejected: int | None = None,
    interaction_available: bool | None = None,
    pr_state: str | None = "merged",
    days: int = 2,
) -> AiSession:
    s = AiSession(
        start=_NOW - timedelta(days=days),
        end=_NOW - timedelta(days=days) + timedelta(hours=1),
        tool="cursor",
        model="sonnet",
        input_tokens=10,
        output_tokens=10,
        cost_usd=1.0,
        project="acme:web",
        pr_state=pr_state,
        pr_ref="acme/web#1" if pr_state else None,
    )
    s.tool_calls = tool_calls
    s.tool_errors = tool_errors
    s.accepted_suggestion_count = accepted
    s.rejected_suggestion_count = rejected
    s.interaction_data_available = interaction_available
    return s


# --- §4.1 tool-error math -------------------------------------------------


def test_tool_error_rate_basic() -> None:
    st = struggle_signals([_s(tool_calls=10, tool_errors=2), _s(tool_calls=10, tool_errors=3)])
    assert st.tool_error_total == 5
    assert st.tool_error_rate == 0.25


def test_tool_error_none_when_no_tool_calls_anywhere() -> None:
    st = struggle_signals([_s(tool_calls=None, tool_errors=None)])
    assert st.tool_error_total is None
    assert st.tool_error_rate is None


def test_tool_error_rate_none_when_denominator_zero() -> None:
    st = struggle_signals([_s(tool_calls=0, tool_errors=0)])
    assert st.tool_error_total == 0  # has tool data (a 0 count is real)
    assert st.tool_error_rate is None  # never divide by zero


# --- §4.2 rejection availability gate -------------------------------------


def test_rejection_counts_only_interaction_captured_sessions() -> None:
    sessions = [
        _s(tool_calls=5, tool_errors=0, accepted=8, rejected=2, interaction_available=True),
        # non-Cursor: has no interaction data; must NOT enter the denom
        _s(tool_calls=5, tool_errors=0, accepted=None, rejected=None, interaction_available=None),
    ]
    st = struggle_signals(sessions)
    assert st.rejection_covered == 1
    assert st.rejection_total == 2
    assert st.rejection_rate == 0.2  # 2 / (8+2), the non-captured one excluded
    assert st.rejection_total_sessions == 2


def test_rejection_all_none_when_no_captured_sessions() -> None:
    st = struggle_signals([_s(tool_calls=5, tool_errors=1, interaction_available=None)])
    assert st.rejection_covered == 0
    assert st.rejection_total is None
    assert st.rejection_rate is None


def test_rejection_rate_none_when_no_accept_or_reject() -> None:
    st = struggle_signals(
        [_s(tool_calls=1, tool_errors=0, accepted=0, rejected=0, interaction_available=True)]
    )
    assert st.rejection_covered == 1
    assert st.rejection_total == 0
    assert st.rejection_rate is None  # 0/(0+0) → None, not 0%


# --- §4.3 R3 honesty: never a bare 0 --------------------------------------


def test_phrase_not_captured_when_covered_zero() -> None:
    st = struggle_signals([_s(tool_calls=5, tool_errors=1, interaction_available=None)])
    phrase = render_rejection_phrase(st)
    assert phrase == "rejections: not captured"
    assert "0" not in phrase  # no misleading bare zero / 0%


def test_phrase_includes_coverage_when_present() -> None:
    sessions = [
        _s(tool_calls=5, tool_errors=0, accepted=8, rejected=2, interaction_available=True),
        _s(tool_calls=5, tool_errors=0, interaction_available=None),
        _s(tool_calls=5, tool_errors=0, interaction_available=None),
    ]
    st = struggle_signals(sessions)
    phrase = render_rejection_phrase(st)
    assert "rejections 2" in phrase
    assert "(20%)" in phrase
    assert "over 1 of 3 sessions" in phrase
    assert "rest: not captured" in phrase


def test_phrase_zero_rejections_still_shows_coverage_not_bare_zero() -> None:
    # captured but genuinely zero rejections — must still be honest, not "0"
    st = struggle_signals(
        [_s(tool_calls=4, tool_errors=0, accepted=5, rejected=0, interaction_available=True)]
    )
    phrase = render_rejection_phrase(st)
    assert phrase == "rejections 0 (0%) (over 1 of 1 sessions; rest: not captured)"


# --- §4.4 report per-bucket ----------------------------------------------


def test_report_bucket_has_struggle() -> None:
    since = (_NOW - timedelta(days=10)).date()
    sessions = [
        _s(tool_calls=10, tool_errors=4, accepted=3, rejected=1, interaction_available=True),
        _s(tool_calls=10, tool_errors=0, pr_state="open", interaction_available=None),
    ]
    buckets = {b.label: b for b in outcome_report(sessions, since=since)}
    merged = buckets["Shipped (PR merged)"]
    assert merged.struggle is not None
    assert merged.struggle.tool_error_total == 4
    assert merged.struggle.rejection_covered == 1
    # empty bucket → struggle stays None (absent-data path)
    assert buckets["Abandoned (PR closed)"].struggle is None


def test_report_bucket_no_tool_data_struggle_inert() -> None:
    since = (_NOW - timedelta(days=10)).date()
    b = {x.label: x for x in outcome_report([_s(tool_calls=None)], since=since)}
    merged = b["Shipped (PR merged)"]
    assert merged.struggle is not None
    assert merged.struggle.tool_error_total is None  # nothing to show → cli omits the line


# --- §4.5 web ↔ TUI parity + absent path ---------------------------------


def test_web_tui_struggle_parity() -> None:
    sessions = [
        _s(tool_calls=10, tool_errors=3, accepted=6, rejected=4, interaction_available=True)
        for _ in range(5)
    ]
    html = _leverage_panel(sessions, _NOW)
    pane = LeveragePane()
    pane.render_sessions(sessions, _NOW)
    st = summarize_struggle(sessions, _NOW)
    # both surfaces show the same tool-error figure and rejection phrase
    assert f"{st.tool_error_total} tool errors" in html
    assert f"{st.tool_error_total} tool errors" in pane.last_rendered_text
    phrase = render_rejection_phrase(st)
    assert phrase in html
    assert phrase in pane.last_rendered_text


def test_absent_struggle_renders_v31_identical() -> None:
    sessions = [_s(tool_calls=None, pr_state="merged")]
    html = _leverage_panel(sessions, _NOW)
    assert "leverage-struggle" not in html
    pane = LeveragePane()
    pane.render_sessions(sessions, _NOW)
    assert "tool errors" not in pane.last_rendered_text


# --- §4.6 R6: no new field / no new log token ----------------------------


def test_no_new_aisession_field_added() -> None:
    names = {f.name for f in fields(AiSession)}
    # the five v3.2 reads, all pre-existing
    assert {
        "tool_calls",
        "tool_errors",
        "accepted_suggestion_count",
        "rejected_suggestion_count",
        "interaction_data_available",
    } <= names
    # v3.2 introduced no struggle-* field on the session model
    assert not any("struggle" in n for n in names)


def test_no_new_log_token_for_struggle() -> None:
    s = _s(tool_calls=9, tool_errors=2, accepted=3, rejected=1, interaction_available=True)
    assert "struggle" not in s.to_log_line()


# --- §4.7 R7: invoice appendix unchanged ---------------------------------


def test_invoice_appendix_ignores_struggle() -> None:
    base = _s(pr_state="merged")
    rich = _s(
        tool_calls=10,
        tool_errors=9,
        accepted=1,
        rejected=9,
        interaction_available=True,
        pr_state="merged",
    )
    assert _render_pr_refs_subsection([base]) == _render_pr_refs_subsection([rich])
    assert "struggle" not in "\n".join(_render_pr_refs_subsection([rich]))


# --- §4.8 privacy ---------------------------------------------------------


def test_struggle_surfaces_do_not_leak_free_text() -> None:
    marker = "SECRET-STRUGGLE-9Z"
    s = _s(tool_calls=10, tool_errors=5, accepted=2, rejected=8, interaction_available=True)
    s.note = f"do not leak {marker}"
    s.resume_command = f"echo {marker}"
    surfaces = [
        _leverage_panel([s], _NOW),
        repr(outcome_report([s], since=(_NOW - timedelta(days=10)).date())),
    ]
    pane = LeveragePane()
    pane.render_sessions([s], _NOW)
    surfaces.append(pane.last_rendered_text)
    for out in surfaces:
        assert marker not in out
