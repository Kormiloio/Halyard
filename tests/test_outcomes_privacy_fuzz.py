"""Privacy fuzz test for the v3.0 outcome graph.

Spec: openspec/changes/v3.0-outcome-graph/specs/privacy-contract.md

The contract: no source code, prompt text, secrets, or other arbitrary
user content may leak into a rendered output surface from any outcome
collector. This test seeds randomized "sensitive substrings" into every
free-text-ish field on AiSession, runs every public outcome surface, and
asserts none of those substrings appears in any output.

If this test ever fails, a real privacy regression has happened.
Investigate before merging.
"""

from __future__ import annotations

import random
import string
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard.ai_log import AiSession
from halyard.attempt_tracker import repeated_attempt_count
from halyard.dashboard import _leverage_panel
from halyard.invoicing import _render_pr_refs_subsection

# Random sensitive markers we'll inject into session fields. Each marker
# is a unique 12-char tag we can grep for in every output surface.
_SECRET_MARKERS = [
    "SECRET-A1B2",
    "SECRET-C3D4",
    "SECRET-E5F6",
    "SECRET-G7H8",
    "SECRET-I9J0",
]


def _rand_str(seed: random.Random, n: int = 8) -> str:
    return "".join(seed.choices(string.ascii_letters + string.digits, k=n))


def _make_fuzzed_sessions(seed: random.Random, n: int = 100) -> list[AiSession]:
    """Generate n sessions, half of them carrying a sensitive marker.

    Markers are placed in `note` and `resume_command` because those are
    the high-risk free-text fields. Outcome collectors must never echo
    these into their outputs.
    """
    sessions: list[AiSession] = []
    base = datetime(2026, 5, 14, 12)
    for i in range(n):
        marker = seed.choice(_SECRET_MARKERS) if i % 2 == 0 else None
        note = f"work {marker} on feature" if marker else "ordinary note"
        sessions.append(
            AiSession(
                start=base - timedelta(hours=i),
                end=base - timedelta(hours=i) + timedelta(minutes=10),
                tool="claude-code",
                model="sonnet",
                input_tokens=seed.randint(100, 5000),
                output_tokens=seed.randint(20, 1000),
                cost_usd=round(seed.random(), 4),
                project="acme:web",
                note=note,
                resume_command=f"echo {marker}" if marker else None,
                branch=f"feat/AUTH-{i}",
                commit_count=seed.randint(0, 5),
                code_added=seed.randint(0, 200),
                code_removed=seed.randint(0, 100),
                pr_ref=f"acme/repo#{i}" if i % 3 == 0 else None,
                pr_state=seed.choice(["merged", "open", "closed", "none"]) if i % 3 == 0 else None,
            )
        )
    return sessions


@pytest.mark.parametrize("trial", range(5))
def test_outcome_surfaces_do_not_leak_note_or_resume_command(trial: int) -> None:
    """Across 5 randomized trials, no marker from `note` or `resume_command`
    may appear in any outcome rendering surface."""
    seed = random.Random(trial * 17 + 1)
    sessions = _make_fuzzed_sessions(seed, n=80)

    # 1. Dashboard Leverage panel must not echo notes/resume_commands.
    leverage_html = _leverage_panel(sessions, datetime(2026, 5, 14, 12))
    for marker in _SECRET_MARKERS:
        assert marker not in leverage_html, (
            f"Leverage panel leaked '{marker}' from note/resume_command field"
        )

    # 2. Invoice appendix PR-refs subsection must list only PR refs.
    pr_lines = _render_pr_refs_subsection(sessions)
    pr_text = "\n".join(pr_lines)
    for marker in _SECRET_MARKERS:
        assert marker not in pr_text, f"Invoice PR-refs leaked '{marker}'"

    # 3. attempt_tracker is an integer-only surface — pin the contract.
    for s in sessions:
        result = repeated_attempt_count(s, sessions)
        assert isinstance(result, int)


