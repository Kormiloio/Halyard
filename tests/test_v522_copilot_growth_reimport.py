"""v5.22 — Copilot importer growth re-import.

The importer froze every chat session at its first import (plain id-set
state), so a session imported while its VS Code window stayed open never
re-imported as it grew — the codex pre-v5.2 / claude pre-v5.21 defect, third
instance. These tests cover the id→size state, the job_id=copilot: read-time
collapse, and the ledger coverage that keeps non-collapsing rows (OTel,
pre-v5.22 imports) from being double-counted.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard.ai_log import AiSession, collapse_gemini_sessions, parse_sessions
from halyard.collectors.copilot import import_copilot_sessions

_SID = "78930975-aaaa-bbbb-cccc-000000000001"


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import halyard.collectors.copilot as mod

    monkeypatch.setattr(mod, "_VSCODE_STORAGE_DIR", tmp_path / "workspaceStorage")
    monkeypatch.setattr(mod, "_IMPORTED_STATE_FILE", tmp_path / "copilot-imported")


def _project(tmp_path: Path) -> Path:
    p = tmp_path / "project"
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[project]\nslug = 'test'\n", encoding="utf-8")
    (p / "ai-sessions.log").write_text("; Halyard AI session log\n", encoding="utf-8")
    return p


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _write_chat(tmp_path: Path, project: Path, *, requests: int) -> Path:
    """A chat session with ``requests`` turns, each with one message part."""
    base = datetime.now() - timedelta(hours=2)
    ws = tmp_path / "workspaceStorage" / "ws1"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "workspace.json").write_text(json.dumps({"folder": project.as_uri()}), encoding="utf-8")
    chat_dir = ws / "chatSessions"
    chat_dir.mkdir(exist_ok=True)
    reqs = [
        {
            "timestamp": _ms(base + timedelta(minutes=5 * i)),
            "completionTokens": 10,
            "response": [{"kind": "message"}],
        }
        for i in range(requests)
    ]
    events = [{"kind": 0, "v": {"creationDate": _ms(base), "requests": reqs}}]
    path = chat_dir / f"{_SID}.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    return path


def _copilot_lines(project: Path) -> list[str]:
    return [
        ln
        for ln in (project / "ai-sessions.log").read_text(encoding="utf-8").splitlines()
        if ln.startswith("s ") and " github-copilot " in ln
    ]


def test_grown_session_reimports_and_collapses(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_chat(tmp_path, project, requests=2)

    first = import_copilot_sessions(project_dir=project)
    assert len(first) == 1
    assert first[0].job_id == f"copilot:{_SID}"
    assert first[0].assistant_message_count == 2

    # The window stays open; the session grows.
    _write_chat(tmp_path, project, requests=6)
    second = import_copilot_sessions(project_dir=project)
    assert len(second) == 1, "grown chat session must re-import"
    assert second[0].assistant_message_count == 6

    # Two raw rows, one canonical session at read time.
    assert len(_copilot_lines(project)) == 2
    collapsed = [s for s in parse_sessions(project) if s.tool == "github-copilot"]
    assert len(collapsed) == 1
    assert collapsed[0].assistant_message_count == 6


def test_unchanged_session_is_skipped(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_chat(tmp_path, project, requests=2)

    assert len(import_copilot_sessions(project_dir=project)) == 1
    assert import_copilot_sessions(project_dir=project) == []
    assert len(_copilot_lines(project)) == 1


def test_legacy_state_entry_never_double_counts(tmp_path: Path) -> None:
    """A pre-v5.22 state file (bare ids) triggers a one-time re-check; a
    session whose pre-v5.22 import row is in the ledger (session_id, no
    collapsing job_id) must be skipped, not re-imported beside it."""
    project = _project(tmp_path)
    _write_chat(tmp_path, project, requests=3)

    # Pre-v5.22 import row: session_id set, NO job_id.
    legacy = AiSession(
        start=datetime.now() - timedelta(hours=2),
        end=datetime.now() - timedelta(hours=1),
        tool="github-copilot",
        model="github-copilot",
        input_tokens=0,
        output_tokens=30,
        cost_usd=0.0,
        source="import",
        session_id=_SID,
    )
    with (project / "ai-sessions.log").open("a", encoding="utf-8") as f:
        f.write(legacy.to_log_line() + "\n")
    # Pre-v5.22 state: bare id, no size.
    (tmp_path / "copilot-imported").write_text(f"{_SID}\n", encoding="utf-8")

    assert import_copilot_sessions(project_dir=project) == []
    assert len(_copilot_lines(project)) == 1  # the legacy row only


def test_otel_captured_session_stays_skipped(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_chat(tmp_path, project, requests=2)

    otel_row = AiSession(
        start=datetime.now() - timedelta(hours=2),
        end=datetime.now() - timedelta(hours=1),
        tool="github-copilot",
        model="github-copilot",
        input_tokens=0,
        output_tokens=50,
        cost_usd=0.0,
        job_id=f"copilot-otel:{_SID}",
        telemetry_source="copilot-otel",
    )
    with (project / "ai-sessions.log").open("a", encoding="utf-8") as f:
        f.write(otel_row.to_log_line() + "\n")

    # Cleared state file: the ledger check alone must protect the session.
    assert import_copilot_sessions(project_dir=project) == []
    assert len(_copilot_lines(project)) == 1


def test_otel_rows_never_collapse_with_import_rows() -> None:
    def _row(job_id: str, out: int) -> AiSession:
        return AiSession(
            start=datetime(2026, 6, 10, 10, 0),
            end=datetime(2026, 6, 10, 11, 0),
            tool="github-copilot",
            model="github-copilot",
            input_tokens=0,
            output_tokens=out,
            cost_usd=0.0,
            job_id=job_id,
            session_id=_SID,
        )

    otel = _row(f"copilot-otel:{_SID}", 50)
    imp = _row(f"copilot:{_SID}", 80)
    # Distinct namespaces: the OTel row passes through untouched.
    out = collapse_gemini_sessions([otel, imp])
    assert len(out) == 2

    # But two import rows of the same session collapse to the fuller one.
    out2 = collapse_gemini_sessions([imp, _row(f"copilot:{_SID}", 200)])
    assert len(out2) == 1
    assert out2[0].output_tokens == 200
