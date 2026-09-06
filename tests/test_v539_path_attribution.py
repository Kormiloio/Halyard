"""v5.39 — imported sessions recorded a directory, then threw it away.

`repos.toml` matches on git *remotes*. Imported sessions do not carry one —
they record the directory they ran in. That directory may since have moved
(an observed Codex rollout pointed at a path that no longer exists) or may
be a repository's *parent* (Junie records the workspace root, which held
four sibling repos). Either way `infer_project` returns None, and the
directory — the only remaining clue — was discarded, leaving the session
permanently unattributable.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard import git_context
from halyard.ai_log import AiSession, _parse_line, resolve_paths
from halyard.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _paths_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg = tmp_path / "paths.toml"
    monkeypatch.setattr(git_context, "_PATHS_CONFIG", cfg)
    return cfg


def _session(**kw) -> AiSession:
    base = {
        "start": datetime(2026, 9, 1, 9),
        "end": datetime(2026, 9, 1, 10),
        "tool": "codex",
        "model": "m",
        "input_tokens": 10,
        "output_tokens": 1,
        "cost_usd": 0.0,
    }
    base.update(kw)
    return AiSession(**base)  # type: ignore[arg-type]


# --- the field survives the wire --------------------------------------


def test_source_path_round_trips_through_the_ledger() -> None:
    """Paths contain spaces and slashes, so the wire form must encode them."""
    line = _session(source_path="/a b/Artifacts/Mycelium").to_log_line()
    assert "source_path=%2Fa%20b" in line, "must be percent-encoded"
    assert _parse_line(line).source_path == "/a b/Artifacts/Mycelium"


def test_a_row_without_a_path_is_unchanged() -> None:
    line = _session().to_log_line()
    assert "source_path" not in line
    assert _parse_line(line).source_path is None


# --- the map ----------------------------------------------------------


def test_register_and_resolve_a_path() -> None:
    git_context.register_path("/gone/Mycelium", "kormilo:mycelium")
    assert git_context.project_for_path("/gone/Mycelium") == "kormilo:mycelium"


def test_an_unmapped_path_resolves_to_nothing() -> None:
    assert git_context.project_for_path("/never/mapped") is None
    assert git_context.project_for_path(None) is None


def test_matching_is_exact_not_prefix() -> None:
    """A parent path must not claim its children.

    The paths needing a mapping are precisely the ambiguous ones: an
    observed Junie workspace root contained four sibling repositories, so a
    prefix rule would attribute all of their work to whichever slug was
    declared first.
    """
    git_context.register_path("/work", "acme:one")
    assert git_context.project_for_path("/work/child") is None


def test_a_corrupt_map_disables_the_rung_rather_than_crashing(_paths_config: Path) -> None:
    _paths_config.write_text("this is not toml {{{", encoding="utf-8")
    assert git_context.load_paths_config() == {}


# --- read-time resolution ---------------------------------------------


def test_a_mapped_path_attributes_history() -> None:
    """Read-time, so mapping fixes sessions imported before the mapping existed."""
    git_context.register_path("/gone/Mycelium", "kormilo:mycelium")
    out = resolve_paths([_session(source_path="/gone/Mycelium")])
    assert out[0].project == "kormilo:mycelium"
    assert out[0].attr_method == "path-map"


def test_an_existing_project_is_never_overwritten() -> None:
    """The importer had better evidence at the time than a directory does now."""
    git_context.register_path("/gone/Mycelium", "kormilo:mycelium")
    out = resolve_paths([_session(source_path="/gone/Mycelium", project="git/Nautilus")])
    assert out[0].project == "git/Nautilus"


def test_an_unmapped_path_stays_unattributed() -> None:
    out = resolve_paths([_session(source_path="/not/mapped")])
    assert out[0].project is None


def test_rows_without_a_path_are_untouched() -> None:
    git_context.register_path("/gone/Mycelium", "kormilo:mycelium")
    rows = [_session()]
    assert resolve_paths(rows) is rows, "no work, same list back"


def test_no_mapping_is_a_cheap_no_op() -> None:
    rows = [_session(source_path="/gone/Mycelium")]
    assert resolve_paths(rows) is rows


# --- the CLI ----------------------------------------------------------


def _project(tmp_path: Path, source_path: str) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    line = _session(source_path=source_path).to_log_line()
    (tmp_path / "ai-sessions.log").write_text(f"; halyard\n{line}\n", encoding="utf-8")
    return tmp_path


def test_dry_run_reports_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _paths_config: Path
) -> None:
    monkeypatch.chdir(_project(tmp_path / "p", "/gone/Mycelium"))

    result = runner.invoke(app, ["link-path", "/gone/Mycelium", "kormilo:mycelium"])

    assert result.exit_code == 0
    assert "Dry run" in result.stdout
    assert not _paths_config.exists(), "dry run must not write"


def test_apply_writes_the_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _paths_config: Path
) -> None:
    monkeypatch.chdir(_project(tmp_path / "p", "/gone/Mycelium"))

    result = runner.invoke(app, ["link-path", "/gone/Mycelium", "kormilo:mycelium", "--apply"])

    assert result.exit_code == 0
    assert _paths_config.exists()
    assert "kormilo:mycelium" in _paths_config.read_text(encoding="utf-8")


def test_the_ledger_is_never_rewritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proj = _project(tmp_path / "p", "/gone/Mycelium")
    before = (proj / "ai-sessions.log").read_text(encoding="utf-8")
    monkeypatch.chdir(proj)

    runner.invoke(app, ["link-path", "/gone/Mycelium", "kormilo:mycelium", "--apply"])

    assert (proj / "ai-sessions.log").read_text(encoding="utf-8") == before


# --- which cwd a long rollout reports ---------------------------------


def test_the_most_frequent_cwd_wins() -> None:
    """A long rollout records `cwd` many times and they need not agree.

    One observed session held 347 records for one path and 83 for another
    after the directory was synced elsewhere mid-session. Last-wins took the
    minority path, mis-attributed the session, and I reported that to the
    user as fact before they corrected it.

    Exercised through the tally helper rather than a synthetic rollout: the
    selection rule is the thing that changed, and a full fixture would have
    to satisfy every unrelated precondition of the parser to reach it.
    """
    from halyard.collectors.codex_app import _tally_cwd

    counts: dict[str, int] = {}
    for _ in range(347):
        _tally_cwd(counts, "/work/Nautilus")
    for _ in range(83):
        _tally_cwd(counts, "/synced/copy/Nautilus")  # recorded *last*

    assert max(counts, key=lambda c: counts[c]) == "/work/Nautilus"


def test_ties_break_toward_the_first_seen_path() -> None:
    """Insertion order is preserved, so a tie keeps where the session began."""
    from halyard.collectors.codex_app import _tally_cwd

    counts: dict[str, int] = {}
    _tally_cwd(counts, "/first")
    _tally_cwd(counts, "/second")

    assert max(counts, key=lambda c: counts[c]) == "/first"


def test_the_tally_ignores_junk() -> None:
    from halyard.collectors.codex_app import _tally_cwd

    counts: dict[str, int] = {}
    for junk in (None, "", 42, {"a": 1}):
        _tally_cwd(counts, junk)

    assert counts == {}
