"""v5.16/B08 — malformed-input crash must not abort a collector import batch.

Blocker B08 (HIGH): token/timestamp fields are coerced with bare
``int()`` / ``datetime.fromtimestamp`` even though every parser documents
"return None on any error". A single crafted file (e.g.
``tokens:{"input":"abc"}`` for Gemini, ``output_tokens:"x"`` for Codex, or an
out-of-range ``creationDate`` for Copilot) raised ValueError/TypeError/
OverflowError that escaped the parser; the importer loops have no per-file
guard, so the *first* bad file aborted the whole import and every later
session was silently dropped.

Each collector gets two checks:
  (a) the malicious/buggy input is handled (parser returns None / batch
      continues), AND
  (b) a benign input still parses and imports (guard against over-restriction).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from halyard.collectors.codex_app import _parse_session_file as codex_parse
from halyard.collectors.codex_app import import_codex_sessions
from halyard.collectors.copilot import import_copilot_sessions, parse_chat_session
from halyard.collectors.gemini_history import parse_session_file as gemini_parse

# ---------------------------------------------------------------------------
# Shared project fixture (a minimal initialised Halyard project)
# ---------------------------------------------------------------------------


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


# ===========================================================================
# Gemini — .jsonl rollout path (the one NOT previously inside a broad except)
# ===========================================================================


def _gemini_rollout_lines(*, tokens: dict[str, object]) -> str:
    return "\n".join(
        json.dumps(o)
        for o in [
            {
                "sessionId": "abc12345-0000-0000-0000-000000000000",
                "startTime": "2026-06-01T10:00:00.000Z",
                "lastUpdated": "2026-06-01T10:05:00.000Z",
            },
            {
                "type": "user",
                "id": "u1",
                "timestamp": "2026-06-01T10:00:01.000Z",
            },
            {
                "type": "gemini",
                "id": "g1",
                "model": "gemini-2.5-pro",
                "timestamp": "2026-06-01T10:05:00.000Z",
                "tokens": tokens,
            },
        ]
    )


def test_gemini_malicious_token_field_returns_none_not_raise(tmp_path: Path) -> None:
    """A non-numeric token field used to raise ValueError out of the rollout
    parser (which only guarded OSError). It must now be contained: the bad
    field degrades to 0 and the session still parses (never raises)."""
    f = tmp_path / "session-a-abc12345.jsonl"
    f.write_text(_gemini_rollout_lines(tokens={"input": "abc", "output": 50}), encoding="utf-8")

    # Must not raise.
    summary = gemini_parse(f)
    assert summary is not None
    # Bad input field degraded to 0; the valid output field survived.
    assert summary.total_input == 0
    assert summary.total_output == 50


def test_gemini_benign_tokens_still_parsed(tmp_path: Path) -> None:
    """Guard against over-restriction: a normal numeric token set still works."""
    f = tmp_path / "session-b-abc12345.jsonl"
    f.write_text(
        _gemini_rollout_lines(tokens={"input": 1200, "cached": 200, "output": 340}),
        encoding="utf-8",
    )
    summary = gemini_parse(f)
    assert summary is not None
    assert summary.total_output == 340
    # gross input (1200) with cached subset (200) -> net input 1000
    assert summary.total_input == 1000


# ===========================================================================
# Codex — parser contract + importer batch must survive one bad file
# ===========================================================================


def _codex_events(*, output_tokens: object, input_tokens: object = 100) -> list[dict]:  # type: ignore[type-arg]
    return [
        {
            "timestamp": "2026-05-23T18:35:58.000Z",
            "type": "session_meta",
            "payload": {
                "id": "x",
                "timestamp": "2026-05-23T18:35:58.000Z",
                "cwd": "/some/project",
            },
        },
        {
            "timestamp": "2026-05-23T18:36:25.000Z",
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
        },
    ]


def _write_codex_rollout(codex_dir: Path, uuid: str, events: list[dict]) -> Path:  # type: ignore[type-arg]
    day = codex_dir / "2026" / "05" / "23"
    day.mkdir(parents=True, exist_ok=True)
    path = day / f"rollout-2026-05-23T18-35-58-{uuid}.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    return path


def test_codex_malicious_token_field_returns_none_not_raise(tmp_path: Path) -> None:
    """``total_token_usage:{"output_tokens":"x"}`` used to raise ValueError out
    of _parse_session_file. It must now be handled (return None for a 0-work
    session, never raise)."""
    path = _write_codex_rollout(
        tmp_path / "codex",
        "00000000-0000-0000-0000-000000000001",
        _codex_events(output_tokens="x"),
    )
    # Must not raise; the bad field degrades to 0 -> 0-work session -> None.
    assert codex_parse(path) is None


def test_codex_one_bad_file_does_not_abort_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The release-gating scenario: a crafted rollout sorted before a good one
    must NOT abort the import — the later valid session must still be imported."""
    import halyard.collectors.codex_app as mod

    codex_dir = tmp_path / "codex"
    monkeypatch.setattr(mod, "_CODEX_SESSIONS_DIR", codex_dir)
    monkeypatch.setattr(mod, "_IMPORTED_STATE_FILE", tmp_path / "codex-imported")
    project = _project(tmp_path)

    # UUID ...01 sorts first (the crafted file); ...02 is a healthy session.
    _write_codex_rollout(
        codex_dir,
        "00000000-0000-0000-0000-000000000001",
        _codex_events(output_tokens="boom", input_tokens="boom"),
    )
    _write_codex_rollout(
        codex_dir,
        "00000000-0000-0000-0000-000000000002",
        _codex_events(output_tokens=500, input_tokens=2000),
    )

    imported = import_codex_sessions(project_dir=project)
    # The good session survives even though a malformed file was processed first.
    assert len(imported) == 1
    assert imported[0].output_tokens == 500


