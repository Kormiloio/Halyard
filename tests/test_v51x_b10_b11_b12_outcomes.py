"""Regression tests for v5.1x outcomes blockers B10, B11, B12.

B10 — GitHub API endpoint injection + append-log injection:
  * `_is_safe_repo` must reject a traversal slug like ``a/b/../../user/keys``
    before it reaches a ``gh api repos/{repo}/...`` path, while still
    accepting a normal ``owner/repo`` slug.
  * `_write_amendment` must route field values through ``_safe_field`` so a
    pr_ref containing whitespace / ``=`` / a newline cannot forge extra
    fields or inject a second append-only record.

B11 — cached transient failure poisons attribution:
  * `fetch_prs_for_branch` returns None (not []) on failure, and
    `resolve_sessions` must NOT cache a failed fetch, while a genuine empty
    result IS cached.

B12 — merged PR mis-bucketed as Abandoned:
  * `_fetch_pr_by_ref` must map a merged PR (``merged``/``mergedAt`` set,
    REST ``state`` == "closed") to ``state`` == "merged", while a genuinely
    closed (unmerged) PR stays "closed".
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time

from halyard.ai_log import AiSession, append_session
from halyard.outcomes import (
    ResolutionResult,
    _fetch_pr_by_ref,
    _is_safe_repo,
    _write_amendment,
    fetch_prs_for_branch,
    gh_pr_inline_comment_count,
    resolve_sessions,
)


@pytest.fixture(autouse=True)
def _no_real_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default to "gh not installed" so resolution tests never shell out."""

    def _no_gh(*_a: object, **_k: object) -> None:
        raise FileNotFoundError("gh not available in tests")

    monkeypatch.setattr("halyard.outcomes.subprocess.run", _no_gh)


@pytest.fixture(autouse=True)
def _freeze_to_may_2026():
    # Pin the wall clock so the May-2026 session fixtures fall inside the
    # default 30-day resolution cutoff.
    with freeze_time("2026-05-15 12:00:00"):
        yield


def _mem_db() -> sqlite3.Connection:
    from halyard.db import _CREATE_SCHEMA_V1

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_CREATE_SCHEMA_V1)
    conn.commit()
    return conn


def _halyard_project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "halyard.toml").write_text("[project]\nslug = 'acme:web'\n", encoding="utf-8")
    (tmp_path / "ai-sessions.log").write_text(
        "; Halyard AI session log\n"
        "; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd>\n",
        encoding="utf-8",
    )
    return tmp_path


def _session_in_log(project: Path, branch: str = "feature/auth") -> AiSession:
    s = AiSession(
        start=datetime(2026, 5, 1, 10, 0),
        end=datetime(2026, 5, 1, 11, 0),
        tool="claude-code",
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        branch=branch,
    )
    append_session(project, s)
    return s


# ---------------------------------------------------------------------------
# B10 — repo validator (GitHub API endpoint injection)
# ---------------------------------------------------------------------------


def test_b10_repo_validator_rejects_traversal() -> None:
    # Malicious: walks the REST path to an arbitrary authenticated endpoint.
    assert _is_safe_repo("a/b/../../user/keys") is False
    assert _is_safe_repo("owner/repo/extra") is False
    assert _is_safe_repo("owner/..") is False
    assert _is_safe_repo("../repo") is False
    assert _is_safe_repo(".") is False
    assert _is_safe_repo("owner repo/x") is False  # whitespace
    assert _is_safe_repo("owner/repo;rm -rf") is False


def test_b10_repo_validator_accepts_normal_slug() -> None:
    # Benign: a plain owner/repo must still pass (guard against over-restriction).
    assert _is_safe_repo("acme/web") is True
    assert _is_safe_repo("octo-cat/My.Repo_2") is True
    assert _is_safe_repo("a/b") is True


def test_b10_fetch_pr_by_ref_blocks_traversal_repo_no_subprocess() -> None:
    # A crafted pr_ref must short-circuit BEFORE any gh api subprocess fires.
    with patch("halyard.outcomes.subprocess.run") as mock_run:
        result = _fetch_pr_by_ref("a/b/../../user/keys#1", None)
    assert result == []
    mock_run.assert_not_called()


