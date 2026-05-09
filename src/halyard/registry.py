"""Project registry — tracks known Halyard project directories.

The registry is a plain-text file at ~/.halyard/projects, one absolute path
per line. It is the primary discovery source for multi-project commands such
as `halyard db sync`. CWD walk-up and hub discovery are fallbacks.
"""

from __future__ import annotations

from pathlib import Path

REGISTRY_PATH = Path.home() / ".halyard" / "projects"
_HEADER = "# Halyard project registry — one absolute path per line\n"


def register_project(path: Path) -> None:
    """Append path to the registry if not already present. Idempotent."""
    resolved = str(path.resolve())
    existing = _read_raw_paths()
    if resolved not in existing:
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not REGISTRY_PATH.exists():
            REGISTRY_PATH.write_text(_HEADER)
        with REGISTRY_PATH.open("a") as f:
            f.write(resolved + "\n")


def read_registry() -> list[Path]:
    """Return registered paths that still exist and contain halyard.toml.

    Paths that no longer exist or lack halyard.toml are silently skipped here;
    callers that want to warn the user should check against _read_raw_paths().
    """
    result: list[Path] = []
    for raw in _read_raw_paths():
        p = Path(raw)
        if p.exists() and (p / "halyard.toml").exists():
            result.append(p)
    return result


def forget_project(path: Path) -> bool:
    """Remove path from the registry. Returns True if it was present."""
    resolved = str(path.resolve())
    if resolved not in _read_raw_paths():
        return False
    kept: list[str] = []
    for line in REGISTRY_PATH.read_text().splitlines(keepends=True):
        if line.strip() == resolved:
            continue
        kept.append(line)
    REGISTRY_PATH.write_text("".join(kept))
    return True


def add_project(path: Path) -> bool:
    """Explicitly register an existing Halyard project directory.

    Returns False if the path doesn't exist or lacks halyard.toml.
    """
    resolved = path.resolve()
    if not resolved.exists() or not (resolved / "halyard.toml").exists():
        return False
    register_project(resolved)
    return True


def stale_paths() -> list[Path]:
    """Return registered paths that no longer exist or lack halyard.toml."""
    result: list[Path] = []
    for raw in _read_raw_paths():
        p = Path(raw)
        if not p.exists() or not (p / "halyard.toml").exists():
            result.append(p)
    return result


def _read_raw_paths() -> list[str]:
    if not REGISTRY_PATH.exists():
        return []
    paths: list[str] = []
    for line in REGISTRY_PATH.read_text().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            paths.append(stripped)
    return paths
