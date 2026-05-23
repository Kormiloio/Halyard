"""v2.69 — machine-readable JSON output.

Audit found `--json` already existed inconsistently (doctor/health/
usage/log/outcome); report/budget/status/evidence were the gaps.
These lock the unified `jsonio` seam, the new coverage, the clean
machine contract (no Rich markup, parseable errors), and that the
v2.68 evidence digest stays markdown-only.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.cli import app

runner = CliRunner()


def _init(tmp: Path) -> None:
    (tmp / "halyard.toml").write_text("[business]\nname = 'Acme'\n")
    (tmp / "time.timeclock").write_text("; time\n")
    (tmp / AI_LOG_FILENAME).write_text(HEADER)


def _add(tmp: Path) -> None:
    append_session(
        tmp,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0123,
            project="acme:auth",
            user_message_count=2,
            assistant_message_count=3,
        ),
    )


def _json_out(args: list[str], tmp: Path, monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.chdir(tmp)
    res = runner.invoke(app, args)
    assert res.exit_code == 0, res.output
    # Clean machine contract: parseable, no Rich markup tags leaked.
    assert "[bold" not in res.output and "[/]" not in res.output
    return json.loads(res.output)


# 1. coverage + clean contract ---------------------------------------------


def test_report_budget_status_usage_evidence_health_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init(tmp_path)
    _add(tmp_path)

    rep = _json_out(["report", "--all", "--json"], tmp_path, monkeypatch)
    assert isinstance(rep, dict)
    assert {"period_label", "totals", "by_project", "attribution"} <= set(rep)

    bud = _json_out(["budget", "--json"], tmp_path, monkeypatch)
    assert isinstance(bud, list)  # no budgets configured → []

    st = _json_out(["status", "--json"], tmp_path, monkeypatch)
    assert st == {"active": False}

    us = _json_out(["usage", "--json"], tmp_path, monkeypatch)
    assert {"range", "summary", "daily", "by_model", "by_tool"} <= set(us)

    ev = _json_out(["evidence", "--all", "--json"], tmp_path, monkeypatch)
    assert {"period_label", "metrics", "cost", "pr_refs"} <= set(ev)

    he = _json_out(["health", "--format", "json"], tmp_path, monkeypatch)
    assert isinstance(he, dict)


# 2. report totals parity with the text path -------------------------------


def test_report_json_totals_match_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init(tmp_path)
    _add(tmp_path)
    _add(tmp_path)
    rep = _json_out(["report", "--all", "--json"], tmp_path, monkeypatch)
    assert isinstance(rep, dict)
    totals = rep["totals"]
    assert totals["input_tokens"] == 2000
    assert totals["output_tokens"] == 1000
    assert round(totals["cost_usd"], 4) == round(0.0123 * 2, 4)


def test_report_json_includes_surface_buckets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0123,
            project="acme:auth",
            client_surface="cli",
        ),
    )
    rep = _json_out(["report", "--all", "--json"], tmp_path, monkeypatch)
    assert isinstance(rep.get("by_tool_surface"), list)
    assert any(bucket["tool"].endswith("cli") for bucket in rep["by_tool_surface"])


# 3. --json-sessions gating -------------------------------------------------


def test_report_json_sessions_gated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init(tmp_path)
    _add(tmp_path)
    base = _json_out(["report", "--all", "--json"], tmp_path, monkeypatch)
    assert "sessions" not in base  # default omits the heavy array
    withs = _json_out(["report", "--all", "--json", "--json-sessions"], tmp_path, monkeypatch)
    assert isinstance(withs, dict)
    assert isinstance(withs["sessions"], list) and len(withs["sessions"]) == 1
    # AiSession serialised: ISO datetimes, no private fields.
    s0 = withs["sessions"][0]
    assert "T" in s0["start"] and "_raw_hash" not in s0


# 4. error path is machine-parseable ---------------------------------------


def test_report_json_error_is_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # No halyard.toml → "no project" error, but as JSON + non-zero exit.
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["report", "--json"])
    assert res.exit_code != 0
    payload = json.loads(res.output)
    assert "error" in payload


# 5. evidence --json carries no digest; markdown still does ----------------


def test_evidence_json_has_no_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init(tmp_path)
    _add(tmp_path)
    ev = _json_out(["evidence", "--all", "--json"], tmp_path, monkeypatch)
    assert isinstance(ev, dict)
    assert ev["digest"] is None
    assert "sha256:" not in json.dumps(ev)

    # The markdown path still carries the integrity digest.
    monkeypatch.chdir(tmp_path)
    md = runner.invoke(app, ["evidence", "--all"])
    assert md.exit_code == 0
    assert "Evidence digest: sha256:" in md.output

    # --verify + --json are mutually exclusive.
    bad = runner.invoke(app, ["evidence", "--json", "--verify", str(tmp_path)])
    assert bad.exit_code == 1


# 6. migration no-op: usage keys unchanged + jsonio encodes types ----------


def test_jsonio_encodes_paths_and_dates() -> None:
    import dataclasses
    from datetime import date

    from halyard.jsonio import to_jsonable

    @dataclasses.dataclass
    class Sample:
        when: datetime
        day: date
        where: Path
        _hidden: int

    out = to_jsonable(Sample(datetime(2026, 5, 7, 9, 0), date(2026, 5, 7), Path("/x/y"), 9))
    assert out == {"when": "2026-05-07T09:00:00", "day": "2026-05-07", "where": "/x/y"}
    assert "_hidden" not in out
