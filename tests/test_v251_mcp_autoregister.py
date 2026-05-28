"""v2.51 — MCP server auto-registration into client configs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from halyard import cli_hooks
from halyard.cli_hooks import (
    _MCP_CLIENTS,
    HookWriteError,
    _auto_install_detected_mcp,
    _do_install_mcp,
)


@pytest.fixture(autouse=True)
def _fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    # _MCP_CLIENTS is built at import time off the real home; rebuild it
    # against the fake home for the duration of the test.
    monkeypatch.setattr(
        cli_hooks,
        "_MCP_CLIENTS",
        {
            "claude": ("Claude Code", tmp_path / ".claude.json"),
            "cursor": ("Cursor", tmp_path / ".cursor" / "mcp.json"),
            "gemini": ("Gemini CLI", tmp_path / ".gemini" / "settings.json"),
        },
    )
    return tmp_path


def _cfg(client: str) -> Path:
    return cli_hooks._MCP_CLIENTS[client][1]


def test_creates_config_when_absent() -> None:
    assert not _cfg("cursor").exists()
    _do_install_mcp("cursor")
    data = json.loads(_cfg("cursor").read_text(encoding="utf-8"))
    entry = data["mcpServers"]["halyard"]
    assert entry["args"] == ["mcp"]
    assert isinstance(entry["command"], str) and entry["command"]


def test_preserves_foreign_servers() -> None:
    p = _cfg("cursor")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"mcpServers": {"claude-mem": {"command": "x"}}}), encoding="utf-8")
    _do_install_mcp("cursor")
    servers = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]
    assert servers["claude-mem"] == {"command": "x"}
    assert servers["halyard"]["args"] == ["mcp"]


def test_preserves_other_top_level_keys() -> None:
    p = _cfg("claude")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"theme": "dark", "projects": {"a": 1}}), encoding="utf-8")
    _do_install_mcp("claude")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    assert data["projects"] == {"a": 1}
    assert data["mcpServers"]["halyard"]["args"] == ["mcp"]


def test_idempotent_and_byte_stable() -> None:
    _do_install_mcp("gemini")
    first = _cfg("gemini").read_text(encoding="utf-8")
    _do_install_mcp("gemini")
    second = _cfg("gemini").read_text(encoding="utf-8")
    assert first == second
    servers = json.loads(second)["mcpServers"]
    assert list(servers) == ["halyard"]


def test_stale_exe_path_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_hooks, "_halyard_exe", lambda: "/old/venv/bin/halyard")
    _do_install_mcp("cursor")
    monkeypatch.setattr(cli_hooks, "_halyard_exe", lambda: "/new/venv/bin/halyard")
    _do_install_mcp("cursor")
    servers = json.loads(_cfg("cursor").read_text(encoding="utf-8"))["mcpServers"]
    assert servers["halyard"]["command"] == "/new/venv/bin/halyard"


def test_refuses_non_object_config() -> None:
    p = _cfg("cursor")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('["not", "an", "object"]', encoding="utf-8")
    with pytest.raises(HookWriteError):
        _do_install_mcp("cursor")
    assert p.read_text(encoding="utf-8") == '["not", "an", "object"]'  # untouched


def test_refuses_non_object_mcpservers() -> None:
    p = _cfg("gemini")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"mcpServers": "oops"}), encoding="utf-8")
    with pytest.raises(HookWriteError):
        _do_install_mcp("gemini")


def test_auto_install_only_detected_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli_hooks.shutil,
        "which",
        lambda b: f"/usr/local/bin/{b}" if b == "cursor" else None,
    )
    _auto_install_detected_mcp()
    assert _cfg("cursor").exists()
    assert not _cfg("claude").exists()
    assert not _cfg("gemini").exists()


def test_client_paths_are_documented_files(_fake_home: Path) -> None:
    assert _MCP_CLIENTS  # import-time map exists
    assert _cfg("claude") == _fake_home / ".claude.json"
    assert _cfg("cursor") == _fake_home / ".cursor" / "mcp.json"
    assert _cfg("gemini") == _fake_home / ".gemini" / "settings.json"
