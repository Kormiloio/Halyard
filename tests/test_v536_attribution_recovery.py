"""v5.36 — the row collapse discarded attribution, and its remedy did not exist.

Two defects in one area:

- `_canonical_gemini_row` ranks by `(input+output, has_project, ...)`. Tokens
  outrank attribution, so a later unattributed row with a higher total
  silently discarded a project every earlier row agreed on. One observed
  group had 74 of 75 rows carrying `project=git/Nautilus` and collapsed to
  no project at all, hiding 419.8M tokens from every per-project report.
- `halyard adopt` has told users to run `halyard reattribute` since it
  shipped. The command did not exist.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.ai_log import AiSession, collapse_gemini_sessions
from halyard.cli import app

runner = CliRunner()


def _row(
    *,
    tokens: int,
    project: str | None,
    job: str = "codex:abc",
    minutes: int = 10,
) -> AiSession:
    start = datetime(2026, 8, 9, 13, 0)
    return AiSession(
        start=start,
        end=start + timedelta(minutes=minutes),
        tool="codex",
        model="gpt-5.6-sol",
        input_tokens=tokens,
        output_tokens=0,
        cost_usd=0.0,
        project=project,
        job_id=job,
    )


# --- the collapse must not lose attribution ---------------------------


def test_the_winning_row_inherits_the_group_project() -> None:
    """The observed shape: the largest row is the one missing a project."""
    rows = [
        _row(tokens=2_508_802, project="git/Nautilus"),
        _row(tokens=15_217_312, project=None),  # newest, largest, unattributed
    ]

    out = collapse_gemini_sessions(rows)

    assert len(out) == 1
    assert out[0].input_tokens == 15_217_312, "still the most complete row"
    assert out[0].project == "git/Nautilus", "attribution must survive the collapse"


def test_a_winner_with_its_own_project_is_untouched() -> None:
    rows = [
        _row(tokens=100, project="acme:web"),
        _row(tokens=999, project="globex:api"),
    ]
    out = collapse_gemini_sessions(rows)
    assert out[0].project == "globex:api"


def test_a_disagreeing_group_is_left_unattributed() -> None:
    """Ambiguity is not guessed at.

    Two rows naming different projects is stranger than a missing field, and
    guessing would move billable attribution onto a project the evidence does
    not support. Unattributed is the honest answer.
    """
    rows = [
        _row(tokens=100, project="acme:web"),
        _row(tokens=200, project="globex:api"),
        _row(tokens=999, project=None),
    ]
    out = collapse_gemini_sessions(rows)
    assert out[0].project is None


def test_a_group_with_no_project_anywhere_stays_unattributed() -> None:
    rows = [_row(tokens=100, project=None), _row(tokens=999, project=None)]
    assert collapse_gemini_sessions(rows)[0].project is None


def test_a_single_row_is_returned_unchanged() -> None:
    row = _row(tokens=100, project=None)
    assert collapse_gemini_sessions([row])[0] is row


def test_unrelated_sessions_are_not_merged() -> None:
    rows = [
        _row(tokens=100, project="acme:web", job="codex:one"),
        _row(tokens=999, project=None, job="codex:two"),
    ]
    out = collapse_gemini_sessions(rows)
    assert len(out) == 2
    assert {s.project for s in out} == {"acme:web", None}


# --- the command that did not exist -----------------------------------


def _project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    rows = ["; halyard\n"]
    for i in range(3):
        start = datetime(2026, 8, 1 + i, 9)
        rows.append(
            f"s {start:%Y-%m-%dT%H:%M:%S} {start + timedelta(hours=1):%Y-%m-%dT%H:%M:%S} "
            "claude-code claude-opus-5 100 50 0.0 project=git/Halyard\n"
        )
    (tmp_path / "ai-sessions.log").write_text("".join(rows), encoding="utf-8")
    return tmp_path


def test_reattribute_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`halyard adopt` has advertised this command since it shipped."""
    monkeypatch.chdir(_project(tmp_path))
    result = runner.invoke(app, ["reattribute", "--help"])
    assert result.exit_code == 0


