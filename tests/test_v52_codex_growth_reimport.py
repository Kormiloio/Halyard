"""v5.2 — Codex importer re-imports in-progress sessions.

The old importer skipped any rollout UUID it had seen once, freezing a session
captured mid-write at a partial snapshot. These tests cover the growth-aware
re-import plus the read-time collapse that keeps it idempotent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from halyard.ai_log import AiSession, collapse_gemini_sessions, parse_sessions
from halyard.collectors.codex_app import import_codex_sessions

_UUID = "019e56fb-207d-7400-8aba-587d0ed53e8e"
_FILENAME = f"rollout-2026-05-23T18-35-58-{_UUID}.jsonl"


def _events(
    *,
    input_tokens: int,
    output_tokens: int,
    end_ts: str = "2026-05-23T18:36:25.000Z",
    filler: int = 0,
    cwd: str = "/some/project",
) -> list[dict]:  # type: ignore[type-arg]
    evs: list[dict] = [  # type: ignore[type-arg]
        {
            "timestamp": "2026-05-23T18:35:58.000Z",
            "type": "session_meta",
            "payload": {"id": _UUID, "timestamp": "2026-05-23T18:35:58.000Z", "cwd": cwd},
        },
        {
            "timestamp": "2026-05-23T18:35:59.000Z",
            "type": "turn_context",
            "payload": {"cwd": cwd, "model": "gpt-5.5"},
        },
    ]
    for _ in range(filler):
        evs.append(
            {
                "timestamp": "2026-05-23T18:36:00.000Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "x" * 64},
            }
        )
    evs.append(
        {
            "timestamp": end_ts,
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": input_tokens,
                        "cached_input_tokens": 0,
                        "output_tokens": output_tokens,
                    }
                },
            },
        }
    )
    return evs


def _write_rollout(codex_dir: Path, events: list[dict]) -> Path:  # type: ignore[type-arg]
    day = codex_dir / "2026" / "05" / "23"
    day.mkdir(parents=True, exist_ok=True)
    path = day / _FILENAME
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    return path


def _project(tmp_path: Path) -> Path:
    p = tmp_path / "project"
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[project]\nslug = 'test'\n", encoding="utf-8")
    (p / "ai-sessions.log").write_text(
        "; Halyard AI session log\n"
        "; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd> [key=value ...]\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the importer at tmp paths. (Hub isolation is handled in conftest.)"""
    import halyard.collectors.codex_app as mod

    monkeypatch.setattr(mod, "_CODEX_SESSIONS_DIR", tmp_path / "codex")
    monkeypatch.setattr(mod, "_IMPORTED_STATE_FILE", tmp_path / "codex-imported")


def _codex_lines(project: Path) -> list[str]:
    return [
        ln
        for ln in (project / "ai-sessions.log").read_text(encoding="utf-8").splitlines()
        if ln.startswith("s ") and " codex " in ln
    ]


def test_reimport_when_rollout_grows(tmp_path: Path) -> None:
    project = _project(tmp_path)
    codex_dir = tmp_path / "codex"

    # First import: a partial snapshot, as if captured mid-session.
    _write_rollout(codex_dir, _events(input_tokens=12842, output_tokens=312))
    first = import_codex_sessions(project_dir=project)
    assert len(first) == 1
    assert first[0].output_tokens == 312

    # The session keeps running: the rollout grows with more tokens.
    _write_rollout(
        codex_dir,
        _events(
            input_tokens=419943,
            output_tokens=61551,
            end_ts="2026-05-23T19:10:33.000Z",
            filler=40,
        ),
    )
    second = import_codex_sessions(project_dir=project)
    assert len(second) == 1, "grown rollout must be re-imported"
    assert second[0].output_tokens == 61551

    # Two raw rows now exist, but they collapse to the fuller one at read time.
    assert len(_codex_lines(project)) == 2
    collapsed = [s for s in parse_sessions(project) if s.tool == "codex"]
    assert len(collapsed) == 1
    assert collapsed[0].output_tokens == 61551
    assert collapsed[0].input_tokens == 419943


def test_unchanged_rollout_is_skipped(tmp_path: Path) -> None:
    project = _project(tmp_path)
    codex_dir = tmp_path / "codex"
    _write_rollout(codex_dir, _events(input_tokens=1000, output_tokens=50))

    assert len(import_codex_sessions(project_dir=project)) == 1
    # Nothing changed on disk — a second run must import nothing.
    assert import_codex_sessions(project_dir=project) == []
    assert len(_codex_lines(project)) == 1


def test_legacy_bare_uuid_triggers_recheck(tmp_path: Path) -> None:
    project = _project(tmp_path)
    codex_dir = tmp_path / "codex"
    _write_rollout(codex_dir, _events(input_tokens=5000, output_tokens=900))

    # Pre-v5.2 state: a bare UUID with no recorded size.
    (tmp_path / "codex-imported").write_text(f"{_UUID}\n", encoding="utf-8")

    re_imported = import_codex_sessions(project_dir=project)
    assert len(re_imported) == 1, "a size-less legacy entry must be re-checked once"
    # And the state is upgraded to the new uuid<TAB>size form.
    state = (tmp_path / "codex-imported").read_text(encoding="utf-8")
    assert "\t" in state and _UUID in state


def test_imported_row_tagged_with_codex_job_id(tmp_path: Path) -> None:
    project = _project(tmp_path)
    codex_dir = tmp_path / "codex"
    _write_rollout(codex_dir, _events(input_tokens=2000, output_tokens=100))

    sessions = import_codex_sessions(project_dir=project)
    assert sessions[0].job_id == f"codex:{_UUID}"


def test_collapse_keeps_fuller_codex_row() -> None:
    from datetime import datetime

    def _row(inp: int, out: int) -> AiSession:
        return AiSession(
            start=datetime(2026, 5, 23, 18, 35, 58),
            end=datetime(2026, 5, 23, 19, 10, 33),
            tool="codex",
            model="gpt-5.5",
            input_tokens=inp,
            output_tokens=out,
            cost_usd=0.0,
            job_id=f"codex:{_UUID}",
        )

    stub = _row(12842, 312)
    full = _row(419943, 61551)
    out = collapse_gemini_sessions([stub, full])
    assert len(out) == 1
    assert out[0].output_tokens == 61551
    # Idempotent.
    assert collapse_gemini_sessions(out) == out