@pytest.mark.parametrize("trial", range(5))
def test_v31_friction_does_not_leak_gh_freetext(trial: int, tmp_path: Path) -> None:
    """v3.1 binding gate: sensitive markers seeded into a gh PR payload's
    title, body, review bodies, and comment bodies must never reach the
    ReviewFriction values, the egress-eligible pr_cache payload, the log
    `a` record, the outcome report, the Leverage panel, or the invoice
    appendix. parse_friction must read only state/counts/timestamps.
    """
    import sqlite3

    from halyard.invoicing import _render_pr_refs_subsection
    from halyard.outcomes import (
        ResolutionResult,
        _friction_cache_set,
        _write_amendment,
        outcome_report,
        parse_friction,
    )

    seed = random.Random(trial * 31 + 7)
    m = seed.choice(_SECRET_MARKERS)
    # A gh `pr view` payload stuffed with the marker in EVERY free-text
    # field a careless parser might echo.
    pr_view = {
        "number": 42,
        "state": "MERGED",
        "title": f"feat: {m} secret title",
        "body": f"PR body with {m}",
        "bodyText": f"body text {m}",
        "createdAt": "2026-05-01T10:00:00Z",
        "mergedAt": "2026-05-01T12:30:00Z",
        "reviewDecision": "CHANGES_REQUESTED",
        "reviews": [
            {"state": "CHANGES_REQUESTED", "body": f"please fix {m}", "author": {"login": m}},
            {"state": "APPROVED", "body": f"ok {m}"},
        ],
        "comments": [{"body": f"comment {m}"}, {"body": f"second {m}"}],
    }
    friction = parse_friction(pr_view, inline_comment_count=3)

    # 1. The reduced values are integers/enum only — no marker anywhere.
    assert m not in repr(friction)
    assert friction.review_rounds == 1
    assert friction.review_comments == 5  # 2 issue + 3 inline
    assert friction.time_to_merge_s == 9000
    assert friction.review_decision == "CHANGES_REQUESTED"

    # 2. The egress-eligible pr_cache payload must not contain the marker.
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE pr_cache (cache_key TEXT PRIMARY KEY, payload TEXT, fetched_at TEXT)"
    )
    _friction_cache_set(conn, "k:friction", friction, "merged")
    payload = conn.execute("SELECT payload FROM pr_cache").fetchone()["payload"]
    assert m not in payload

    # 3. The log `a` amendment record must not contain the marker.
    proj = tmp_path / "p"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "ai-sessions.log").write_text("; log\n")
    result = ResolutionResult(
        session_hash="deadbeef",
        pr_ref="acme/repo#42",
        pr_state="merged",
        resolved_at="2026-05-02T09:00:00",
        review_comments=friction.review_comments,
        review_rounds=friction.review_rounds,
        time_to_merge_s=friction.time_to_merge_s,
        review_decision=friction.review_decision,
    )
    _write_amendment(proj, result)
    assert m not in (proj / "ai-sessions.log").read_text()

    # 4. Rendered surfaces, with a session carrying the friction values.
    s = AiSession(
        start=datetime(2026, 5, 1, 10),
        end=datetime(2026, 5, 1, 11),
        tool="claude-code",
        model="sonnet",
        input_tokens=10,
        output_tokens=10,
        cost_usd=1.0,
        project="acme:web",
        pr_ref="acme/repo#42",
        pr_state="merged",
        review_comments=friction.review_comments,
        review_rounds=friction.review_rounds,
        time_to_merge_s=friction.time_to_merge_s,
        review_decision=friction.review_decision,
        outcome_resolved_at="2026-05-02T09:00:00",
    )
    surfaces = [
        _leverage_panel([s], datetime(2026, 5, 1, 12)),
        "\n".join(_render_pr_refs_subsection([s])),
        repr(outcome_report([s], since=datetime(2026, 4, 1).date())),
    ]
    for out in surfaces:
        assert m not in out


def test_shell_history_returns_only_an_integer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Privacy contract: shell_history.count_test_runs_in_window MUST return
    an integer, never a string or a list of lines."""
    from halyard.shell_history import count_test_runs_in_window

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("HISTFILE", raising=False)
    # Drop the same marker into shell history; the function must not echo it.
    bash_history = tmp_path / ".bash_history"
    bash_history.write_text(
        "SECRET-A1B2=value pytest tests/\npytest tests/ # comment SECRET-C3D4\necho SECRET-E5F6\n"
    )

    now = datetime(2026, 5, 14, 12)
    result = count_test_runs_in_window(now - timedelta(hours=1), now)
    assert isinstance(result, int)
    # The only thing this function may return is a count. We don't pin a
    # specific value here — the substring-leak assertion is what matters,
    # and it's implicit in the int-only return type.
