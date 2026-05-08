"""Tests for v2.10 guided setup."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from halyard.cli import app
from halyard.setup import resolve_selection


def test_resolve_selection_all_yes() -> None:
    selection = resolve_selection(
        all_tools=True,
        claude=False,
        cursor=False,
        gemini=False,
        yes=True,
    )
    assert selection.tools == ("claude", "cursor", "gemini")


def test_resolve_selection_yes_without_tool_flags_defaults_to_all() -> None:
    selection = resolve_selection(
        all_tools=False,
        claude=False,
        cursor=False,
        gemini=False,
        yes=True,
    )
    assert selection.tools == ("claude", "cursor", "gemini")


def test_resolve_selection_selected_tools() -> None:
    selection = resolve_selection(
        all_tools=False,
        claude=True,
        cursor=True,
        gemini=False,
        yes=True,
    )
    assert selection.tools == ("claude", "cursor")


def test_setup_all_yes_installs_all_tools(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[str, bool | None]] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "halyard.cli.install_hook",
        lambda global_=False: calls.append(("claude", global_)),
    )
    monkeypatch.setattr("halyard.cli.install_cursor_hook", lambda: calls.append(("cursor", None)))
    monkeypatch.setattr("halyard.cli.install_gemini_hook", lambda: calls.append(("gemini", None)))

    result = CliRunner().invoke(app, ["setup", "--all", "--yes"])

    assert result.exit_code == 0
    assert calls == [("claude", False), ("cursor", None), ("gemini", None)]
    assert "doctor --first-capture" in result.stdout


def test_setup_selected_tools(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.cli.install_hook", lambda global_=False: calls.append("claude"))
    monkeypatch.setattr("halyard.cli.install_cursor_hook", lambda: calls.append("cursor"))
    monkeypatch.setattr("halyard.cli.install_gemini_hook", lambda: calls.append("gemini"))

    result = CliRunner().invoke(app, ["setup", "--claude", "--cursor", "--yes"])

    assert result.exit_code == 0
    assert calls == ["claude", "cursor"]


def test_setup_global_claude_forwards_flag(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    calls: list[bool] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.cli.install_hook", lambda global_=False: calls.append(global_))

    result = CliRunner().invoke(app, ["setup", "--claude", "--global-claude", "--yes"])

    assert result.exit_code == 0
    assert calls == [True]


def test_setup_no_project_no_hub_guidance(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    result = CliRunner().invoke(app, ["setup", "--yes"])

    assert result.exit_code == 0
    assert "Capture has no destination" in result.stdout
    assert "halyard init" in result.stdout


def test_setup_installer_failure_exits_1_after_summary(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)

    def fail_install() -> None:
        raise PermissionError("settings.json")

    monkeypatch.setattr("halyard.cli.install_gemini_hook", fail_install)

    result = CliRunner().invoke(app, ["setup", "--gemini", "--yes"])

    assert result.exit_code == 1
    assert "Could not install Gemini CLI hooks" in result.stdout
    assert "Halyard Doctor" in result.stdout
    assert "doctor --first-capture" in result.stdout
