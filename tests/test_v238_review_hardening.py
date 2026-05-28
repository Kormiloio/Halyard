"""Regression tests for v2.38 review-hardening fixes (security/injection)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from halyard.ai_log import AiSession
from halyard.cli import app


def _session(branch: str | None = None, model: str = "claude-sonnet-4-6") -> AiSession:
    return AiSession(
        start=datetime(2026, 5, 15, 9),
        end=datetime(2026, 5, 15, 9) + timedelta(minutes=5),
        tool="claude-code",
        model=model,
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.01,
        project="acme:auth",
        branch=branch,
    )


def test_session_feed_escapes_rich_markup_in_branch() -> None:
    from halyard.tui.widgets.session_feed import SessionFeed

    feed = SessionFeed()
    feed.render_sessions([_session(branch="feat/[red]boom[/red]")])
    text = feed.last_rendered_text
    # Escaped as \[red] — Rich renders it literally instead of as a style tag.
    assert r"\[red]" in text
    assert "[red]" not in text.replace(r"\[red]", "")


def test_session_feed_escapes_markup_in_model() -> None:
    from halyard.tui.widgets.session_feed import SessionFeed

    feed = SessionFeed()
    feed.render_sessions([_session(model="[bold]evil")])
    assert r"\[bold]" in feed.last_rendered_text


def test_usage_pane_escapes_markup_in_favorite_model() -> None:
    # v2.71: usage_pane rendered favorite_model unescaped (v2.38 gap).
    from halyard.tui.widgets.usage_pane import UsagePane

    pane = UsagePane()
    pane.render_sessions([_session(model="[bold]evil"), _session(model="[bold]evil")])
    assert r"\[bold]" in pane.last_rendered_text
    assert "[bold]" not in pane.last_rendered_text.replace(r"\[bold]", "")


def test_branch_modal_label_escapes_markup_in_branch() -> None:
    # v2.71: branch_modal rendered branch unescaped (v2.38 gap).
    from halyard.tui.widgets.branch_modal import _branch_label

    label = _branch_label("feat/[red]boom[/red]", None)
    assert r"\[red]" in label
    assert "[red]" not in label.replace(r"\[red]", "")


def test_adopt_rejects_slug_with_toml_injection(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    target.mkdir()
    result = CliRunner().invoke(app, ["adopt", str(target), "--slug", 'acme"\nevil = "x'])
    assert result.exit_code == 1
    assert "invalid slug" in result.output
    assert not (target / "halyard.toml").exists()


def test_adopt_accepts_clean_slug(tmp_path: Path) -> None:
    target = tmp_path / "proj2"
    target.mkdir()
    result = CliRunner().invoke(app, ["adopt", str(target), "--slug", "kormilo:halyard"])
    assert result.exit_code == 0
    assert (target / "halyard.toml").read_text(
        encoding="utf-8"
    ) == '[project]\nslug = "kormilo:halyard"\n'


def test_gemini_find_session_file_rejects_glob_metachars() -> None:
    from halyard.collectors.gemini_history import find_session_file

    # Glob metacharacters / path separators must be refused outright.
    assert find_session_file("../../*") is None
    assert find_session_file("a*b?c[d]") is None
    assert find_session_file("") is None


# --- Phase 3: data integrity ------------------------------------------------


def test_mode_cache_not_poisoned_across_projects(tmp_path: Path) -> None:
    from halyard import state_integrity as si

    si._reset_cache_for_tests()
    hash_proj = tmp_path / "h"
    hash_proj.mkdir()
    (hash_proj / "halyard.toml").write_text('state_integrity = "hash"\n', encoding="utf-8")
    plain_proj = tmp_path / "p"
    plain_proj.mkdir()  # no halyard.toml

    assert si.current_mode(hash_proj) == "hash"
    # A different project (and project_dir=None) must NOT inherit "hash".
    assert si.current_mode(plain_proj) == "off"
    assert si.current_mode(None) == "off"
    si._reset_cache_for_tests()


def test_write_trusted_state_sidecar_is_atomic_and_verifies(tmp_path: Path) -> None:
    from halyard import state_integrity as si

    si._reset_cache_for_tests()
    target = tmp_path / "state.txt"
    si.write_trusted_state(target, "payload", mode="hash")
    # No leftover tmp files; sidecar present; read verifies.
    assert not list(tmp_path.glob("*.tmp"))
    assert si.read_trusted_state(target, mode="hash") == "payload"
    si._reset_cache_for_tests()


def test_db_migration_self_heals_duplicate_column(tmp_path: Path, monkeypatch) -> None:
    import sqlite3

    from halyard import db as dbmod

    db_file = tmp_path / "cache.db"
    monkeypatch.setattr(dbmod, "_DB_PATH", db_file)
    conn = dbmod.get_db()
    conn.close()
    # Simulate a crash that applied an ALTER but never bumped user_version.
    raw = sqlite3.connect(str(db_file))
    raw.execute(f"PRAGMA user_version = {dbmod._CURRENT_VERSION - 1}")
    raw.commit()
    raw.close()
    # Re-opening must not raise "duplicate column name" — it self-heals.
    conn2 = dbmod.get_db()
    assert conn2.execute("PRAGMA user_version").fetchone()[0] == dbmod._CURRENT_VERSION
    conn2.close()
