"""Regression tests for v5.17/B14 — mcp_server_names CSV corruption on db sync.

`_sync_sessions` previously wrote ``",".join(session.mcp_server_names)`` into
the cache. Because ``mcp_server_names`` is already a CSV *string* (str | None),
``join`` iterated it character-by-character, so "filesystem,github" was cached
as "f,i,l,e,s,y,s,t,e,m,,,g,i,t,h,u,b". On read-back, the leverage path's
``split(",")`` then yielded single-character "server names".

These tests prove the CSV now round-trips intact (multi-server input) and that
a single-server / empty input still behaves (guard against over-correction).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from halyard.db import get_db, get_recent_branch_activity, sync_all
from halyard.leverage import summarize_mcp


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect cache, registry, and hub so tests never touch real user data."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    monkeypatch.setattr("halyard.registry.REGISTRY_PATH", tmp_path / ".halyard" / "projects")
    monkeypatch.setattr("halyard.hub.find_hub", lambda: None)


def _setup_project(tmp_path: Path, session_line: str) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\nname = 'Test'\n", encoding="utf-8")
    (tmp_path / "ai-sessions.log").write_text("; header\n" + session_line + "\n", encoding="utf-8")


def _session_line(*, mcp_count: int, mcp_names: str, remote: str, branch: str) -> str:
    return (
        "s 2026-01-01T09:00:00 2026-01-01T09:30:00 claude-code claude-sonnet-4-6 "
        "10000 2000 0.0850 project=test:proj "
        f"remote={remote} branch={branch} "
        f"mcp_servers_used={mcp_count} mcp_server_names={mcp_names}"
    )


def _stored_csv(tmp_path: Path) -> str | None:
    conn = get_db()
    try:
        row = conn.execute("SELECT mcp_server_names FROM sessions LIMIT 1").fetchone()
    finally:
        conn.close()
    return None if row is None else row["mcp_server_names"]


def test_multi_server_csv_roundtrips_intact(tmp_path: Path) -> None:
    """Malicious-of-old case: a two-server CSV must NOT be char-split."""
    _setup_project(
        tmp_path,
        _session_line(
            mcp_count=2,
            mcp_names="filesystem,github",
            remote="git@github.com:acme/widgets.git",
            branch="main",
        ),
    )

    assert sync_all().sessions_added == 1

    # The cache column holds the exact CSV — not "f,i,l,e,...".
    assert _stored_csv(tmp_path) == "filesystem,github"

    # Read-back via the AiSession reconstruction path.
    rows = get_recent_branch_activity("git@github.com:acme/widgets.git", "main")
    assert len(rows) == 1
    assert rows[0].mcp_server_names == "filesystem,github"

    # The leverage surface resolves the real server names, not single chars.
    rollup = summarize_mcp(rows, now=datetime(2026, 1, 1, 12, 0, 0))
    assert rollup is not None
    assert rollup.named == ("filesystem", "github")


def test_single_server_still_works(tmp_path: Path) -> None:
    """Benign case: a single-server name must round-trip unchanged (no
    over-restriction from the fix)."""
    _setup_project(
        tmp_path,
        _session_line(
            mcp_count=1,
            mcp_names="github",
            remote="git@github.com:acme/widgets.git",
            branch="main",
        ),
    )

    assert sync_all().sessions_added == 1
    assert _stored_csv(tmp_path) == "github"

    rows = get_recent_branch_activity("git@github.com:acme/widgets.git", "main")
    assert rows[0].mcp_server_names == "github"

    rollup = summarize_mcp(rows, now=datetime(2026, 1, 1, 12, 0, 0))
    assert rollup is not None
    assert rollup.named == ("github",)


def test_no_mcp_usage_stores_empty_not_corrupted(tmp_path: Path) -> None:
    """A session with no MCP fields stores an empty string (the None case),
    and leverage reports no MCP rollup rather than phantom servers."""
    _setup_project(
        tmp_path,
        (
            "s 2026-01-01T09:00:00 2026-01-01T09:30:00 claude-code claude-sonnet-4-6 "
            "10000 2000 0.0850 project=test:proj "
            "remote=git@github.com:acme/widgets.git branch=main"
        ),
    )

    assert sync_all().sessions_added == 1
    assert _stored_csv(tmp_path) == ""

    rows = get_recent_branch_activity("git@github.com:acme/widgets.git", "main")
    assert rows[0].mcp_server_names in ("", None)
    # No mcp_servers_used => no rollup at all.
    assert summarize_mcp(rows, now=datetime(2026, 1, 1, 12, 0, 0)) is None
