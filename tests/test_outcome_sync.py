"""Tests for outcomes.py — PR resolution, caching, attribution, and report bucketing."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch  # MagicMock used in fetch_prs tests

from halyard.ai_log import AiSession
from halyard.outcomes import (
    _best_pr_for_session,
    _normalize_pr_ref,
    _parse_pr_ref,
    _remote_to_repo,
    fetch_prs_for_branch,
    gh_available,
    outcome_report,
    resolve_sessions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_START = datetime(2026, 5, 1, 10, 0, 0)
_END = datetime(2026, 5, 1, 11, 0, 0)


def _session(
    *,
    branch: str | None = "main",
    pr_ref: str | None = None,
    pr_state: str | None = None,
    project: str | None = "acme:web",
    start: datetime = _START,
    end: datetime = _END,
) -> AiSession:
    return AiSession(
        start=start,
        end=end,
        tool="claude-code",
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        project=project,
        branch=branch,
        pr_ref=pr_ref,
        pr_state=pr_state,
    )


def _pr(
    number: int = 42,
    state: str = "merged",
    created_offset_hours: float = 0.5,
    base: datetime = _END,
) -> dict:  # type: ignore[type-arg]
    created = base + timedelta(hours=created_offset_hours)
    return {
        "number": number,
        "state": state,
        "createdAt": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "url": f"https://github.com/acme/web/pull/{number}",
        "mergedAt": None,
        "baseRefName": "main",
    }


def _mem_db() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with the pr_cache and outcomes tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE pr_cache (cache_key TEXT PRIMARY KEY, payload TEXT, fetched_at TEXT);
        CREATE TABLE outcomes (
            session_id TEXT PRIMARY KEY, pr_ref TEXT, pr_state TEXT, resolved_at TEXT
        );
        """
    )
    conn.commit()
    return conn


