"""Integrity verification for ~/.halyard/ state files.

Opt-in via the ``state_integrity`` key in ``halyard.toml`` (or the
``HALYARD_STATE_INTEGRITY`` env override). Three tiers, with **exactly**
these guarantees — no more:

- ``"off"`` (default): pass-through. No integrity at all.
- ``"hash"``: a ``.sha256`` sidecar holds an *unkeyed* digest of the
  content. This detects accidental corruption and naive single-file
  edits. It is **NOT tamper-resistant**: anyone who can write the state
  file can also recompute and rewrite its ``.sha256`` sidecar. Use it
  for corruption detection only, never as a security control.
- ``"hmac"``: a ``.hmac`` sidecar holds ``HMAC-SHA256(key, content)``
  where ``key`` is a 32-byte secret at ``~/.halyard/integrity.key``
  (mode 0600). This detects tampering by any process that **cannot read
  the key file**. It is **NOT** a defense against a full local-account
  compromise: an attacker who can read ``~/.halyard/integrity.key`` can
  forge a valid sidecar. It raises the bar from "anyone who reads this
  open-source code" to "an attacker who can also read the 0600 key".

Verification failure raises :class:`IntegrityError`. Callers decide
fail-closed vs fail-open — :func:`read_active_project` and
:func:`find_hub` log and return ``None`` so the rest of Halyard keeps
running. ``hmac`` fails closed if the key is missing/unreadable: it never
silently downgrades to "unverified".
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import tomllib
from pathlib import Path
from typing import Literal, cast

IntegrityMode = Literal["off", "hash", "hmac"]

_VALID_MODES = ("off", "hash", "hmac")
# v5.19/B13: relative strength of each mode. The sidecar that exists on disk is
# a *trusted* signal (an attacker who can't read integrity.key cannot forge an
# .hmac sidecar); the resolved mode, by contrast, can come from
# attacker-controlled config reached via an untrusted pointer. Verification
# must never use a mode weaker than the file's sidecar implies.
_MODE_STRENGTH: dict[IntegrityMode, int] = {"off": 0, "hash": 1, "hmac": 2}
_KEY_PATH = Path.home() / ".halyard" / "integrity.key"

_DEFAULT_MODE: IntegrityMode = "off"
# Cached per process, keyed by resolved project directory. Keying by dir
# matters: a `hash`-mode project must not poison a later read for a
# different project (or a project_dir=None read such as find_hub()), which
# would raise spurious IntegrityErrors and silently disable hub discovery.
# CLI invocations are short-lived so stale reads are not a concern.
_MODE_CACHE: dict[str, IntegrityMode] = {}


class IntegrityError(Exception):
    """Raised when a tracked state file fails integrity verification."""


def _sidecar(path: Path, mode: IntegrityMode) -> Path:
    # Distinct suffixes so an unkeyed SHA-256 can never be mistaken for
    # an HMAC when the mode changes.
    suffix = ".hmac" if mode == "hmac" else ".sha256"
    return path.with_suffix(path.suffix + suffix)


def detect_sidecar_mode(path: Path) -> IntegrityMode | None:
    """Return the integrity mode implied by an existing sidecar, if any.

    Used for *global* state files (e.g. ``~/.halyard/active``) whose
    governing project — and therefore mode — would otherwise be derived
    from tamperable in-file content. If a sidecar exists, verification
    was enabled and must not be silently downgraded to ``off`` just
    because a (possibly tampered) path no longer resolves to a project
    with integrity configured. ``hmac`` wins over ``hash``.
    """
    if _sidecar(path, "hmac").exists():
        return "hmac"
    if _sidecar(path, "hash").exists():
        return "hash"
    return None


def _integrity_key(*, create: bool) -> bytes:
    """Return the 32-byte HMAC key.

    Read path (create=False): a missing/unreadable key is fatal — raise
    IntegrityError rather than silently downgrade to "unverified".
    Write path (create=True): generate and atomically create on first use.
    """
    if _KEY_PATH.exists():
        try:
            raw = _KEY_PATH.read_text(encoding="utf-8").strip()
            key = bytes.fromhex(raw)
        except (OSError, ValueError) as exc:
            raise IntegrityError(f"Integrity key unreadable: {_KEY_PATH}") from exc
        if len(key) < 16:
            raise IntegrityError(f"Integrity key too short: {_KEY_PATH}")
        return key
    if not create:
        raise IntegrityError(f"Missing integrity key: {_KEY_PATH}")
    _KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    _atomic_write(_KEY_PATH, key.hex() + "\n")
    return key


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
    if value in _VALID_MODES:
        return cast("IntegrityMode", value)
    return None


def current_mode(project_dir: Path | None = None) -> IntegrityMode:
    """Return the active integrity mode.

    Resolution order: explicit project_dir > HALYARD_STATE_INTEGRITY env
    override > cached value > default ("off"). The cache is process-local
    so hot paths (every hook fire) don't re-read halyard.toml.
    """
    env = os.environ.get("HALYARD_STATE_INTEGRITY")
    if env in _VALID_MODES:
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


def read_global_trusted_state(path: Path) -> str | None:
    """Read a *global* state file (e.g. ``~/.halyard/active``, ``~/.halyard/hub``).

    Global pointers are not owned by any project, so the resolved mode
    comes from the env override / process default only. If a sidecar
    already exists on disk, integrity was previously enabled and must
    not be silently downgraded to ``off`` — the sidecar mode wins over
    a default-off resolution. This mirrors the per-project pattern in
    :func:`halyard.reports.read_active_timer` and is the canonical entry
    point for any caller reading a global trusted-state file.

    Returns the file's contents on success, ``None`` if the file does
    not exist. Raises :class:`IntegrityError` on verification failure
    (callers decide fail-closed vs fail-open).
    """
    # The sidecar floor is enforced inside read_trusted_state (B13), so a
    # plain resolved mode is safe to pass — a stronger sidecar cannot be
    # silently downgraded.
    return read_trusted_state(path, mode=current_mode())


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
    # v5.19/B13: enforce the sidecar as a strength floor. The resolved mode can
    # be steered by an attacker (a forged ~/.halyard/active pointer → an
    # attacker-controlled halyard.toml with state_integrity="hash"/"off"), but
    # the .hmac sidecar on disk cannot be forged without integrity.key. If a
    # stronger sidecar exists than the resolved mode, verify with the stronger
    # scheme — never silently downgrade hmac → hash/off.
    sidecar_mode = detect_sidecar_mode(path)
    if sidecar_mode is not None and _MODE_STRENGTH[sidecar_mode] > _MODE_STRENGTH[active_mode]:
        active_mode = sidecar_mode
    content = path.read_text(encoding="utf-8")
    if active_mode == "off":
        return content
    if active_mode in ("hash", "hmac"):
        sidecar = _sidecar(path, active_mode)
        if not sidecar.exists():
            raise IntegrityError(f"Missing integrity sidecar for {path}")
        expected = sidecar.read_text(encoding="utf-8").strip()
        if active_mode == "hmac":
            key = _integrity_key(create=False)
            actual = hmac.new(key, content.encode("utf-8"), hashlib.sha256).hexdigest()
        else:
            actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(expected, actual):
            raise IntegrityError(f"Integrity mismatch for {path}")
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
    if active_mode in ("hash", "hmac"):
        # Write the sidecar (fsync'd) BEFORE swapping the data file in. A
        # crash then leaves an old file with an old (matching) sidecar, or a
        # new sidecar with the old file — the latter raises a clean
        # IntegrityError instead of silently trusting tampered content.
        if active_mode == "hmac":
            key = _integrity_key(create=True)
            digest = hmac.new(key, content.encode("utf-8"), hashlib.sha256).hexdigest()
        else:
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        _atomic_write(_sidecar(path, active_mode), digest + "\n")
    _atomic_write(path, content)


def _atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* via tmp + fsync + atomic rename."""
    from halyard.ai_log import atomic_replace

    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    atomic_replace(tmp, path)


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
