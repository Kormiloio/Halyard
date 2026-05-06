"""Smoke tests for the CLI surface.

These do not exercise behavior — that's what the v0 task tests will do. They
just guarantee that the CLI app constructs and exposes the expected commands.
"""
from __future__ import annotations

from typer.testing import CliRunner

from halyard.cli import app

runner = CliRunner()


def test_help_runs() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Halyard" in result.stdout or "halyard" in result.stdout


def test_v0_commands_registered() -> None:
    result = runner.invoke(app, ["--help"])
    for cmd in ("init", "log", "start", "stop", "invoice"):
        assert cmd in result.stdout, f"command {cmd!r} not registered"
