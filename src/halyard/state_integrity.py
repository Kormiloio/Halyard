"""Integrity verification for ~/.halyard/ state files (phase 1).

Opt-in via the ``state_integrity`` key in ``halyard.toml``.

- ``"off"`` (default): pass-through; no overhead, no sidecar files.
- ``"hash"``: each tracked file has a ``.sha256`` sidecar holding the hex
  digest of its content. Reads verify; writes refresh.

Tampering with a tracked state file out of band causes the next read to
raise :class:`IntegrityError`. Callers decide whether to fail closed or
fail open — :func:`read_active_project` and :func:`find_hub` log the
error and return ``None`` so the rest of Halyard keeps running.

Phase 2 will add an ``"hmac"`` mode with a per-user key for tamper
detection that resists local-account attacks.
"""

from __future__ import annotations

import hashlib
import os
import tomllib
from pathlib import Path
from typing import Literal, cast

IntegrityMode = Literal["off", "hash"]

_DEFAULT_MODE: IntegrityMode = "off"
_MODE_CACHE: IntegrityMode | None = None


class IntegrityError(Exception):
    """Raised when a tracked state file fails integrity verification."""


def _sidecar(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".sha256")


def _read_mode_from_toml(project_dir: Path) -> IntegrityMode | None:
    """Read state_integrity from project_dir/halyard.toml, or None if absent."""
    toml_path = project_dir / "halyard.toml"
    if not toml_path.exists():
        return None
    try:
        with toml_path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    value = data.get("state_integrity")
    if value in ("off", "hash"):
        return cast("IntegrityMode", value)
    return None


def current_mode(project_dir: Path | None = None) -> IntegrityMode:
    """Return the active integrity mode.

    Resolution order: explicit project_dir > HALYARD_STATE_INTEGRITY env
    override > cached value > default ("off"). The cache is process-local
    so hot paths (every hook fire) don't re-read halyard.toml.
    """
    global _MODE_CACHE
    env = os.environ.get("HALYARD_STATE_INTEGRITY")
    if env in ("off", "hash"):
        return cast("IntegrityMode", env)
    if project_dir is not None:
        mode = _read_mode_from_toml(project_dir)
        if mode is not None:
            _MODE_CACHE = mode
            return mode
    if _MODE_CACHE is not None:
        return _MODE_CACHE
    return _DEFAULT_MODE


def _reset_cache_for_tests() -> None:
    """Test helper: clear the cached mode so subsequent calls re-read config."""
    global _MODE_CACHE
    _MODE_CACHE = None


def read_trusted_state(path: Path, *, mode: IntegrityMode | None = None) -> str | None:
    """Read a state file with integrity verification per ``mode``.

    Returns the file's contents on success, or ``None`` if the file does
    not exist (a missing file is not a tampering signal — it's just
    absent state). Raises :class:`IntegrityError` if hash verification
    fails.
    """
    if not path.exists():
        return None
    active_mode = mode if mode is not None else current_mode()
    content = path.read_text(encoding="utf-8")
    if active_mode == "off":
        return content
    if active_mode == "hash":
        sidecar = _sidecar(path)
        if not sidecar.exists():
            raise IntegrityError(f"Missing integrity sidecar for {path}")
        expected = sidecar.read_text(encoding="utf-8").strip()
        actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if expected != actual:
            raise IntegrityError(f"Hash mismatch for {path}")
        return content
    return content  # pragma: no cover - exhaustive Literal


def write_trusted_state(path: Path, content: str, *, mode: IntegrityMode | None = None) -> None:
    """Write *content* to *path* and refresh its integrity sidecar.

    Uses a tmp-then-rename pattern to keep the file write atomic. The
    sidecar is written last so a reader observing an updated file with
    a stale sidecar will get a clean IntegrityError rather than silent
    acceptance.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    active_mode = mode if mode is not None else current_mode()
    if active_mode == "hash":
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        _sidecar(path).write_text(digest + "\n", encoding="utf-8")


def verify_all(paths: list[Path]) -> tuple[bool, Path | None]:
    """Verify every path in ``paths`` under the current mode.

    Returns ``(True, None)`` if all paths verify (or the mode is off);
    ``(False, first_failure)`` if any path raises IntegrityError.
    """
    if current_mode() == "off":
        return True, None
    for p in paths:
        try:
            read_trusted_state(p)
        except IntegrityError:
            return False, p
    return True, None
