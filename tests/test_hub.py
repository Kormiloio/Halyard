"""Tests for halyard.hub — hub discovery and registration."""

from __future__ import annotations

from pathlib import Path

import pytest

from halyard.hub import clear_hub, find_hub, set_hub


@pytest.fixture()
def hub_pointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    pointer = tmp_path / "hub"
    monkeypatch.setattr("halyard.hub._HUB_POINTER", pointer)
    return pointer


def test_find_hub_returns_none_when_not_configured(hub_pointer: Path) -> None:
    assert find_hub() is None


def test_find_hub_returns_none_when_pointer_missing(hub_pointer: Path) -> None:
    assert not hub_pointer.exists()
    assert find_hub() is None


def test_set_hub_then_find_hub(hub_pointer: Path, tmp_path: Path) -> None:
    project = tmp_path / "myproject"
    project.mkdir()
    set_hub(project)
    assert hub_pointer.exists()
    assert find_hub() == project


def test_find_hub_returns_none_when_dir_missing(hub_pointer: Path, tmp_path: Path) -> None:
    missing = tmp_path / "gone"
    set_hub(missing)
    assert find_hub() is None


def test_clear_hub(hub_pointer: Path, tmp_path: Path) -> None:
    project = tmp_path / "p"
    project.mkdir()
    set_hub(project)
    assert find_hub() is not None
    clear_hub()
    assert find_hub() is None


def test_clear_hub_is_idempotent(hub_pointer: Path) -> None:
    clear_hub()  # no error when pointer doesn't exist
