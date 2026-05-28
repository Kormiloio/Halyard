"""Tests for VS Code task installation."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from halyard.cli import app
from halyard.cli_hooks import _do_install_vscode_tasks


def test_install_vscode_tasks_creates_record_task(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr("halyard.cli_hooks._halyard_exe", lambda: "/bin/halyard")  # type: ignore[attr-defined]

    path = _do_install_vscode_tasks()

    assert path == tmp_path / ".vscode" / "tasks.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    task = next(t for t in data["tasks"] if t["label"] == "Halyard: Record VS Code AI session")
    assert task["command"] == "/bin/halyard"
    assert task["args"][:3] == ["record-session", "--tool", "vscode"]
    assert {item["id"] for item in data["inputs"]} == {
        "halyardModel",
        "halyardMinutes",
        "halyardNote",
    }


def test_install_vscode_tasks_preserves_existing_tasks(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    vscode = tmp_path / ".vscode"
    vscode.mkdir()
    (vscode / "tasks.json").write_text(
        json.dumps(
            {
                "version": "2.0.0",
                "tasks": [{"label": "Existing", "type": "shell", "command": "true"}],
                "inputs": [{"id": "existing", "type": "promptString"}],
            }
        ),
        encoding="utf-8",
    )

    _do_install_vscode_tasks()
    _do_install_vscode_tasks()

    data = json.loads((vscode / "tasks.json").read_text(encoding="utf-8"))
    labels = [task["label"] for task in data["tasks"]]
    assert labels.count("Existing") == 1
    assert labels.count("Halyard: Record VS Code AI session") == 1
    input_ids = [item["id"] for item in data["inputs"]]
    assert "existing" in input_ids
    assert input_ids.count("halyardModel") == 1


def test_install_vscode_tasks_cli(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

    result = CliRunner().invoke(app, ["install-vscode-tasks"])

    assert result.exit_code == 0, result.output
    assert "VS Code Halyard task installed" in result.output
    assert (tmp_path / ".vscode" / "tasks.json").exists()