def test_b10_inline_comment_count_blocks_traversal_repo_no_subprocess() -> None:
    with patch("halyard.outcomes.subprocess.run") as mock_run:
        result = gh_pr_inline_comment_count("a/b/../../user/keys#1", None)
    assert result is None
    mock_run.assert_not_called()


def test_b10_fetch_pr_by_ref_allows_normal_repo() -> None:
    # Benign slug reaches the subprocess and the path is the expected endpoint.
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(
        {"number": 7, "state": "open", "merged": False, "mergedAt": None, "url": "u"}
    )
    with patch("halyard.outcomes.subprocess.run", return_value=mock_result) as mock_run:
        result = _fetch_pr_by_ref("acme/web#7", None)
    assert result and result[0]["number"] == 7
    api_path = mock_run.call_args[0][0][2]
    assert api_path == "repos/acme/web/pulls/7"


# ---------------------------------------------------------------------------
# B10 — amendment field encoding (append-log injection)
# ---------------------------------------------------------------------------


def test_b10_amendment_neutralizes_injected_pr_ref(tmp_path: Path) -> None:
    project = _halyard_project(tmp_path)
    # Malicious pr_ref: spaces + '=' + newline would forge fields and inject a
    # second append-only "a <hash>" record if written verbatim.
    malicious = "acme/web#1 forged=evil\na deadbeef pr_state=merged"
    result = ResolutionResult(
        session_hash="cafebabe",
        pr_ref=malicious,
        pr_state="open",
        resolved_at="2026-05-01T11:00:00",
    )
    _write_amendment(project, result)

    log = (project / "ai-sessions.log").read_text(encoding="utf-8")
    amendment_lines = [ln for ln in log.splitlines() if ln.startswith("a ")]
    # Exactly ONE amendment record — no smuggled second "a " line.
    assert len(amendment_lines) == 1
    line = amendment_lines[0]
    # The injected newline is gone, and the value collapsed to a single token:
    # _safe_field maps whitespace and '=' to '_'.
    assert "forged=evil" not in line
    # The forged "pr_state=merged" key cannot stand alone: it is folded into
    # the sanitized pr_ref token, never written as its own key=value.
    assert "pr_ref=acme/web#1_forged_evil_a_deadbeef_pr_state_merged" in line
    # The real pr_state we passed ("open") is still its own correct field.
    assert "pr_state=open" in line


def test_b10_amendment_writes_benign_ref_unchanged(tmp_path: Path) -> None:
    project = _halyard_project(tmp_path)
    result = ResolutionResult(
        session_hash="cafebabe",
        pr_ref="acme/web#5",
        pr_state="merged",
        resolved_at="2026-05-01T11:00:00",
    )
    _write_amendment(project, result)
    log = (project / "ai-sessions.log").read_text(encoding="utf-8")
    amendment_lines = [ln for ln in log.splitlines() if ln.startswith("a ")]
    assert len(amendment_lines) == 1
    assert "pr_ref=acme/web#5" in amendment_lines[0]
    assert "pr_state=merged" in amendment_lines[0]


# ---------------------------------------------------------------------------
# B11 — transient failure must not poison the cache
# ---------------------------------------------------------------------------


def test_b11_fetch_signals_failure_as_none() -> None:
    mock_result = MagicMock()
    mock_result.returncode = 1
    with patch("halyard.outcomes.subprocess.run", return_value=mock_result):
        assert fetch_prs_for_branch("main", None) is None


def test_b11_fetch_genuine_empty_is_list() -> None:
    # Benign: a real "no PRs" result is an empty list, NOT a failure sentinel.
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "[]"
    with patch("halyard.outcomes.subprocess.run", return_value=mock_result):
        assert fetch_prs_for_branch("main", None) == []


