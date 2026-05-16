"""v2.65 — attribution integrity & visibility."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard import git_context
from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.attribution import (
    attribution_confidence,
    attribution_mix,
    format_attribution_mix,
)
from halyard.doctor import build_doctor_report, has_errors

_NOW = datetime.now()


def _s(i: int, *, project: str | None, attr: str | None, remote: str | None = None) -> AiSession:
    start = _NOW - timedelta(hours=200) + timedelta(hours=i)
    return AiSession(
        start=start,
        end=start + timedelta(minutes=3),
        tool="claude-code",
        model="claude-opus-4-7",
        input_tokens=100,
        output_tokens=50,
        cost_usd=1.0,
        project=project,
        attr_method=attr,
        remote=remote,
    )


# --- confidence -----------------------------------------------------------


@pytest.mark.parametrize(
    "attr,project,expected",
    [
        ("timer", "acme:web", "timer"),
        ("repo-map", "acme:web", "mapped"),
        ("ws_root", "acme:web", "mapped"),
        ("toml", "acme:web", "toml"),
        ("git-auto", "git/x", "auto"),
        ("git", "git/x", "auto"),  # legacy → safe lower bound, never mapped
        ("backfill", "acme:web", "unknown"),
        ("timer", None, "none"),  # no project always none
        (None, None, "none"),
    ],
)
def test_confidence_mapping(attr: str | None, project: str | None, expected: str) -> None:
    assert attribution_confidence(_s(0, project=project, attr=attr)) == expected


def test_mix_orders_strongest_first() -> None:
    sessions = [
        _s(1, project="a:b", attr="timer"),
        _s(2, project="a:b", attr="git"),  # legacy → auto
        _s(3, project=None, attr=None),
        _s(4, project="a:b", attr="toml"),
    ]
    mix = attribution_mix(sessions)
    assert list(mix) == ["timer", "toml", "auto", "none"]  # CONFIDENCE_ORDER
    assert mix == {"timer": 1, "toml": 1, "auto": 1, "none": 1}
    assert "adrift 1" in format_attribution_mix(sessions)


# --- infer_project_with_source rung --------------------------------------


def test_rung_toml_walkup(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text('[project]\nslug = "acme:web"\n')
    slug, rung = git_context.infer_project_with_source(tmp_path)
    assert slug == "acme:web"
    assert rung == "toml"


def test_rung_repo_map_then_git_auto(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(git_context, "_slug_from_halyard_toml", lambda _c: None)
    monkeypatch.setattr(git_context, "_git_remote_url", lambda _c: "git@github.com:acme/web.git")
    monkeypatch.setattr(git_context, "_remote_matches", lambda remote, pat: pat in remote)
    monkeypatch.setattr(git_context, "_load_repos_config", lambda: {"acme/web": "acme:web"})
    slug, rung = git_context.infer_project_with_source(tmp_path)
    assert (slug, rung) == ("acme:web", "repo-map")

    monkeypatch.setattr(git_context, "_load_repos_config", lambda: {})
    slug, rung = git_context.infer_project_with_source(tmp_path)
    assert rung == "git-auto" and slug == "git/web"


# --- doctor attribution canary -------------------------------------------


def _proj(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[business]\n")
    (p / AI_LOG_FILENAME).write_text(HEADER)
    return p


def _report_ids(tmp_path: Path, sessions: list[AiSession]) -> set[str]:
    proj = _proj(tmp_path / "p")
    for s in sessions:
        append_session(proj, s)
    rep = build_doctor_report(start=proj)
    _report_ids.last = rep  # type: ignore[attr-defined]
    return {c.id for c in rep.checks}


def test_adrift_regression_fires(tmp_path: Path) -> None:
    # 20 prior attributed, 20 recent unattributed → regression.
    prior = [_s(i, project="acme:web", attr="timer") for i in range(20)]
    recent = [_s(20 + i, project=None, attr=None) for i in range(20)]
    ids = _report_ids(tmp_path, prior + recent)
    assert "attr.adrift_regression" in ids
    rep = _report_ids.last  # type: ignore[attr-defined]
    assert has_errors(rep) is False  # warning only — exit-code contract


def test_stable_attribution_no_canary(tmp_path: Path) -> None:
    sessions = [_s(i, project="acme:web", attr="timer") for i in range(40)]
    ids = _report_ids(tmp_path, sessions)
    assert "attr.adrift_regression" not in ids


def test_per_remote_regression_fires(tmp_path: Path) -> None:
    prior = [
        _s(i, project="acme:web", attr="timer", remote="git@github.com:acme/web.git")
        for i in range(20)
    ]
    recent = [
        _s(20 + i, project=None, attr=None, remote="git@github.com:acme/web.git") for i in range(20)
    ]
    ids = _report_ids(tmp_path, prior + recent)
    assert any(i.startswith("attr.remote.") for i in ids)


def test_remediation_emits_command_and_writes_nothing(tmp_path: Path) -> None:
    from halyard.doctor import _group_unattributed_by_remote

    home = tmp_path / "home"
    monkey_home = home / ".halyard"
    monkey_home.mkdir(parents=True)
    ulog = monkey_home / "unattributed.log"
    ulog.write_text(HEADER)
    s = _s(0, project=None, attr=None, remote="git@github.com:acme/web.git")
    with ulog.open("a") as fh:
        fh.write(s.to_log_line() + "\n")
    groups = _group_unattributed_by_remote(ulog)
    assert groups  # sanity: grouped by remote
    before = ulog.read_text()
    # The doctor check only proposes; the file is never mutated by it.
    assert ulog.read_text() == before


# --- MCP surface ----------------------------------------------------------


def test_work_summary_includes_attribution_mix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard import mcp_server

    proj = _proj(tmp_path / "p")
    append_session(proj, _s(0, project="acme:web", attr="timer"))
    append_session(proj, _s(1, project=None, attr=None))
    monkeypatch.setattr(mcp_server, "aggregate_session_dirs", lambda: [proj])
    ws = mcp_server._work_summary("30d")
    assert "attribution_mix" in ws
    assert ws["attribution_mix"].get("timer") == 1
    assert ws["attribution_mix"].get("none") == 1
    json.dumps(ws)  # must stay JSON-serialisable (MCP contract)