def _halyard_project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "halyard.toml").write_text("[project]\nslug = 'acme:web'\n")
    (tmp_path / "ai-sessions.log").write_text(
        "; Halyard AI session log\n"
        "; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd>\n"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# gh_available
# ---------------------------------------------------------------------------


def test_gh_available_returns_true_when_gh_installed() -> None:
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch("halyard.outcomes.subprocess.run", return_value=mock_result):
        assert gh_available() is True


def test_gh_available_returns_false_when_not_installed() -> None:
    with patch("halyard.outcomes.subprocess.run", side_effect=FileNotFoundError):
        assert gh_available() is False


def test_gh_available_returns_false_on_timeout() -> None:
    import subprocess

    with patch("halyard.outcomes.subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 5)):
        assert gh_available() is False


def test_gh_available_returns_false_on_nonzero_exit() -> None:
    mock_result = MagicMock()
    mock_result.returncode = 1
    with patch("halyard.outcomes.subprocess.run", return_value=mock_result):
        assert gh_available() is False


# ---------------------------------------------------------------------------
# _remote_to_repo
# ---------------------------------------------------------------------------


def test_remote_to_repo_ssh() -> None:
    assert _remote_to_repo("git@github.com:acme/web.git") == "acme/web"


def test_remote_to_repo_https() -> None:
    assert _remote_to_repo("https://github.com/acme/web.git") == "acme/web"


def test_remote_to_repo_https_no_dot_git() -> None:
    assert _remote_to_repo("https://github.com/acme/web") == "acme/web"


def test_remote_to_repo_unknown_scheme_returns_none() -> None:
    assert _remote_to_repo("svn://example.com/repo") is None


def test_remote_to_repo_empty_returns_none() -> None:
    assert _remote_to_repo("") is None


# ---------------------------------------------------------------------------
# _normalize_pr_ref
# ---------------------------------------------------------------------------


def test_normalize_pr_ref_with_remote() -> None:
    assert _normalize_pr_ref(42, "git@github.com:acme/web.git") == "acme/web#42"


def test_normalize_pr_ref_without_remote() -> None:
    assert _normalize_pr_ref(42, None) == "#42"


# ---------------------------------------------------------------------------
# _parse_pr_ref
# ---------------------------------------------------------------------------


def test_parse_pr_ref_full_url() -> None:
    url = "https://github.com/acme/web/pull/42"
    assert _parse_pr_ref(url, None) == "acme/web#42"


def test_parse_pr_ref_owner_repo_hash() -> None:
    assert _parse_pr_ref("acme/web#42", None) == "acme/web#42"


def test_parse_pr_ref_bare_number_with_remote() -> None:
    assert _parse_pr_ref("#42", "git@github.com:acme/web.git") == "acme/web#42"


def test_parse_pr_ref_bare_number_no_remote() -> None:
    assert _parse_pr_ref("#42", None) == "#42"


# ---------------------------------------------------------------------------
# _best_pr_for_session
# ---------------------------------------------------------------------------


def test_best_pr_picks_closest_to_session_end() -> None:
    s = _session()
    pr_close = _pr(number=1, created_offset_hours=0.1)
    pr_far = _pr(number=2, created_offset_hours=5.0)
    result = _best_pr_for_session(s, [pr_close, pr_far])
    assert result is not None
    assert result["number"] == 1


def test_best_pr_returns_none_for_empty_list() -> None:
    assert _best_pr_for_session(_session(), []) is None


def test_best_pr_handles_malformed_created_at() -> None:
    s = _session()
    pr = {"number": 9, "state": "open", "createdAt": "not-a-date", "url": ""}
    assert _best_pr_for_session(s, [pr]) is None


def test_best_pr_handles_utc_timezone() -> None:
    s = _session()
    pr = _pr(number=7, created_offset_hours=0.25)
    result = _best_pr_for_session(s, [pr])
    assert result is not None
    assert result["number"] == 7


# ---------------------------------------------------------------------------
# fetch_prs_for_branch
# ---------------------------------------------------------------------------


def test_fetch_prs_for_branch_returns_list() -> None:
    prs = [_pr(number=1), _pr(number=2, state="open")]
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(prs)
    with patch("halyard.outcomes.subprocess.run", return_value=mock_result):
        result = fetch_prs_for_branch("main", None)
    assert len(result) == 2
    assert result[0]["number"] == 1


def test_fetch_prs_for_branch_returns_empty_on_nonzero() -> None:
    mock_result = MagicMock()
    mock_result.returncode = 1
    with patch("halyard.outcomes.subprocess.run", return_value=mock_result):
        assert fetch_prs_for_branch("main", None) == []


def test_fetch_prs_for_branch_returns_empty_on_oserror() -> None:
    with patch("halyard.outcomes.subprocess.run", side_effect=OSError):
        assert fetch_prs_for_branch("main", None) == []


def test_fetch_prs_for_branch_passes_repo_when_remote_given() -> None:
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "[]"
    with patch("halyard.outcomes.subprocess.run", return_value=mock_result) as mock_run:
        fetch_prs_for_branch("feature/x", "git@github.com:acme/web.git")
    args = mock_run.call_args[0][0]
    assert "--repo" in args
    assert "acme/web" in args


# ---------------------------------------------------------------------------
# outcome_report
# ---------------------------------------------------------------------------


def test_outcome_report_buckets_merged() -> None:
    sessions = [_session(pr_state="merged"), _session(pr_state="merged")]
    buckets = outcome_report(sessions)
    merged = next(b for b in buckets if "merged" in b.label.lower() or "shipped" in b.label.lower())
    assert merged.session_count == 2


def test_outcome_report_buckets_open() -> None:
    sessions = [_session(pr_state="open")]
    buckets = outcome_report(sessions)
    open_b = next(b for b in buckets if "open" in b.label.lower() or "in-flight" in b.label.lower())
    assert open_b.session_count == 1


def test_outcome_report_buckets_closed() -> None:
    sessions = [_session(pr_state="closed")]
    buckets = outcome_report(sessions)
    closed = next(
        b for b in buckets if "closed" in b.label.lower() or "abandoned" in b.label.lower()
    )
    assert closed.session_count == 1


def test_outcome_report_buckets_none() -> None:
    sessions = [_session(pr_state="none")]
    buckets = outcome_report(sessions)
    no_pr = next(b for b in buckets if "no pr" in b.label.lower() or b.label == "No PR detected")
    assert no_pr.session_count == 1


def test_outcome_report_unsynced_for_null_pr_state() -> None:
    sessions = [_session(pr_state=None, branch="feature/x")]
    buckets = outcome_report(sessions)
    unsynced = next(b for b in buckets if "sync" in b.label.lower())
    assert unsynced.session_count == 1


def test_outcome_report_sums_cost() -> None:
    sessions = [
        AiSession(
            start=_START,
            end=_END,
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.05,
            pr_state="merged",
        ),
        AiSession(
            start=_START,
            end=_END,
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.03,
            pr_state="merged",
        ),
    ]
    buckets = outcome_report(sessions)
    merged = next(b for b in buckets if "shipped" in b.label.lower() or "merged" in b.label.lower())
    assert abs(merged.total_cost - 0.08) < 1e-9


def test_outcome_report_since_filter() -> None:
    old = _session(
        start=datetime(2026, 1, 1, 10, 0), end=datetime(2026, 1, 1, 11, 0), pr_state="merged"
    )
    recent = _session(pr_state="merged")
    buckets = outcome_report([old, recent], since=date(2026, 5, 1))
    merged = next(b for b in buckets if "shipped" in b.label.lower() or "merged" in b.label.lower())
    assert merged.session_count == 1


def test_outcome_report_project_filter() -> None:
    s1 = _session(pr_state="merged", project="acme:web")
    s2 = _session(pr_state="merged", project="acme:api")
    buckets = outcome_report([s1, s2], project_slug="acme:web")
    merged = next(b for b in buckets if "shipped" in b.label.lower() or "merged" in b.label.lower())
    assert merged.session_count == 1


def test_outcome_report_returns_five_buckets() -> None:
    assert len(outcome_report([])) == 5


def test_outcome_report_trust_captured_for_resolved() -> None:
    sessions = [_session(pr_state="merged")]
    buckets = outcome_report(sessions)
    merged = next(b for b in buckets if "shipped" in b.label.lower() or "merged" in b.label.lower())
    assert merged.trust == "captured"


def test_outcome_report_trust_none_for_unsynced() -> None:
    sessions = [_session(pr_state=None)]
    buckets = outcome_report(sessions)
    unsynced = next(b for b in buckets if "sync" in b.label.lower())
    assert unsynced.trust is None


# ---------------------------------------------------------------------------
# resolve_sessions — write_amendment path (mocked db)
# ---------------------------------------------------------------------------


def _make_sessions_with_log(
    project: Path,
    branch: str = "feature/auth",
    num: int = 1,
) -> list[AiSession]:
    """Write `num` session lines to the project log and return parsed sessions."""
    from halyard.ai_log import append_session

    sessions = []
    for i in range(num):
        s = AiSession(
            start=datetime(2026, 5, 1, 10 + i, 0),
            end=datetime(2026, 5, 1, 11 + i, 0),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
            branch=branch,
        )
        append_session(project, s)
        sessions.append(s)
    return sessions


def test_resolve_sessions_dry_run_no_amendment(tmp_path: Path) -> None:
    project = _halyard_project(tmp_path)
    sessions = _make_sessions_with_log(project)
    prs = [_pr(number=10, state="merged")]

    with (
        patch("halyard.outcomes.fetch_prs_for_branch", return_value=prs),
        patch("halyard.git_context.current_remote", return_value=None),
        patch("halyard.db.get_db", return_value=_mem_db()),
    ):
        results = resolve_sessions(project, sessions, dry_run=True)

    assert len(results) == 1
    assert results[0].pr_state == "merged"
    # No amendment appended in dry_run
    log = (project / "ai-sessions.log").read_text()
    assert "\na " not in log


def test_resolve_sessions_returns_none_pr_when_no_prs(tmp_path: Path) -> None:
    project = _halyard_project(tmp_path)
    sessions = _make_sessions_with_log(project)

    with (
        patch("halyard.outcomes.fetch_prs_for_branch", return_value=[]),
        patch("halyard.git_context.current_remote", return_value=None),
        patch("halyard.db.get_db", return_value=_mem_db()),
    ):
        results = resolve_sessions(project, sessions)

    assert results[0].pr_ref is None
    assert results[0].pr_state == "none"


def test_resolve_sessions_skips_already_resolved_without_force(tmp_path: Path) -> None:
    project = _halyard_project(tmp_path)
    sessions = _make_sessions_with_log(project)
    # Mark already resolved
    sessions[0].pr_ref = "acme/web#1"
    sessions[0].pr_state = "merged"

    with patch("halyard.outcomes.fetch_prs_for_branch") as mock_fetch:
        results = resolve_sessions(project, sessions)

    mock_fetch.assert_not_called()
    assert results == []


def test_resolve_sessions_force_re_resolves(tmp_path: Path) -> None:
    project = _halyard_project(tmp_path)
    sessions = _make_sessions_with_log(project)
    sessions[0].pr_ref = "acme/web#1"
    sessions[0].pr_state = "merged"

    with (
        patch("halyard.outcomes.fetch_prs_for_branch", return_value=[]),
        patch("halyard.git_context.current_remote", return_value=None),
        patch("halyard.db.get_db", return_value=_mem_db()),
    ):
        results = resolve_sessions(project, sessions, force=True)

    assert len(results) == 1


def test_resolve_sessions_skips_no_branch(tmp_path: Path) -> None:
    project = _halyard_project(tmp_path)
    sessions = _make_sessions_with_log(project, branch="")
    sessions[0].branch = None

    with patch("halyard.outcomes.fetch_prs_for_branch") as mock_fetch:
        results = resolve_sessions(project, sessions)

    mock_fetch.assert_not_called()
    assert results == []


def test_resolve_sessions_groups_by_branch(tmp_path: Path) -> None:
    project = _halyard_project(tmp_path)
    s1 = _make_sessions_with_log(project, branch="feat/a")[0]
    s2 = _make_sessions_with_log(project, branch="feat/b")[0]

    with (
        patch("halyard.outcomes.fetch_prs_for_branch", return_value=[]) as mock_fetch,
        patch("halyard.git_context.current_remote", return_value=None),
        patch("halyard.db.get_db", return_value=_mem_db()),
    ):
        resolve_sessions(project, [s1, s2])

    # One gh call per unique branch
    assert mock_fetch.call_count == 2


def test_resolve_sessions_writes_amendment(tmp_path: Path) -> None:
    project = _halyard_project(tmp_path)
    sessions = _make_sessions_with_log(project)
    prs = [_pr(number=5, state="merged")]

    with (
        patch("halyard.outcomes.fetch_prs_for_branch", return_value=prs),
        patch("halyard.git_context.current_remote", return_value="git@github.com:acme/web.git"),
        patch("halyard.db.get_db", return_value=_mem_db()),
    ):
        resolve_sessions(project, sessions)

    log = (project / "ai-sessions.log").read_text()
    amendment_lines = [ln for ln in log.splitlines() if ln.startswith("a ")]
    assert len(amendment_lines) == 1
    assert "pr_ref=acme/web#5" in amendment_lines[0]
    assert "pr_state=merged" in amendment_lines[0]
