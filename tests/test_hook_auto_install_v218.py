"""Test backfill for hook auto-install (v2.18 tasks 9.1-9.4)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from halyard.cli import _auto_install_detected_hooks, _do_install_hook_claude


def _settings(tmp_path: Path) -> Path:
    return tmp_path / ".claude" / "settings.json"


# ---------------------------------------------------------------------------
# 9.1: Fake $HOME with no ~/.claude/settings.json — file is created
# ---------------------------------------------------------------------------


def test_install_hook_claude_creates_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    assert not _settings(tmp_path).exists()
    _do_install_hook_claude(global_=True)

    assert _settings(tmp_path).exists()
    data = json.loads(_settings(tmp_path).read_text())
    assert "hooks" in data


# ---------------------------------------------------------------------------
# 9.2: _auto_install_detected_hooks writes expected hook entries
# ---------------------------------------------------------------------------


def test_auto_install_writes_claude_hooks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    def _which(binary: str) -> str | None:
        return f"/usr/local/bin/{binary}" if binary == "claude" else None

    with patch("shutil.which", side_effect=_which):
        _auto_install_detected_hooks()

    assert _settings(tmp_path).exists()
    hooks = json.loads(_settings(tmp_path).read_text()).get("hooks", {})
    assert len(hooks) >= 1


def test_auto_install_no_tools_detected_no_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    with patch("shutil.which", return_value=None):
        _auto_install_detected_hooks()

    assert not _settings(tmp_path).exists()


# ---------------------------------------------------------------------------
# 9.3: Existing settings file is preserved (other entries untouched)
# ---------------------------------------------------------------------------


def test_install_hook_claude_preserves_existing_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    path = _settings(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"theme": "dark", "fontSize": 14}))

    _do_install_hook_claude(global_=True)

    data = json.loads(path.read_text())
    assert data["theme"] == "dark"
    assert data["fontSize"] == 14
    assert "hooks" in data


# ---------------------------------------------------------------------------
# 9.4: Idempotent: running twice does not duplicate entries
# ---------------------------------------------------------------------------


def test_install_hook_claude_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    _do_install_hook_claude(global_=True)
    _do_install_hook_claude(global_=True)

    data = json.loads(_settings(tmp_path).read_text())
    for event, entries in data.get("hooks", {}).items():
        commands = [h.get("command") for entry in entries for h in entry.get("hooks", [])]
        assert len(commands) == len(set(commands)), f"Duplicate hook commands in event '{event}'"


# ---------------------------------------------------------------------------
# v2.31: Cross-file duplicate detection
# ---------------------------------------------------------------------------


def _write_hook_settings(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"type": "command", "command": "/bin/halyard cc-session"}]}
                    ],
                    "Stop": [{"hooks": [{"type": "command", "command": "/bin/halyard cc-hook"}]}],
                }
            }
        )
    )


def test_local_install_skipped_when_global_hook_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(project)

    _write_hook_settings(home / ".claude" / "settings.json")

    _do_install_hook_claude(global_=False)

    assert not (project / ".claude" / "settings.json").exists()


def test_global_install_skipped_when_local_hook_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(project)

    _write_hook_settings(project / ".claude" / "settings.json")

    _do_install_hook_claude(global_=True)

    assert not (home / ".claude" / "settings.json").exists()


def test_install_proceeds_when_other_file_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(project)

    _do_install_hook_claude(global_=False)

    settings = project / ".claude" / "settings.json"
    assert settings.exists()
    assert "hooks" in json.loads(settings.read_text())


def test_install_proceeds_when_other_file_has_no_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(project)

    global_settings = home / ".claude" / "settings.json"
    global_settings.parent.mkdir(parents=True, exist_ok=True)
    global_settings.write_text(json.dumps({"theme": "dark"}))

    _do_install_hook_claude(global_=False)

    local_settings = project / ".claude" / "settings.json"
    assert local_settings.exists()
    assert "hooks" in json.loads(local_settings.read_text())