def test_dry_run_reports_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    (home / ".halyard").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr("halyard.attribution._ALIASES_PATH", home / ".halyard" / "a.toml")
    monkeypatch.chdir(_project(tmp_path / "proj"))

    result = runner.invoke(app, ["reattribute", "git/Halyard", "kormilo:halyard"])

    assert result.exit_code == 0
    assert "Dry run" in result.stdout
    assert not (home / ".halyard" / "a.toml").exists(), "dry run must not write"


def test_apply_records_the_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    (home / ".halyard").mkdir(parents=True)
    alias_file = home / ".halyard" / "a.toml"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr("halyard.attribution._ALIASES_PATH", alias_file)
    monkeypatch.setattr("halyard.attribution._alias_cache", None, raising=False)
    monkeypatch.chdir(_project(tmp_path / "proj"))

    result = runner.invoke(app, ["reattribute", "git/Halyard", "kormilo:halyard", "--apply"])

    assert result.exit_code == 0
    assert alias_file.exists()
    assert "kormilo:halyard" in alias_file.read_text(encoding="utf-8")


def test_aliasing_a_slug_to_itself_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_project(tmp_path))
    result = runner.invoke(app, ["reattribute", "acme:web", "acme:web"])
    assert result.exit_code == 1


def test_the_ledger_is_never_rewritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Read-time aliasing only — history stays append-only."""
    home = tmp_path / "home"
    (home / ".halyard").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr("halyard.attribution._ALIASES_PATH", home / ".halyard" / "a.toml")
    proj = _project(tmp_path / "proj")
    before = (proj / "ai-sessions.log").read_text(encoding="utf-8")
    monkeypatch.chdir(proj)

    runner.invoke(app, ["reattribute", "git/Halyard", "kormilo:halyard", "--apply"])

    assert (proj / "ai-sessions.log").read_text(encoding="utf-8") == before


# --- v5.40: the same rule, for the recorded path ----------------------


def _row_with_path(*, tokens: int, path: str | None, job: str = "codex:abc") -> AiSession:
    s = _row(tokens=tokens, project=None, job=job)
    s.source_path = path
    return s


def test_the_winning_row_inherits_the_group_source_path() -> None:
    """v5.36's fix did not generalise, and the gap was load-bearing.

    A re-imported Codex session recorded its directory on the *new* row, but
    that row carried fewer tokens than an older one and lost the ranking —
    so the session stayed pathless and `halyard link-path` could not reach
    it. Observed: canonical row 2,019,287 in+out with no path, against
    107,376 with one.
    """
    rows = [
        _row_with_path(tokens=107_376, path="/Documents/ChatGPT/Mycelium"),
        _row_with_path(tokens=2_019_287, path=None),  # newest, largest, pathless
    ]

    out = collapse_gemini_sessions(rows)

    assert len(out) == 1
    assert out[0].input_tokens == 2_019_287, "still the most complete row"
    assert out[0].source_path == "/Documents/ChatGPT/Mycelium"


def test_a_winner_with_its_own_path_is_untouched() -> None:
    rows = [
        _row_with_path(tokens=100, path="/old"),
        _row_with_path(tokens=999, path="/new"),
    ]
    assert collapse_gemini_sessions(rows)[0].source_path == "/new"


def test_a_group_disagreeing_on_path_stays_pathless() -> None:
    """Same rule as project: a contradiction is not a gap."""
    rows = [
        _row_with_path(tokens=100, path="/one"),
        _row_with_path(tokens=200, path="/two"),
        _row_with_path(tokens=999, path=None),
    ]
    assert collapse_gemini_sessions(rows)[0].source_path is None


def test_project_and_path_are_inherited_independently() -> None:
    a = _row(tokens=100, project="acme:web")
    b = _row_with_path(tokens=200, path="/work")
    c = _row(tokens=999, project=None)
    out = collapse_gemini_sessions([a, b, c])[0]
    assert out.project == "acme:web"
    assert out.source_path == "/work"
