"""Tests for `halyard init` (task 2.3)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from halyard.cli import app

runner = CliRunner()


def test_init_creates_all_files(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0, result.output

    assert (tmp_path / "halyard.toml").exists()
    assert (tmp_path / "clients.toml").exists()
    assert (tmp_path / "projects.toml").exists()
    assert (tmp_path / "time.timeclock").exists()
    assert (tmp_path / "ai-sessions.log").exists()
    assert (tmp_path / "invoices").is_dir()
    assert (tmp_path / ".gitignore").exists()


def test_init_halyard_toml_content(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    runner.invoke(app, ["init"])

    content = (tmp_path / "halyard.toml").read_text(encoding="utf-8")
    assert "[business]" in content
    assert "[invoicing]" in content
    assert "counter = 0" in content


def test_init_prints_next_steps(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    result = runner.invoke(app, ["init"])

    assert "halyard.toml" in result.output
    assert "clients.toml" in result.output
    assert "halyard" in result.output


def test_init_existing_project_exits_nonzero(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    (tmp_path / "halyard.toml").write_text("[business]\nname = 'Test'\n", encoding="utf-8")

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 1
    assert "already exists" in result.output


def test_init_existing_project_writes_no_files(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    (tmp_path / "halyard.toml").write_text("[business]\nname = 'Test'\n", encoding="utf-8")

    runner.invoke(app, ["init"])

    assert not (tmp_path / "clients.toml").exists()
    assert not (tmp_path / "projects.toml").exists()


def test_init_creates_gitignore_when_missing(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0, result.output
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".halyard-cache/" in content
    assert ".DS_Store" in content


def test_init_preserves_existing_gitignore(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    existing = "# Python\n__pycache__/\ndist/\n"
    (tmp_path / ".gitignore").write_text(existing, encoding="utf-8")

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0, result.output
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert content.startswith(existing)
    assert "__pycache__/" in content
    assert "dist/" in content
    assert ".halyard-cache/" in content
    assert content.count(".halyard-cache/") == 1


# ---------------------------------------------------------------------------
# L-5: .gitignore must include .halyard/ to prevent accidental commit of
#       user-local logs (quarantine.log, unattributed.log, active, cc-session)
# ---------------------------------------------------------------------------


def test_init_gitignore_includes_halyard_dir(tmp_path: Path, monkeypatch: object) -> None:
    """halyard init must add .halyard/ to .gitignore (L-5 fix)."""
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0, result.output
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".halyard/" in content
