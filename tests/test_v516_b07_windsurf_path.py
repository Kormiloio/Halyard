"""Regression tests for v5.16/B07 — Windsurf path-traversal arbitrary write.

`record_turn` builds a state-file path from the untrusted stdin
`trajectory_id`. A malicious id like "../../../../.claude/settings" must not
be allowed to escape ~/.halyard/ws-sessions/ and overwrite arbitrary
user-writable JSON. Benign ids must still produce a state file as before.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from halyard.collectors.windsurf import record_turn


@pytest.mark.parametrize(
    "malicious_tid",
    [
        "../../../../.claude/settings",
        "../escape",
        "..",
        ".",
        "/etc/passwd",
        "/absolute/path",
        "sub/dir/id",
        "a/../../b",
        "bad name",  # space is not in the safe charset
        "id$with;meta",
        "",
    ],
)
def test_b07_malicious_trajectory_id_writes_nothing_outside_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, malicious_tid: str
) -> None:
    home = tmp_path / "home"
    home.mkdir()

    # Plant a victim file the traversal payload would target.
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    victim = claude_dir / "settings.json"
    original = '{"trusted": true}'
    victim.write_text(original, encoding="utf-8")

    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(tmp_path)

    rc = record_turn({"trajectory_id": malicious_tid, "model_name": "m"}, is_start=True)

    # Returns cleanly without performing the write.
    assert rc == 0
    # The victim file is untouched.
    assert victim.read_text(encoding="utf-8") == original
    # No state file leaked anywhere outside the (possibly absent) root, and the
    # ws-sessions dir must not contain a smuggled entry.
    ws_dir = home / ".halyard" / "ws-sessions"
    if ws_dir.exists():
        assert list(ws_dir.glob("*.json")) == []
    # No JSON state file was written anywhere under home except the victim.
    stray = [p for p in home.rglob("*.json") if p != victim]
    assert stray == []


def test_b07_benign_trajectory_id_still_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(tmp_path)

    tid = "trajectory-123_abc.v2"
    rc = record_turn({"trajectory_id": tid, "model_name": "SWE-1.6"}, is_start=True)

    assert rc == 0
    state_file = home / ".halyard" / "ws-sessions" / f"{tid}.json"
    assert state_file.exists()
    # And it lives strictly inside the ws-sessions root.
    root = (home / ".halyard" / "ws-sessions").resolve()
    assert state_file.resolve().parent == root

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["user_count"] == 1
    assert state["assistant_count"] == 0
    assert state["model"] == "SWE-1.6"
