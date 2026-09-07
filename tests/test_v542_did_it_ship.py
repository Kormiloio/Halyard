"""v5.42 — the "Did it ship?" panel could not answer yes.

On a machine that had merged four PRs that afternoon it read `0%`, `0 of
140 sessions landed in merged PRs`, `Not synced 140 (100%)`. Two defects:
`gh pr list` defaults to open-only so a merged PR was invisible to the
resolver, and the headline divided by *every* session including the
unresolved ones, so "nobody looked" rendered as a confident zero.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from halyard import outcomes
from halyard.ai_log import AiSession
from halyard.leverage import summarize

NOW = datetime(2026, 9, 6, 12)


def _session(state: str | None, days_ago: int = 1) -> AiSession:
    s = AiSession(
        start=NOW - timedelta(days=days_ago),
        end=NOW - timedelta(days=days_ago) + timedelta(hours=1),
        tool="claude-code",
        model="claude-opus-5",
        input_tokens=10,
        output_tokens=1,
        cost_usd=0.0,
    )
    s.pr_state = state
    return s


# --- the resolver can see merged PRs ----------------------------------


def test_the_pr_query_asks_for_every_state(monkeypatch) -> None:
    """`gh pr list` defaults to --state open.

    Without an explicit state the one outcome this panel exists to report
    is invisible. Verified against a real branch: bare returns [], with
    `--state all` returns the merged PR #38.
    """
    seen: list[list[str]] = []

    class _R:
        returncode = 0
        stdout = "[]"

    monkeypatch.setattr(outcomes.subprocess, "run", lambda cmd, **kw: (seen.append(cmd), _R())[1])
    outcomes.fetch_prs_for_branch("some-branch")

    assert seen, "gh was never invoked"
    cmd = seen[0]
    assert "--state" in cmd, "no state flag: gh defaults to open-only"
    assert cmd[cmd.index("--state") + 1] == "all"


def test_all_four_outcome_states_stay_reachable(monkeypatch) -> None:
    """`--state merged` would fix the headline and empty Open/Closed."""

    class _R:
        returncode = 0
        stdout = "[]"

    seen: list[list[str]] = []
    monkeypatch.setattr(outcomes.subprocess, "run", lambda cmd, **kw: (seen.append(cmd), _R())[1])
    outcomes.fetch_prs_for_branch("b")

    assert "merged" not in seen[0], "narrowing to merged loses the other buckets"


# --- the denominator --------------------------------------------------


def test_unresolved_sessions_are_out_of_the_denominator() -> None:
    """1 merged of 2 resolved is 50%, not 25% because two were never checked."""
    s = summarize([_session("merged"), _session("none"), _session(None), _session(None)], NOW)

    assert s.total == 4
    assert s.resolved == 2
    assert s.pct == 50


def test_a_wholly_unresolved_window_is_not_measured() -> None:
    """The reported symptom: 140 unsynced sessions rendering as a grey 0%."""
    s = summarize([_session(None) for _ in range(140)], NOW)

    assert s.unsynced == 140
    assert s.resolved == 0
    assert s.measured is False


def test_a_resolved_window_is_measured() -> None:
    assert summarize([_session("merged")], NOW).measured is True


def test_genuinely_nothing_shipped_still_reports_zero() -> None:
    """The honest zero must survive: resolved, and none of them merged."""
    s = summarize([_session("none"), _session("closed")], NOW)

    assert s.measured is True
    assert s.pct == 0, "this zero is a measurement"


def test_an_empty_window_is_not_measured() -> None:
    assert summarize([], NOW).measured is False


def test_row_counts_still_describe_the_whole_window() -> None:
    """Only the headline changes denominator — how much is unresolved is
    itself worth showing, so the buckets keep counting against total."""
    s = summarize([_session("merged"), _session(None), _session(None)], NOW)

    assert s.total == 3
    assert s.merged == 1
    assert s.unsynced == 2