def test_codex_benign_session_still_imported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard against over-restriction: a normal session imports as before."""
    import halyard.collectors.codex_app as mod

    codex_dir = tmp_path / "codex"
    monkeypatch.setattr(mod, "_CODEX_SESSIONS_DIR", codex_dir)
    monkeypatch.setattr(mod, "_IMPORTED_STATE_FILE", tmp_path / "codex-imported")
    project = _project(tmp_path)

    _write_codex_rollout(
        codex_dir,
        "00000000-0000-0000-0000-000000000003",
        _codex_events(output_tokens=321, input_tokens=1000),
    )
    imported = import_codex_sessions(project_dir=project)
    assert len(imported) == 1
    assert imported[0].output_tokens == 321


# ===========================================================================
# Copilot — out-of-range epoch-millis timestamp must not crash the parser
# ===========================================================================


def _copilot_session_text(*, creation_date: object) -> str:
    return json.dumps(
        {
            "kind": 0,
            "v": {
                "creationDate": creation_date,
                "sessionId": "session-x",
                "requests": [
                    {
                        "requestId": "r1",
                        "timestamp": creation_date,
                        "completionTokens": 100,
                        "response": [
                            {"kind": "message", "value": "ok"},
                            {"kind": "toolInvocationSerialized"},
                        ],
                    }
                ],
            },
        }
    )


def test_copilot_out_of_range_timestamp_returns_none_not_raise(tmp_path: Path) -> None:
    """A crafted out-of-range epoch-millis ``creationDate`` made
    ``datetime.fromtimestamp`` raise OSError/OverflowError straight out of the
    parser. It must now be handled: no valid start -> return None, never raise."""
    f = tmp_path / "session-bad.jsonl"
    # 10**20 ms is far beyond the platform's representable time_t range.
    f.write_text(_copilot_session_text(creation_date=10**20), encoding="utf-8")
    assert parse_chat_session(f) is None  # must not raise


def test_copilot_benign_session_still_parsed(tmp_path: Path) -> None:
    """Guard against over-restriction: a normal millis timestamp parses fine."""
    f = tmp_path / "session-ok.jsonl"
    f.write_text(_copilot_session_text(creation_date=1779563464638), encoding="utf-8")
    s = parse_chat_session(f)
    assert s is not None
    assert s.output_tokens == 100
    assert s.tool == "github-copilot"


def test_copilot_one_bad_session_does_not_abort_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed chat session must skip-and-continue so a later valid session
    in the same workspace is still imported."""
    import halyard.collectors.copilot as mod

    storage = tmp_path / "workspaceStorage"
    ws = storage / "ws1"
    chat = ws / "chatSessions"
    chat.mkdir(parents=True, exist_ok=True)
    project = _project(tmp_path)
    (ws / "workspace.json").write_text(json.dumps({"folder": project.as_uri()}), encoding="utf-8")

    monkeypatch.setattr(mod, "_VSCODE_STORAGE_DIR", storage)
    monkeypatch.setattr(mod, "_IMPORTED_STATE_FILE", tmp_path / "copilot-imported")

    # "a-bad" sorts before "b-good" in glob order on most platforms; the guard
    # in the importer loop is what makes the ordering irrelevant.
    (chat / "a-bad.jsonl").write_text(_copilot_session_text(creation_date=10**20), encoding="utf-8")
    (chat / "b-good.jsonl").write_text(
        _copilot_session_text(creation_date=1779563464638), encoding="utf-8"
    )

    imported = import_copilot_sessions(project_dir=project)
    assert len(imported) == 1
    assert imported[0].output_tokens == 100
