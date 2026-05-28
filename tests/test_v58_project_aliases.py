"""v5.8 — read-time project alias canonicalization.

One logical project can accrue several slug forms in the append-only log; a
user-defined alias map merges them at read time (the log is never rewritten).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from halyard import attribution
from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session, parse_sessions
from halyard.attribution import canonical_project, load_project_aliases, set_project_alias


def _use_alias_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "project-aliases.toml"
    monkeypatch.setattr(attribution, "_ALIASES_PATH", p)
    return p


def test_canonical_project_passthrough_and_hit() -> None:
    aliases = {"git/Halyard": "kormilo:halyard"}
    assert canonical_project("git/Halyard", aliases) == "kormilo:halyard"
    assert canonical_project("other:proj", aliases) == "other:proj"  # passthrough
    assert canonical_project(None, aliases) is None


def test_load_missing_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_alias_file(tmp_path, monkeypatch)
    assert load_project_aliases() == {}


def test_set_then_load_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_alias_file(tmp_path, monkeypatch)
    set_project_alias("git/Halyard", "kormilo:halyard")
    set_project_alias("kormilo/halyard", "kormilo:halyard")
    assert load_project_aliases() == {
        "git/Halyard": "kormilo:halyard",
        "kormilo/halyard": "kormilo:halyard",
    }


def test_invalid_toml_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _use_alias_file(tmp_path, monkeypatch)
    p.write_text("this is not valid toml = = =", encoding="utf-8")
    assert load_project_aliases() == {}


def _write_log(tmp_path: Path, *projects: str) -> None:
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")
    for i, proj in enumerate(projects):
        append_session(
            tmp_path,
            AiSession(
                start=datetime(2026, 5, 7, 10, i),
                end=datetime(2026, 5, 7, 10, i + 1),
                tool="claude-code",
                model="claude-sonnet-4-6",
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.10,
                project=proj,
            ),
            direct=True,
        )


def test_parse_sessions_canonicalizes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_alias_file(tmp_path, monkeypatch)
    set_project_alias("git/Halyard", "kormilo:halyard")
    set_project_alias("kormilo/halyard", "kormilo:halyard")
    _write_log(tmp_path, "git/Halyard", "kormilo/halyard", "kormilo:halyard", "acme:auth")

    projects = sorted({s.project for s in parse_sessions(tmp_path)})
    # the three Halyard forms merge; the unrelated project is untouched
    assert projects == ["acme:auth", "kormilo:halyard"]


def test_parse_sessions_no_aliases_is_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_alias_file(tmp_path, monkeypatch)  # file absent → empty map
    _write_log(tmp_path, "git/Halyard", "kormilo:halyard")
    projects = sorted({s.project for s in parse_sessions(tmp_path)})
    assert projects == ["git/Halyard", "kormilo:halyard"]  # unchanged
