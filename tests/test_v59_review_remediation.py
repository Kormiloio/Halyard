"""v5.9 — regression tests for the review-remediation fixes."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from halyard import ai_log, attribution
from halyard.ai_log import AiSession, read_locked_file
from halyard.attribution import canonical_project, load_project_aliases, set_project_alias


# #4 — transitive alias resolution + cycle guard
def test_canonical_project_follows_chain() -> None:
    aliases = {"A": "B", "B": "C"}
    assert canonical_project("A", aliases) == "C"
    assert canonical_project("B", aliases) == "C"
    assert canonical_project("C", aliases) == "C"
    assert canonical_project("X", aliases) == "X"  # passthrough
    assert canonical_project(None, aliases) is None


def test_canonical_project_cycle_terminates() -> None:
    # Must not hang; resolves to a member of the cycle.
    assert canonical_project("A", {"A": "B", "B": "A"}) in {"A", "B"}


# #6 — alias map cached, refreshed on write (mtime)
def test_alias_cache_refreshes_after_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(attribution, "_ALIASES_PATH", tmp_path / "project-aliases.toml")
    monkeypatch.setattr(attribution, "_alias_cache", None)
    assert load_project_aliases() == {}
    set_project_alias("git/X", "client:x")
    assert load_project_aliases() == {"git/X": "client:x"}


# #1 — read path releases via _release_read_lock (never the writer's unlock)
def test_read_locked_file_uses_read_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "f.log"
    log.write_text("hi\n", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(ai_log, "_release_lock", lambda fd: calls.append("write"))
    monkeypatch.setattr(ai_log, "_release_read_lock", lambda fd: calls.append("read"))
    with read_locked_file(log) as fh:
        fh.read()
    assert calls == ["read"]  # the v5.9 fix: never the writer's release


# #3 — one failing write does not drop the rest of the dequeued batch
def test_process_write_queue_continues_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard.hub_server import HubServer

    monkeypatch.setattr(ai_log, "_HALYARD_DIAG_LOG", tmp_path / "diag.log")
    srv = HubServer(project_dir=tmp_path, port=54330)

    def mk(minute: int) -> AiSession:
        return AiSession(
            start=datetime(2026, 5, 1, 10, minute),
            end=datetime(2026, 5, 1, 10, minute + 1),
            tool="t",
            model="m",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
        )

    s1, s2 = mk(0), mk(2)
    srv._write_queue.append(s1)
    srv._write_queue.append(s2)
    written: list[AiSession] = []

    def fake_write(sess: AiSession) -> None:
        if sess is s1:
            raise OSError("boom")
        written.append(sess)

    monkeypatch.setattr(srv, "_write_to_log", fake_write)
    srv._process_write_queue()
    assert written == [s2]  # s1 failed but s2 still written; no thread death


# #5 — a budget keyed on an aliased raw slug matches canonical sessions
def test_budget_matches_aliased_slug(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from halyard import budget
    from halyard.ai_log import AI_LOG_FILENAME, HEADER, append_session

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")
    append_session(
        proj,
        AiSession(
            start=datetime(2026, 5, 1, 10, 0),
            end=datetime(2026, 5, 1, 10, 5),
            tool="claude-code",
            model="m",
            input_tokens=100,
            output_tokens=50,
            cost_usd=2.50,
            project="client:x",  # canonical
        ),
        direct=True,
    )
    # alias maps the raw slug the budget is keyed on → the canonical slug
    monkeypatch.setattr(attribution, "_ALIASES_PATH", tmp_path / "aliases.toml")
    monkeypatch.setattr(attribution, "_alias_cache", None)
    set_project_alias("git/X", "client:x")
    monkeypatch.setattr(
        budget,
        "load_budgets",
        lambda: {"git/X": budget.ProjectBudget(daily_usd=100.0, monthly_usd=1000.0)},
    )
    # find_hub / find_project_dir are local imports inside budget_status — patch source.
    monkeypatch.setattr("halyard.hub.find_hub", lambda: proj)
    monkeypatch.setattr("halyard.ai_log.find_project_dir", lambda: None)

    statuses = budget.budget_status(now=datetime(2026, 5, 1, 12, 0))
    assert len(statuses) == 1
    assert statuses[0].month_spend == 2.50  # matched despite the slug mismatch
