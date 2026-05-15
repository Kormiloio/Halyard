"""v2.45 — cursor/gemini hook install de-dup regressions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from halyard import cli_hooks

_EXE = "/opt/halyard/bin/halyard"


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(cli_hooks, "_halyard_exe", lambda: _EXE)
    return tmp_path


# --- cursor ---------------------------------------------------------------


def test_cursor_collapses_stale_halyard_entries(tmp_path: Path) -> None:
    cfg = tmp_path / ".cursor" / "hooks.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {
                    "beforeSubmitPrompt": [
                        {"command": '"/bun" worker.cjs hook cursor session-init'},
                        {"command": "/usr/local/bin/halyard cursor-session"},
                        {"command": "/repo/.venv/bin/halyard cursor-session"},
                        {"command": "/private/tmp/dead/venv/bin/halyard cursor-session"},
                    ],
                    "stop": [
                        {"command": "/old/halyard cursor-hook"},
                    ],
                },
            }
        )
    )
    cli_hooks._do_install_hook_cursor()
    d = json.loads(cfg.read_text())
    bsp = d["hooks"]["beforeSubmitPrompt"]
    halyard = [e for e in bsp if cli_hooks._is_halyard_hook_cmd(e["command"])]
    assert len(halyard) == 1
    assert halyard[0]["command"] == f"{_EXE} cursor-session"
    # foreign bun entry preserved
    assert any("worker.cjs" in e["command"] for e in bsp)
    stop_halyard = [e for e in d["hooks"]["stop"] if cli_hooks._is_halyard_hook_cmd(e["command"])]
    assert len(stop_halyard) == 1
    assert stop_halyard[0]["command"] == f"{_EXE} cursor-hook"


def test_cursor_install_is_byte_idempotent(tmp_path: Path) -> None:
    cli_hooks._do_install_hook_cursor()
    cfg = tmp_path / ".cursor" / "hooks.json"
    first = cfg.read_text()
    cli_hooks._do_install_hook_cursor()
    assert cfg.read_text() == first  # true no-op on the second run


# --- gemini ---------------------------------------------------------------


def test_gemini_collapses_duplicate_blocks(tmp_path: Path) -> None:
    cfg = tmp_path / ".gemini" / "settings.json"
    cfg.parent.mkdir(parents=True)
    foreign = {"matcher": "*", "hooks": [{"type": "command", "command": "/other/tool run"}]}

    def hblock(cmd: str) -> dict:
        return {
            "matcher": "*",
            "hooks": [{"name": "halyard", "type": "command", "command": cmd}],
        }

    cfg.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        hblock("/a/halyard gc-session"),
                        foreign,
                        hblock("/b/.venv/bin/halyard gc-session"),
                    ],
                    "AfterModel": [hblock("/dead/halyard gc-model")],
                    "AfterAgent": [hblock("/a/halyard gc-hook")],
                }
            }
        )
    )
    cli_hooks._do_install_hook_gemini()
    d = json.loads(cfg.read_text())
    ss = d["hooks"]["SessionStart"]
    halyard_blocks = [
        b
        for b in ss
        if any(cli_hooks._is_halyard_hook_cmd(h.get("command", "")) for h in b["hooks"])
    ]
    assert len(halyard_blocks) == 1
    assert halyard_blocks[0]["hooks"][0]["command"] == f"{_EXE} gc-session"
    # foreign block preserved
    assert any(b is not None and b == foreign for b in ss)
    assert d["hooks"]["AfterModel"][-1]["hooks"][0]["command"] == f"{_EXE} gc-model"


def test_gemini_install_is_byte_idempotent(tmp_path: Path) -> None:
    cli_hooks._do_install_hook_gemini()
    cfg = tmp_path / ".gemini" / "settings.json"
    first = cfg.read_text()
    cli_hooks._do_install_hook_gemini()
    assert cfg.read_text() == first


def test_is_halyard_hook_cmd_does_not_match_foreign() -> None:
    assert cli_hooks._is_halyard_hook_cmd("/x/halyard cursor-session")
    assert cli_hooks._is_halyard_hook_cmd("halyard gc-hook")
    assert not cli_hooks._is_halyard_hook_cmd('"/bun" worker.cjs hook cursor')
    assert not cli_hooks._is_halyard_hook_cmd("")
