"""v2.50 — Halyard MCP server (SDK-free: tests the data helpers)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard import mcp_server
from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.cli import app

_NOW = datetime.now()


def _proj(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (p / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")
    return p


def _s(
    start,
    tool="claude-code",
    model="claude-opus-4-7",
    cost=1.0,
    project="acme:web",
    pr_state=None,
    inp=100,
    out=50,
):
    return AiSession(
        start=start,
        end=start + timedelta(minutes=3),
        tool=tool,
        model=model,
        input_tokens=inp,
        output_tokens=out,
        cost_usd=cost,
        project=project,
        pr_state=pr_state,
    )


@pytest.fixture
def two_projects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    a = _proj(tmp_path / "a")
    b = _proj(tmp_path / "b")
    base = _NOW - timedelta(days=2)
    append_session(a, _s(base, project="acme:web", cost=2.0, pr_state="merged"))
    append_session(
        a,
        _s(
            base + timedelta(hours=1),
            tool="cursor",
            model="claude-3.5-sonnet",
            project="acme:web",
            cost=0.0,
        ),
    )
    append_session(
        b, _s(base + timedelta(hours=2), project="kormilo:halyard", cost=5.0, pr_state="open")
    )
    append_session(b, _s(base + timedelta(hours=3), project=None, cost=0.5))  # adrift
    monkeypatch.setattr(mcp_server, "aggregate_session_dirs", lambda: [a, b])
    return a, b


def test_work_summary(two_projects) -> None:
    r = mcp_server._work_summary("30d")
    assert r["sessions"] == 4
    assert r["total_cost_usd"] == pytest.approx(7.5)
    assert r["by_tool"]["claude-code"] == 3 and r["by_tool"]["cursor"] == 1
    assert r["adrift_sessions"] == 1
    assert r["adrift_pct"] == pytest.approx(25.0)
    assert r["outcomes"]["merged"] == 1 and r["outcomes"]["open"] == 1
    assert r["top_projects"][0]["project"] == "kormilo:halyard"


def test_sessions_filter(two_projects) -> None:
    alls = mcp_server._sessions(limit=10)
    assert len(alls) == 4
    cur = mcp_server._sessions(tool="cursor")
    assert len(cur) == 1 and cur[0]["tool"] == "cursor"
    one = mcp_server._sessions(project="kormilo:halyard")
    assert len(one) == 1 and one[0]["project"] == "kormilo:halyard"
    # metadata only — never prompt/code fields
    assert set(alls[0]) == {
        "start",
        "end",
        "tool",
        "model",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "project",
        "branch",
        "api_seconds",
        "tool_seconds",
    }


def test_spend_in_range(two_projects) -> None:
    start = (_NOW - timedelta(days=5)).isoformat()
    end = _NOW.isoformat()
    r = mcp_server._spend_in_range(start, end, api_only=False)
    assert r["usd"] == pytest.approx(7.5)
    assert r["sessions"] == 4


def test_project_breakdown_and_cost_by_model(two_projects) -> None:
    pb = mcp_server._project_breakdown("30d")
    by = {x["project"]: x for x in pb}
    assert by["kormilo:halyard"]["cost_usd"] == pytest.approx(5.0)
    assert by["(unattributed)"]["sessions"] == 1
    cm = mcp_server._cost_by_model("30d")
    assert any(m["model"] == "claude-opus-4-7" for m in cm)


def test_outcomes_status(two_projects) -> None:
    o = mcp_server._outcomes_status("30d")
    assert o["merged"] == 1
    assert o["open"] == 1
    assert o["not_synced"] == 2  # the two with pr_state=None


def test_build_server_requires_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    # Importing halyard.mcp_server must NOT require the SDK; only
    # build_server() does. With the SDK absent, `halyard mcp` exits 1
    # with an actionable message (no traceback).
    import builtins

    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "mcp" or name.startswith("mcp."):
            raise ModuleNotFoundError("No module named 'mcp'")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    res = CliRunner().invoke(app, ["mcp"])
    assert res.exit_code == 1
    assert "halyard[mcp]" in res.output
