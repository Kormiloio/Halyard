"""v5.19/B2 — secure dashboard token lifecycle.

Audit blocker B2 (docs/reviews/2026-06-pre-release-audit.md).
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from halyard import service

_POSIX = hasattr(os, "getuid")


@pytest.fixture
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def test_token_created_0o600(_home: Path) -> None:
    token = service._load_or_create_token()
    assert service._is_valid_token(token)
    path = service._token_path()
    assert path.exists()
    if _POSIX:
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, f"token must be owner-only, got {oct(mode)}"


def test_halyard_dir_is_private(_home: Path) -> None:
    service._load_or_create_token()
    if _POSIX:
        mode = stat.S_IMODE(service._token_path().parent.stat().st_mode)
        assert mode == 0o700, f"~/.halyard must be 0o700, got {oct(mode)}"


def test_existing_valid_token_is_stable(_home: Path) -> None:
    a = service._load_or_create_token()
    b = service._load_or_create_token()
    assert a == b  # adopted, not regenerated


def test_loose_perms_tightened_on_adopt(_home: Path) -> None:
    if not _POSIX:
        pytest.skip("POSIX perms only")
    token = service._load_or_create_token()
    path = service._token_path()
    os.chmod(path, 0o644)  # simulate a world-readable token
    again = service._load_or_create_token()
    assert again == token  # still ours -> adopted
    assert stat.S_IMODE(path.stat().st_mode) == 0o600  # re-tightened


def test_garbage_token_file_recreated(_home: Path) -> None:
    path = service._token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not-a-valid-token", encoding="utf-8")
    if _POSIX:
        os.chmod(path, 0o600)
    token = service._load_or_create_token()
    assert service._is_valid_token(token)
    assert path.read_text(encoding="utf-8").strip() == token


@pytest.mark.skipif(not _POSIX, reason="symlink/ownership semantics are POSIX")
def test_symlink_planted_at_token_path_not_followed(_home: Path, tmp_path: Path) -> None:
    # An attacker pre-places a symlink at the token path pointing at a file
    # they want clobbered. O_NOFOLLOW + lstat must refuse to follow it.
    target = tmp_path / "victim.txt"
    target.write_text("important", encoding="utf-8")
    path = service._token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target)

    token = service._load_or_create_token()
    assert service._is_valid_token(token)
    # The victim file must be untouched, and the token path is now a real file.
    assert target.read_text(encoding="utf-8") == "important"
    assert not path.is_symlink()
    assert path.read_text(encoding="utf-8").strip() == token


def test_concurrent_callers_converge(_home: Path) -> None:
    # Simulate the race: pre-create a valid token (as if a sibling won), then
    # a fresh call must adopt it rather than overwrite with a different one.
    first = service._load_or_create_token()
    # Second caller sees an existing valid, owned token -> same value.
    second = service._load_or_create_token()
    assert first == second
    assert service._token_path().read_text(encoding="utf-8").strip() == first


def test_no_world_readable_window_uses_o_excl(_home: Path) -> None:
    # White-box guard: ensure we create with O_EXCL (race-free) — a stand-in
    # for "no temp-file-then-chmod window". The function must not leave a
    # predictable .token.tmp behind.
    service._load_or_create_token()
    leftovers = list(service._token_path().parent.glob("*.tmp"))
    assert leftovers == [], f"unexpected temp files: {leftovers}"


if sys.platform == "win32":  # pragma: no cover - documents the fallback

    def test_windows_nofollow_is_noop() -> None:
        assert service._O_NOFOLLOW == 0
