"""v2.52 — unwired-tool detection nudge in halyard doctor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from halyard import doctor
from halyard.collectors import codex_app, copilot, junie
from halyard.doctor import build_doctor_report, render_json


@pytest.fixture(autouse=True)
def _fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    # Default: no Codex history, nothing imported.
    monkeypatch.setattr(codex_app, "codex_history_present", lambda: False)
    monkeypatch.setattr(codex_app, "codex_imported_any", lambda: False)
    # Same for Copilot. Its collector binds ~/Library/.../workspaceStorage
    # and ~/.halyard/copilot-imported as module-level constants at import
    # time, so patching Path.home above cannot reach them — without these
    # stubs the nudge fires off the developer's real VS Code chat history.
    monkeypatch.setattr(copilot, "copilot_history_present", lambda: False)
    monkeypatch.setattr(copilot, "copilot_imported_any", lambda: False)
    # And Junie (v5.38). Its _INDEX_FILE is another module-level constant
    # bound to the real home at import, so this fixture's Path.home patch
    # cannot reach it either — the same reason Copilot needed stubbing.
    monkeypatch.setattr(junie, "junie_history_present", lambda: False)
    monkeypatch.setattr(junie, "junie_imported_any", lambda: False)
    return tmp_path


def _patch_which(monkeypatch: pytest.MonkeyPatch, *on_path: str) -> None:
    present = set(on_path)
    monkeypatch.setattr(
        doctor.shutil, "which", lambda b: f"/usr/local/bin/{b}" if b in present else None
    )


def _ids(report: object) -> set[str]:
    return {c.id for c in report.checks}  # type: ignore[attr-defined]


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_installed_zero_integration_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_which(monkeypatch, "cursor")
    report = build_doctor_report(tool="all")
    ids = _ids(report)
    assert "unwired.cursor" in ids
    assert "unwired.claude" not in ids  # not on PATH
    check = next(c for c in report.checks if c.id == "unwired.cursor")
    assert check.status == "warning"
    assert "halyard setup" in (check.fix or "")


def test_hooks_present_suppresses_nudge(monkeypatch: pytest.MonkeyPatch, _fake_home: Path) -> None:
    _patch_which(monkeypatch, "cursor")
    _write(
        _fake_home / ".cursor" / "hooks.json",
        {
            "version": 1,
            "hooks": {
                "beforeSubmitPrompt": [{"command": "/x/halyard cursor-session"}],
                "stop": [{"command": "/x/halyard cursor-hook"}],
            },
        },
    )
    assert "unwired.cursor" not in _ids(build_doctor_report(tool="all"))


def test_mcp_only_suppresses_nudge(monkeypatch: pytest.MonkeyPatch, _fake_home: Path) -> None:
    _patch_which(monkeypatch, "gemini")
    _write(
        _fake_home / ".gemini" / "settings.json",
        {"mcpServers": {"halyard": {"command": "/some/venv/bin/halyard", "args": ["mcp"]}}},
    )
    assert "unwired.gemini" not in _ids(build_doctor_report(tool="all"))


def test_absent_tool_no_nudge(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_which(monkeypatch)  # nothing on PATH
    ids = _ids(build_doctor_report(tool="all"))
    assert not any(i.startswith("unwired.") for i in ids)


def test_scoped_run_only_that_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_which(monkeypatch, "claude", "cursor")
    ids = _ids(build_doctor_report(tool="cursor"))
    assert "unwired.cursor" in ids
    assert "unwired.claude" not in ids  # scoped to cursor


def test_codex_history_unimported_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_which(monkeypatch)
    monkeypatch.setattr(codex_app, "codex_history_present", lambda: True)
    monkeypatch.setattr(codex_app, "codex_imported_any", lambda: False)
    report = build_doctor_report(tool="all")
    check = next(c for c in report.checks if c.id == "unwired.codex")
    assert check.status == "warning"
    assert check.fix == "halyard import-codex"


def test_codex_already_imported_no_nudge(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_which(monkeypatch)
    monkeypatch.setattr(codex_app, "codex_history_present", lambda: True)
    monkeypatch.setattr(codex_app, "codex_imported_any", lambda: True)
    assert "unwired.codex" not in _ids(build_doctor_report(tool="all"))


def test_codex_check_skipped_when_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_which(monkeypatch)
    monkeypatch.setattr(codex_app, "codex_history_present", lambda: True)
    monkeypatch.setattr(codex_app, "codex_imported_any", lambda: False)
    assert "unwired.codex" not in _ids(build_doctor_report(tool="claude"))


def test_unwired_warnings_preserve_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_which(monkeypatch, "claude", "cursor", "gemini")
    monkeypatch.setattr(codex_app, "codex_history_present", lambda: True)
    monkeypatch.setattr(codex_app, "codex_imported_any", lambda: False)
    report = build_doctor_report(tool="all")
    unwired = [c for c in report.checks if c.id.startswith("unwired.")]
    assert unwired  # the nudge fired
    # Contract: an unwired tool is never an error — it cannot, by
    # itself, flip the doctor exit code. (Other checks may error for
    # unrelated reasons in a bare environment; that is not this
    # feature's concern.)
    assert all(c.status == "warning" for c in unwired)


def test_unwired_ids_in_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_which(monkeypatch, "cursor")
    payload = json.loads(render_json(build_doctor_report(tool="all")))
    assert any(c["id"] == "unwired.cursor" for c in payload["checks"])


def test_mcp_registered_basename_match(_fake_home: Path) -> None:
    _write(
        _fake_home / ".claude.json",
        {"mcpServers": {"halyard": {"command": "/moved/venv/bin/halyard", "args": ["mcp"]}}},
    )
    assert doctor._mcp_registered("claude") is True
    _write(_fake_home / ".cursor" / "mcp.json", {"mcpServers": {"other": {"command": "x"}}})
    assert doctor._mcp_registered("cursor") is False
