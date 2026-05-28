"""v3.1 review-friction — unit + degraded-path + privacy + parity tests.

Spec: openspec/changes/v3.1-review-friction/specs/review-friction.md
"""

from __future__ import annotations

import sqlite3
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from halyard.ai_log import AiSession
from halyard.outcomes import (
    ReviewFriction,
    _friction_cache_get,
    _friction_cache_set,
    _resolve_friction,
    gh_pr_inline_comment_count,
    gh_pr_view,
    outcome_report,
    parse_friction,
)


def _mem() -> sqlite3.Connection:
    from halyard.db import _CREATE_SCHEMA_V1

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_CREATE_SCHEMA_V1)
    conn.commit()
    return conn


def _cp(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def _sess(**kw: object) -> AiSession:
    base = {
        "start": datetime(2026, 5, 1, 10),
        "end": datetime(2026, 5, 1, 11),
        "tool": "claude-code",
        "model": "sonnet",
        "input_tokens": 10,
        "output_tokens": 10,
        "cost_usd": 1.0,
        "project": "acme:web",
    }
    base.update(kw)
    return AiSession(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5.1 parse_friction units
# ---------------------------------------------------------------------------


def test_parse_friction_full_merged() -> None:
    pv = {
        "state": "MERGED",
        "createdAt": "2026-05-01T10:00:00Z",
        "mergedAt": "2026-05-01T11:00:00Z",
        "reviewDecision": "APPROVED",
        "reviews": [
            {"state": "CHANGES_REQUESTED"},
            {"state": "APPROVED"},
            {"state": "CHANGES_REQUESTED"},
        ],
        "comments": [{}, {}],
    }
    f = parse_friction(pv, 5)
    assert (f.review_comments, f.review_rounds, f.time_to_merge_s, f.review_decision) == (
        7,
        2,
        3600,
        "APPROVED",
    )


def test_parse_friction_zero_rounds_and_zero_comments() -> None:
    pv = {"state": "OPEN", "reviews": [], "comments": [], "reviewDecision": "REVIEW_REQUIRED"}
    f = parse_friction(pv, 0)
    assert f.review_rounds == 0
    assert f.review_comments == 0
    assert f.time_to_merge_s is None  # not merged
    assert f.review_decision == "REVIEW_REQUIRED"


def test_parse_friction_inline_missing_only_drops_comment_count() -> None:
    pv = {
        "state": "MERGED",
        "createdAt": "2026-05-01T10:00:00Z",
        "mergedAt": "2026-05-01T10:30:00Z",
        "reviews": [{"state": "CHANGES_REQUESTED"}],
        "comments": [{}],
    }
    f = parse_friction(pv, None)
    assert f.review_comments is None  # unknown, NOT 1, NOT 0
    assert f.review_rounds == 1
    assert f.time_to_merge_s == 1800


def test_parse_friction_none_payload_all_absent() -> None:
    f = parse_friction(None, 9)
    assert (f.review_comments, f.review_rounds, f.time_to_merge_s, f.review_decision) == (
        None,
        None,
        None,
        None,
    )


def test_parse_friction_missing_keys_fail_closed() -> None:
    f = parse_friction({"state": "MERGED"}, 2)
    assert f.review_rounds is None  # no reviews key
    assert f.review_comments is None  # no comments key
    assert f.time_to_merge_s is None  # no timestamps
    assert f.review_decision is None


def test_parse_friction_junk_review_decision_dropped() -> None:
    f = parse_friction(
        {"state": "OPEN", "reviews": [], "comments": [], "reviewDecision": "LGTM"}, 0
    )
    assert f.review_decision is None


def test_parse_friction_closed_unmerged_has_no_ttm() -> None:
    pv = {
        "state": "CLOSED",
        "createdAt": "2026-05-01T10:00:00Z",
        "mergedAt": None,
        "reviews": [],
        "comments": [],
    }
    assert parse_friction(pv, 0).time_to_merge_s is None


def test_parse_friction_negative_duration_rejected() -> None:
    pv = {
        "state": "MERGED",
        "createdAt": "2026-05-01T12:00:00Z",
        "mergedAt": "2026-05-01T10:00:00Z",  # before created → negative
        "reviews": [],
        "comments": [],
    }
    assert parse_friction(pv, 0).time_to_merge_s is None


# ---------------------------------------------------------------------------
# 5.2 per-PR call dedup + cache (merged permanent, open TTL)
# ---------------------------------------------------------------------------


def test_resolve_friction_caches_and_dedups() -> None:
    conn = _mem()
    pv = _cp(
        '{"state":"MERGED","createdAt":"2026-05-01T10:00:00Z",'
        '"mergedAt":"2026-05-01T11:00:00Z","reviews":[],"comments":[],'
        '"reviewDecision":"APPROVED"}'
    )
    with patch("halyard.outcomes.subprocess.run", return_value=pv) as run:
        f1 = _resolve_friction(conn, "acme/web#1", "merged", "git@github.com:acme/web.git")
        n_first = run.call_count
        f2 = _resolve_friction(conn, "acme/web#1", "merged", "git@github.com:acme/web.git")
    assert f1 == f2
    assert n_first <= 2  # ≤2 gh calls (pr view + inline) on first miss
    assert run.call_count == n_first  # second call fully served from cache


def test_friction_cache_merged_permanent_open_ttl() -> None:
    conn = _mem()
    fr = ReviewFriction(3, 1, 7200, "APPROVED")
    _friction_cache_set(conn, "k:merged", fr, "merged")
    _friction_cache_set(conn, "k:open", fr, "open")
    stale = (datetime.now() - timedelta(days=30)).isoformat()
    conn.execute("UPDATE pr_cache SET fetched_at = ?", (stale,))
    conn.commit()
    assert _friction_cache_get(conn, "k:merged") == fr  # immutable post-merge
    assert _friction_cache_get(conn, "k:open") is None  # expired past TTL


def test_resolve_friction_total_failure_not_cached() -> None:
    conn = _mem()
    with patch("halyard.outcomes.subprocess.run", return_value=_cp("", returncode=1)):
        f = _resolve_friction(conn, "acme/web#9", "merged", "git@github.com:acme/web.git")
    assert f == ReviewFriction()
    assert conn.execute("SELECT COUNT(*) c FROM pr_cache").fetchone()["c"] == 0


# ---------------------------------------------------------------------------
# 5.3 degraded paths
# ---------------------------------------------------------------------------


def test_gh_pr_view_nonzero_returns_none() -> None:
    with patch("halyard.outcomes.subprocess.run", return_value=_cp("", returncode=1)):
        assert gh_pr_view("acme/web#1", "git@github.com:acme/web.git") is None


def test_gh_pr_view_timeout_returns_none() -> None:
    with patch("halyard.outcomes.subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 10)):
        assert gh_pr_view("acme/web#1", "git@github.com:acme/web.git") is None


def test_gh_pr_view_invalid_ref_returns_none() -> None:
    assert gh_pr_view("not-a-ref", None) is None


def test_inline_comment_count_404_returns_none() -> None:
    with patch("halyard.outcomes.subprocess.run", return_value=_cp("Not Found", returncode=1)):
        assert gh_pr_inline_comment_count("acme/web#1", "git@github.com:acme/web.git") is None


def test_inline_comment_count_non_numeric_returns_none() -> None:
    with patch("halyard.outcomes.subprocess.run", return_value=_cp("garbage")):
        assert gh_pr_inline_comment_count("acme/web#1", "git@github.com:acme/web.git") is None


def test_degraded_inline_only_keeps_other_three() -> None:
    conn = _mem()

    def fake_run(cmd, **kw):  # type: ignore[no-untyped-def]
        if "view" in cmd:
            return _cp(
                '{"state":"MERGED","createdAt":"2026-05-01T10:00:00Z",'
                '"mergedAt":"2026-05-01T11:00:00Z","reviews":'
                '[{"state":"CHANGES_REQUESTED"}],"comments":[{}],'
                '"reviewDecision":"CHANGES_REQUESTED"}'
            )
        return _cp("Not Found", returncode=1)  # the inline-comments API 404s

    with patch("halyard.outcomes.subprocess.run", side_effect=fake_run):
        f = _resolve_friction(conn, "acme/web#1", "merged", "git@github.com:acme/web.git")
    assert f.review_comments is None  # only this is absent
    assert f.review_rounds == 1
    assert f.time_to_merge_s == 3600
    assert f.review_decision == "CHANGES_REQUESTED"


# ---------------------------------------------------------------------------
# 5.4 report friction breakdown + v3.0-identical absent path
# ---------------------------------------------------------------------------


def test_report_bucket_medians() -> None:
    since = datetime(2026, 4, 1).date()
    sessions = [
        _sess(pr_state="merged", time_to_merge_s=3600, review_comments=2),
        _sess(pr_state="merged", time_to_merge_s=7200, review_comments=8),
        _sess(pr_state="open"),
    ]
    buckets = {b.label: b for b in outcome_report(sessions, since=since)}
    merged = buckets["Shipped (PR merged)"]
    assert merged.median_time_to_merge_s == 5400
    assert merged.median_review_comments == 5
    assert buckets["In-flight (PR open)"].median_time_to_merge_s is None


def test_report_absent_friction_is_v30_identical() -> None:
    since = datetime(2026, 4, 1).date()
    sessions = [_sess(pr_state="merged"), _sess(pr_state="open")]
    for b in outcome_report(sessions, since=since):
        assert b.median_time_to_merge_s is None
        assert b.median_review_comments is None


# ---------------------------------------------------------------------------
# 5.5 additive migration (v4 → v5), no reset, original line intact
# ---------------------------------------------------------------------------


def test_migration_v4_to_v5_is_additive() -> None:
    import halyard.db as db

    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        "CREATE TABLE outcomes(session_id TEXT PRIMARY KEY, pr_ref TEXT, "
        "pr_state TEXT, resolved_at TEXT); CREATE TABLE sessions(id TEXT);"
    )
    c.execute("PRAGMA user_version=4")
    c.commit()
    sql = dict(db._MIGRATIONS)[4]
    db._apply_migration(c, sql)
    cols = {r[1] for r in c.execute("PRAGMA table_info(outcomes)")}
    assert {
        "review_comment_count",
        "review_round_trips",
        "time_to_merge_seconds",
        "review_decision",
    } <= cols
    db._apply_migration(c, sql)  # idempotent self-heal, must not raise


def test_friction_amendment_does_not_mutate_original_s_line(tmp_path: Path) -> None:
    from halyard.outcomes import ResolutionResult, _write_amendment

    proj = tmp_path / "p"
    proj.mkdir(parents=True)
    log = proj / "ai-sessions.log"
    original = "s 2026-05-01T10:00 2026-05-01T11:00 claude-code sonnet 10 10 1.0\n"
    log.write_text("; log\n" + original, encoding="utf-8")
    _write_amendment(
        proj,
        ResolutionResult(
            session_hash="abc123",
            pr_ref="acme/web#4",
            pr_state="merged",
            resolved_at="2026-05-02T09:00:00",
            review_comments=3,
            review_rounds=1,
            time_to_merge_s=3600,
            review_decision="APPROVED",
        ),
    )
    text = log.read_text(encoding="utf-8")
    assert original in text  # s line byte-intact
    assert "a abc123" in text
    assert "review_comments=3" in text and "review_rounds=1" in text


# ---------------------------------------------------------------------------
# 4.2 privacy — gh --json field list carries no free-text key
# ---------------------------------------------------------------------------


def test_gh_pr_view_json_field_list_has_no_freetext_key() -> None:
    captured: list[list[str]] = []

    def grab(cmd, **kw):  # type: ignore[no-untyped-def]
        captured.append(cmd)
        return _cp('{"state":"OPEN","reviews":[],"comments":[]}')

    with patch("halyard.outcomes.subprocess.run", side_effect=grab):
        gh_pr_view("acme/web#1", "git@github.com:acme/web.git")

    json_arg = captured[0][captured[0].index("--json") + 1]
    fields = set(json_arg.split(","))
    for forbidden in ("body", "bodyText", "title", "author", "comments.body"):
        assert forbidden not in fields
    assert fields == {
        "number",
        "state",
        "createdAt",
        "mergedAt",
        "reviewDecision",
        "reviews",
        "comments",
    }


# ---------------------------------------------------------------------------
# 4.3 config gating — enabled=false makes zero gh calls
# ---------------------------------------------------------------------------


def test_outcomes_disabled_makes_no_gh_calls(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from halyard.cli_outcome import app

    proj = tmp_path
    (proj / "halyard.toml").write_text("[outcomes]\nenabled = false\n", encoding="utf-8")
    (proj / "ai-sessions.log").write_text("; log\n", encoding="utf-8")

    with (
        patch("halyard.ai_log.find_project_dir", return_value=proj),
        patch("halyard.outcomes.subprocess.run") as run,
        patch("halyard.outcomes.resolve_sessions") as resolve,
    ):
        result = CliRunner().invoke(app, ["sync"])
    assert result.exit_code == 0
    run.assert_not_called()
    resolve.assert_not_called()


# ---------------------------------------------------------------------------
# 5.6 Leverage friction parity (web == TUI) + perf-pinned
# ---------------------------------------------------------------------------


def test_leverage_friction_web_tui_parity_and_perf(perf_ceiling) -> None:  # type: ignore[no-untyped-def]
    from halyard.dashboard import _leverage_panel
    from halyard.leverage import humanize_seconds, summarize
    from halyard.tui.widgets.leverage_pane import LeveragePane

    now = datetime(2026, 5, 17, 12)
    sessions = [
        _sess(
            start=now - timedelta(days=2),
            end=now - timedelta(days=2, hours=-1),
            pr_state="merged",
            time_to_merge_s=90000,
            review_comments=6,
        )
        for _ in range(200)
    ]

    s = summarize(sessions, now)
    assert s.median_time_to_merge_s == 90000
    assert s.median_review_comments == 6

    t0 = time.perf_counter()
    html = _leverage_panel(sessions, now)
    elapsed = time.perf_counter() - t0
    assert elapsed < perf_ceiling(1.0)  # well inside the 10s refresh budget

    pane = LeveragePane()
    pane.render_sessions(sessions, now)

    human = humanize_seconds(90000)  # "1d 1h"
    assert human in html  # web shows it
    assert human in pane.last_rendered_text  # TUI shows the same number
    assert "6 review comments" in html
    assert "6 review comments" in pane.last_rendered_text


def test_leverage_no_friction_renders_v30_identical() -> None:
    from halyard.dashboard import _leverage_panel

    now = datetime(2026, 5, 17, 12)
    sessions = [_sess(start=now - timedelta(days=1), end=now, pr_state="merged")]
    html = _leverage_panel(sessions, now)
    assert "leverage-friction" not in html
