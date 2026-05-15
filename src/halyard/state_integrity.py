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
# Cached per process, keyed by resolved project directory. Keying by dir
# matters: a `hash`-mode project must not poison a later read for a
# different project (or a project_dir=None read such as find_hub()), which
# would raise spurious IntegrityErrors and silently disable hub discovery.
# CLI invocations are short-lived so stale reads are not a concern.
_MODE_CACHE: dict[str, IntegrityMode] = {}


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
    env = os.environ.get("HALYARD_STATE_INTEGRITY")
    if env in ("off", "hash"):
        return cast("IntegrityMode", env)
    if project_dir is not None:
        key = str(project_dir.resolve())
        cached = _MODE_CACHE.get(key)
        if cached is not None:
            return cached
        mode = _read_mode_from_toml(project_dir)
        if mode is not None:
            _MODE_CACHE[key] = mode
            return mode
    return _DEFAULT_MODE


def _reset_cache_for_tests() -> None:
    """Test helper: clear the cached mode so subsequent calls re-read config."""
    _MODE_CACHE.clear()


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

    Both the data file and its sidecar are written via tmp + fsync +
    atomic rename. The sidecar is committed first, so a crash mid-write
    leaves the pair mismatched and the next read raises a clean
    IntegrityError rather than silently trusting stale content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    active_mode = mode if mode is not None else current_mode()
    if active_mode == "hash":
        # Write the sidecar (fsync'd) BEFORE swapping the data file in. A
        # crash then leaves an old file with an old (matching) sidecar, or a
        # new sidecar with the old file — the latter raises a clean
        # IntegrityError instead of silently trusting tampered content.
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        _atomic_write(_sidecar(path), digest + "\n")
    _atomic_write(path, content)


def _atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* via tmp + fsync + atomic rename."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


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
