"""v2.73 — sortable dashboard tables (markup/no-JS contract)."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.dashboard import _session_sev, _stbl, render_dashboard


def _init(tmp: Path) -> None:
    (tmp / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (tmp / "time.timeclock").write_text("; time\n", encoding="utf-8")
    (tmp / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")


def _sess(**kw: object) -> AiSession:
    base: dict = {
        "start": datetime(2026, 5, 7, 10, 0),
        "end": datetime(2026, 5, 7, 10, 30),
        "tool": "claude-code",
        "model": "claude-sonnet-4-6",
        "input_tokens": 1000,
        "output_tokens": 500,
        "cost_usd": 0.01,
        "project": "acme:auth",
    }
    base.update(kw)
    return AiSession(**base)


def test_stbl_helper_shape() -> None:
    out = _stbl("recent-sessions", "m,x,n", "usage-models-rows")
    assert "data-sortable" in out
    assert "data-sort-key='recent-sessions'" in out
    assert "data-cols='m,x,n'" in out
    assert "class='usage-models-rows'" in out
    # no-cls variant omits class entirely
    assert "class=" not in _stbl("models", "t,n")


def test_session_sev_ranks() -> None:
    assert _session_sev(_sess(tool_errors=3)) == 2
    assert _session_sev(_sess(test_status="fail")) == 2
    assert _session_sev(_sess(tokens_available=False)) == 1
    assert _session_sev(_sess(interaction_data_available=False)) == 1
    assert _session_sev(_sess(tokens_available=True)) == 0


def test_sortable_tables_present_with_unique_keys(tmp_path: Path) -> None:
    _init(tmp_path)
    append_session(tmp_path, _sess())
    html = render_dashboard(tmp_path)

    keys = re.findall(r"data-sort-key='([^']+)'", html)
    # default view tables (the Usage-Analytics "Models" tab table
    # `usage-models` is tab-gated and not in the default render)
    assert "recent-sessions" in keys
    assert "models" in keys
    assert "tools" in keys
    assert "ledger" in keys
    # every sortable table carries a key and they are unique
    assert keys, "no sortable tables emitted"
    assert len(keys) == len(set(keys)), f"duplicate sort keys: {keys}"
    # the client sorter script is wired in
    assert "table[data-sortable]" in html
    assert "halyard.sort." in html


def test_recent_sessions_sort_vals(tmp_path: Path) -> None:
    _init(tmp_path)
    append_session(tmp_path, _sess(input_tokens=1000, output_tokens=500))
    html = render_dashboard(tmp_path)

    # tokens column carries a numeric sort key (sum), not the "1,000 / 500" label
    assert "data-sort-val='1500'" in html
    # health column carries a severity rank, never the glyph text
    assert re.search(r"data-sev='[012]'", html)
    # the recent-sessions table declares its column kinds
    assert "data-cols='m,x,x,x,x,n,n,s'" in html


def test_no_js_baseline_unchanged(tmp_path: Path) -> None:
    """Additive attributes only — server still emits the rows, in
    server order, with the same visible text."""
    _init(tmp_path)
    append_session(tmp_path, _sess(model="claude-sonnet-4-6", project="acme:auth"))
    html = render_dashboard(tmp_path)

    # The row content the server rendered is still there verbatim.
    assert "acme:auth" in html
    assert "claude-sonnet-4-6" in html
    assert "1,000 / 500" in html
    # data-sortable is an attribute on <table>, never replaces <tbody>
    # rows: the table still has a thead + tbody structure.
    assert "<thead>" in html and "<tbody>" in html


def test_sortable_headers_get_an_affordance_icon(tmp_path: Path) -> None:
    """Sortable columns must look sortable: the CSS + script provide a
    small indicator (neutral ⇅, ▲/▼ when active)."""
    _init(tmp_path)
    append_session(tmp_path, _sess())
    html = render_dashboard(tmp_path)
    assert ".sort-ind" in html  # CSS rule shipped
    assert "h-sortable" in html  # hover/cursor affordance class
    assert "sort-ind" in html and "⇅" in html  # script injects the icon
    assert "▲" in html and "▼" in html  # active-direction glyphs


def test_budget_panel_is_not_marked_sortable(tmp_path: Path) -> None:
    """Budget is card-based, not a <table> — deliberately dropped from
    the sortable set rather than shipping a broken card sorter."""
    _init(tmp_path)
    append_session(tmp_path, _sess())
    html = render_dashboard(tmp_path)
    keys = re.findall(r"data-sort-key='([^']+)'", html)
    assert "budget" not in keys
