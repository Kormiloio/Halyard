"""Tests for v3.0 outcomes feature flag (`outcomes_config.py`)."""

from __future__ import annotations

from pathlib import Path

from halyard.outcomes_config import (
    outcomes_enabled,
    read_outcomes_config,
    shell_history_enabled,
)


def test_default_outcomes_enabled_when_no_toml(tmp_path: Path) -> None:
    assert outcomes_enabled(tmp_path) is True


def test_default_shell_history_disabled_when_no_toml(tmp_path: Path) -> None:
    assert shell_history_enabled(tmp_path) is False


def test_explicit_disable(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[outcomes]\nenabled = false\n")
    assert outcomes_enabled(tmp_path) is False


def test_explicit_shell_history_enable(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text(
        "[outcomes]\nenabled = true\nshell_history = true\n"
    )
    assert shell_history_enabled(tmp_path) is True


def test_garbage_value_keeps_defaults(tmp_path: Path) -> None:
    """Non-boolean values are ignored — the documented contract is bool-only."""
    (tmp_path / "halyard.toml").write_text(
        "[outcomes]\nenabled = \"yes\"\nshell_history = 1\n"
    )
    cfg = read_outcomes_config(tmp_path)
    assert cfg["enabled"] is True  # default
    assert cfg["shell_history"] is False  # default


def test_malformed_toml_returns_defaults(tmp_path: Path) -> None:
    """A malformed halyard.toml must not crash — fall back to defaults."""
    (tmp_path / "halyard.toml").write_text("not [valid toml at all")
    cfg = read_outcomes_config(tmp_path)
    assert cfg["enabled"] is True
    assert cfg["shell_history"] is False
