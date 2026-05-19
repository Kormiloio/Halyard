"""v3.4 — MCP-server usage inventory.

Spec: openspec/changes/v3.4-mcp-inventory/specs/mcp-inventory.md
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import halyard.db as db
from halyard.ai_log import AiSession
from halyard.collectors.claude_code import _read_from_transcript
from halyard.dashboard import _leverage_panel
from halyard.leverage import render_mcp_phrase, summarize_mcp
from halyard.mcp_inventory import (
    MCP_SERVER_ALLOWLIST,
    extract_mcp_server,
    reduce_mcp,
)
from halyard.tui.widgets.leverage_pane import LeveragePane

_NOW = datetime(2026, 5, 18, 12)


def _sess(used: int | None, names: str | None, days: int = 1) -> AiSession:
    s = AiSession(
        start=_NOW - timedelta(days=days),
        end=_NOW - timedelta(days=days) + timedelta(hours=1),
        tool="claude-code",
        model="m",
        input_tokens=1,
        output_tokens=1,
        cost_usd=1.0,
        project="acme:web",
        pr_state="merged",
        pr_ref="a/b#1",
    )
    s.mcp_servers_used = used
    s.mcp_server_names = names
    return s


# --- §1 privacy primitive -------------------------------------------------


def test_extract_basic() -> None:
    assert extract_mcp_server("mcp__github__create_issue") == "github"


def test_extract_server_with_tool_having_double_underscores() -> None:
    # only the FIRST __ after the prefix delimits the server
    assert extract_mcp_server("mcp__github__some__deep__tool") == "github"


def test_extract_non_mcp_returns_none() -> None:
    assert extract_mcp_server("Bash") is None
    assert extract_mcp_server("Read") is None
    assert extract_mcp_server("str_replace_editor") is None


def test_extract_malformed_fail_closed() -> None:
    assert extract_mcp_server("mcp__") is None  # no server, no tool
    assert extract_mcp_server("mcp____tool") is None  # empty server
    assert extract_mcp_server("mcp__github") is None  # no tool delimiter
    assert extract_mcp_server("") is None
    assert extract_mcp_server(None) is None
    assert extract_mcp_server("xmcp__github__t") is None  # not anchored


def test_reduce_empty_is_none_not_zero() -> None:
    assert reduce_mcp(set()) == (None, None)


def test_reduce_counts_all_names_only_allowlisted() -> None:
    count, names = reduce_mcp({"github", "filesystem", "acme_secret_internal"})
    assert count == 3  # all three counted
    assert names == "filesystem,github"  # sorted; the secret one NOT named


def test_reduce_all_non_allowlisted_counts_but_no_names() -> None:
    count, names = reduce_mcp({"acme_internal", "corp_billing"})
    assert count == 2
    assert names is None  # counted, never named


def test_reduce_names_sorted_for_byte_stability() -> None:
    _, names = reduce_mcp({"slack", "github", "fetch"})
    assert names == "fetch,github,slack"


def test_allowlist_is_frozenset_and_public_only() -> None:
    assert isinstance(MCP_SERVER_ALLOWLIST, frozenset)
    assert "github" in MCP_SERVER_ALLOWLIST
    # no user/company-specific entries snuck in
    assert not any("acme" in s or "internal" in s for s in MCP_SERVER_ALLOWLIST)


# --- §2 schema + log ------------------------------------------------------


def test_round_trip_and_byte_stable_empty() -> None:
    s = _sess(3, "filesystem,github")
    line = s.to_log_line()
    assert "mcp_servers_used=3" in line
    assert "mcp_server_names=filesystem,github" in line
    r = AiSession.from_log_line(line)
    assert r is not None
    assert r.mcp_servers_used == 3
    assert r.mcp_server_names == "filesystem,github"
    assert r.to_log_line() == line  # byte-stable
    empty = AiSession(
        start=_NOW,
        end=_NOW,
        tool="t",
        model="m",
        input_tokens=0,
        output_tokens=0,
        cost_usd=0,
    )
    assert "mcp_" not in empty.to_log_line()  # v2.75 path unaffected


def test_migration_v5_to_v6_additive_idempotent() -> None:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("CREATE TABLE sessions(id TEXT); PRAGMA user_version=5;")
    c.commit()
    sql = dict(db._MIGRATIONS)[5]
    db._apply_migration(c, sql)
    db._apply_migration(c, sql)  # idempotent self-heal must not raise
    cols = {row[1] for row in c.execute("PRAGMA table_info(sessions)")}
    assert {"mcp_servers_used", "mcp_server_names"} <= cols
    assert db._CURRENT_VERSION == 6


# --- §3 collector wiring (Claude Code) ------------------------------------


def _transcript(tmp: Path, names: list[str]) -> str:
    blocks = [{"type": "tool_use", "name": n} for n in names]
    rows = [
        {
            "type": "assistant",
            "timestamp": "2026-05-18T09:00:00Z",
            "message": {
                "model": "m",
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "content": blocks,
            },
        },
        {
            "type": "user",
            "timestamp": "2026-05-18T09:01:00Z",
            "message": {"content": [{"type": "tool_result", "is_error": False}]},
        },
    ]
    p = tmp / "t.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return str(p)


def test_collector_counts_all_but_names_allowlisted_only() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _transcript(
            Path(d),
            [
                "mcp__github__create_issue",
                "mcp__acme_secret_internal__charge",  # sensitive → counted, not named
                "Bash",  # non-MCP → ignored
            ],
        )
        ts = _read_from_transcript(path, since=None)
    assert ts.tool_calls == 3
    assert ts.mcp_servers_used == 2  # github + secret
    assert ts.mcp_server_names == "github"  # secret never named


def test_collector_no_mcp_leaves_fields_none() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _transcript(Path(d), ["Bash", "Read"])
        ts = _read_from_transcript(path, since=None)
    assert ts.tool_calls == 2
    assert ts.mcp_servers_used is None  # honest absence, not 0
    assert ts.mcp_server_names is None


# --- §4 surface parity + absent path --------------------------------------


def test_summarize_mcp_peak_session() -> None:
    m = summarize_mcp([_sess(4, "filesystem,github"), _sess(2, "github")], _NOW)
    assert m is not None
    assert m.peak_servers == 4
    assert m.named == ("filesystem", "github")
    assert render_mcp_phrase(m) == "MCP: 4 servers (filesystem, github +2)"


def test_summarize_mcp_none_when_no_data() -> None:
    plain = AiSession(
        start=_NOW - timedelta(days=1),
        end=_NOW,
        tool="t",
        model="m",
        input_tokens=1,
        output_tokens=1,
        cost_usd=1.0,
        project="p",
        pr_state="merged",
        pr_ref="a/b#9",
    )
    assert summarize_mcp([plain], _NOW) is None


def test_render_phrase_all_non_allowlisted() -> None:
    m = summarize_mcp([_sess(3, None)], _NOW)
    assert m is not None
    assert render_mcp_phrase(m) == "MCP: 3 servers (none on allowlist)"


def test_web_tui_parity_and_absent_identical() -> None:
    sessions = [_sess(4, "filesystem,github"), _sess(1, "github")]
    phrase = render_mcp_phrase(summarize_mcp(sessions, _NOW))  # type: ignore[arg-type]
    html = _leverage_panel(sessions, _NOW)
    pane = LeveragePane()
    pane.render_sessions(sessions, _NOW)
    assert phrase in html and "leverage-mcp" in html
    assert phrase in pane.last_rendered_text  # web == TUI
    # absent → no MCP line on either surface (v3.2-identical)
    none = [
        AiSession(
            start=_NOW - timedelta(days=1),
            end=_NOW,
            tool="t",
            model="m",
            input_tokens=1,
            output_tokens=1,
            cost_usd=1.0,
            project="p",
            pr_state="merged",
            pr_ref="a/b#9",
        )
    ]
    assert "leverage-mcp" not in _leverage_panel(none, _NOW)
    p2 = LeveragePane()
    p2.render_sessions(none, _NOW)
    assert "MCP:" not in p2.last_rendered_text


def test_partial_rollout_is_honest_no_zero() -> None:
    # a non-instrumented collector's session (fields None) must never
    # imply "0 servers" — it simply doesn't contribute / show a line.
    non_instrumented = AiSession(
        start=_NOW - timedelta(days=1),
        end=_NOW,
        tool="cursor",
        model="m",
        input_tokens=1,
        output_tokens=1,
        cost_usd=1.0,
        project="p",
        pr_state="merged",
        pr_ref="a/b#3",
    )
    assert summarize_mcp([non_instrumented], _NOW) is None
    assert "MCP:" not in _leverage_panel([non_instrumented], _NOW)


# --- §5.6 privacy fuzz ----------------------------------------------------


def test_privacy_sensitive_server_and_args_never_surface() -> None:
    secret = "acme_secret_billing_prod"
    with tempfile.TemporaryDirectory() as d:
        path = _transcript(
            Path(d),
            [
                f"mcp__{secret}__charge_customer",
                "mcp__github__pr",
            ],
        )
        ts = _read_from_transcript(path, since=None)
    s = _sess(ts.mcp_servers_used, ts.mcp_server_names)
    surfaces = [
        s.to_log_line(),
        _leverage_panel([s], _NOW),
        render_mcp_phrase(summarize_mcp([s], _NOW)),  # type: ignore[arg-type]
    ]
    pane = LeveragePane()
    pane.render_sessions([s], _NOW)
    surfaces.append(pane.last_rendered_text)
    for out in surfaces:
        assert secret not in out
        assert "charge_customer" not in out  # tool segment never retained
        assert "mcp__" not in out  # raw prefixed name never retained
    # the sensitive server still COUNTED (honest), just never named
    assert s.mcp_servers_used == 2
    assert s.mcp_server_names == "github"