def test_b11_transient_failure_not_cached(tmp_path: Path) -> None:
    # resolve_sessions closes its own (in-memory) conn in a finally block, so
    # rather than inspect the db after the fact we spy on _cache_set: the B11
    # contract is precisely "do not cache a failed fetch".
    project = _halyard_project(tmp_path)
    _session_in_log(project)
    sessions_loaded = _load(project)

    with (
        patch("halyard.outcomes.fetch_prs_for_branch", return_value=None),
        patch("halyard.outcomes._cache_set") as mock_cache_set,
        patch("halyard.git_context.current_remote", return_value=None),
        patch("halyard.db.get_db", return_value=_mem_db()),
    ):
        results = resolve_sessions(project, sessions_loaded)

    # A failed fetch falls through to the no-PR path for this sync...
    assert results[0].pr_state == "none"
    # ...but must NOT have written a poisoned cache entry that would freeze
    # every future session at pr_state="none" for an hour.
    mock_cache_set.assert_not_called()


def test_b11_genuine_empty_is_cached(tmp_path: Path) -> None:
    # Benign: a real empty result SHOULD be cached (the intended behavior;
    # guard against over-restriction that would refuse to cache "no PRs").
    project = _halyard_project(tmp_path)
    _session_in_log(project)
    sessions_loaded = _load(project)

    with (
        patch("halyard.outcomes.fetch_prs_for_branch", return_value=[]),
        patch("halyard.outcomes._cache_set") as mock_cache_set,
        patch("halyard.git_context.current_remote", return_value=None),
        patch("halyard.db.get_db", return_value=_mem_db()),
    ):
        results = resolve_sessions(project, sessions_loaded)

    assert results[0].pr_state == "none"
    mock_cache_set.assert_called_once()
    # The genuine empty list is what gets cached.
    assert mock_cache_set.call_args[0][2] == []


# ---------------------------------------------------------------------------
# B12 — merged PR must not be mis-bucketed as Abandoned
# ---------------------------------------------------------------------------


def _api_result(payload: dict) -> MagicMock:  # type: ignore[type-arg]
    m = MagicMock()
    m.returncode = 0
    m.stdout = json.dumps(payload)
    return m


def test_b12_merged_pr_maps_to_merged_not_closed() -> None:
    # The gh REST API returns state="closed" for a merged PR; the merged-ness
    # is only in .merged / .merged_at. The mapped result must be "merged".
    payload = {
        "number": 42,
        "state": "closed",
        "merged": True,
        "mergedAt": "2026-05-01T12:00:00Z",
        "url": "https://github.com/acme/web/pull/42",
    }
    with patch("halyard.outcomes.subprocess.run", return_value=_api_result(payload)):
        prs = _fetch_pr_by_ref("acme/web#42", None)
    assert prs and prs[0]["state"] == "merged"


def test_b12_merged_via_merged_at_only() -> None:
    # Defensive: even if .merged is absent/false, a non-null mergedAt means
    # the PR was merged.
    payload = {
        "number": 43,
        "state": "closed",
        "merged": False,
        "mergedAt": "2026-05-02T09:30:00Z",
        "url": "u",
    }
    with patch("halyard.outcomes.subprocess.run", return_value=_api_result(payload)):
        prs = _fetch_pr_by_ref("acme/web#43", None)
    assert prs and prs[0]["state"] == "merged"


def test_b12_genuinely_closed_pr_stays_closed() -> None:
    # Benign: a PR closed WITHOUT merging stays "closed" (Abandoned bucket).
    # Guard against over-mapping every closed PR to merged.
    payload = {
        "number": 44,
        "state": "closed",
        "merged": False,
        "mergedAt": None,
        "url": "u",
    }
    with patch("halyard.outcomes.subprocess.run", return_value=_api_result(payload)):
        prs = _fetch_pr_by_ref("acme/web#44", None)
    assert prs and prs[0]["state"] == "closed"


def test_b12_open_pr_stays_open() -> None:
    payload = {
        "number": 45,
        "state": "open",
        "merged": False,
        "mergedAt": None,
        "url": "u",
    }
    with patch("halyard.outcomes.subprocess.run", return_value=_api_result(payload)):
        prs = _fetch_pr_by_ref("acme/web#45", None)
    assert prs and prs[0]["state"] == "open"


def _load(project: Path) -> list[AiSession]:
    from halyard.ai_log import parse_sessions

    return parse_sessions(project)
