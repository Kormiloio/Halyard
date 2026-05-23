"""Tests for Claude Code client surface detection and AiSession serialization."""

from __future__ import annotations

from datetime import datetime

from halyard.ai_log import AiSession
from halyard.collectors.claude_code_surface import detect_surface


def test_detect_surface_returns_cli_for_terminal_env(monkeypatch) -> None:
    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
    monkeypatch.delenv("__CFBundleIdentifier", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")

    assert detect_surface() == "cli"


def test_detect_surface_returns_desktop_for_bundle_id(monkeypatch) -> None:
    monkeypatch.setenv("__CFBundleIdentifier", "com.anthropic.claude")
    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")

    assert detect_surface() == "desktop"


def test_detect_surface_returns_ide_for_vscode(monkeypatch) -> None:
    monkeypatch.setenv("TERM_PROGRAM", "vscode")
    monkeypatch.delenv("__CFBundleIdentifier", raising=False)

    assert detect_surface() == "ide"


def test_detect_surface_returns_unknown_when_signals_are_missing(monkeypatch) -> None:
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.delenv("__CFBundleIdentifier", raising=False)
    monkeypatch.setenv("TERM", "")
    monkeypatch.setattr("halyard.collectors.claude_code_surface.sys.stdin.isatty", lambda: False)

    assert detect_surface() == "unknown"


def test_ai_session_round_trips_client_surface() -> None:
    session = AiSession(
        start=datetime.now(),
        end=datetime.now(),
        tool="claude-code",
        model="claude-sonnet-4-6",
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        client_surface="cli",
    )
    line = session.to_log_line()
    parsed = AiSession.from_log_line(line)

    assert parsed is not None
    assert parsed.client_surface == "cli"


def test_old_log_line_parses_without_client_surface() -> None:
    old_line = (
        "s 2026-05-01T00:00:00 2026-05-01T00:01:00 claude-code claude-sonnet-4-6 10 10 0.0000"
    )
    parsed = AiSession.from_log_line(old_line)

    assert parsed is not None
    assert parsed.client_surface is None
