"""Git-based project inference for automatic session attribution.

When a session is captured to the hub (no local halyard.toml found), this
module tries to determine which project the work belongs to by inspecting the
git remote of the working directory.

Priority:
  1. Explicit mapping in ~/.halyard/repos.toml  ([repos] section, key = remote pattern)
  2. Auto-derived slug: git/<repo-name>

Users can promote auto-slugs to real project slugs with ``halyard link-repo``.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

_REPOS_CONFIG = Path.home() / ".halyard" / "repos.toml"


def infer_project(cwd: Path) -> str | None:
    """Return a project slug inferred from the git remote of cwd, or None."""
    remote = _git_remote_url(cwd)
    if remote is None:
        return None

    for pattern, slug in _load_repos_config().items():
        if _remote_matches(remote, pattern):
            return slug

    repo_name = _extract_repo_name(remote)
    return f"git/{repo_name}" if repo_name else None


def current_branch(cwd: Path) -> str | None:
    """Return the current git branch name for cwd, or None if not in a repo."""
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        branch = result.stdout.strip()
        return branch or None
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return None


def register_repo(remote_pattern: str, project_slug: str) -> None:
    """Add or update a remote-pattern → project-slug mapping."""
    existing = _load_repos_config()
    existing[remote_pattern] = project_slug
    _write_repos_config(existing)


def current_remote(cwd: Path | None = None) -> str | None:
    """Return the normalized origin remote URL for cwd (or CWD), or None."""
    return _git_remote_url(cwd or Path.cwd())


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _git_remote_url(cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return None


def _load_repos_config() -> dict[str, str]:
    if not _REPOS_CONFIG.exists():
        return {}
    try:
        data = tomllib.loads(_REPOS_CONFIG.read_text())
        repos = data.get("repos", {})
        return {k: v for k, v in repos.items() if isinstance(k, str) and isinstance(v, str)}
    except Exception:
        return {}


def _write_repos_config(mapping: dict[str, str]) -> None:
    _REPOS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[repos]"]
    for k, v in sorted(mapping.items()):
        lines.append(f'"{k}" = "{v}"')
    _REPOS_CONFIG.write_text("\n".join(lines) + "\n")


def _normalize_remote(url: str) -> str:
    """Reduce a git remote URL to host/path form, no protocol or .git suffix."""
    url = url.strip()
    for prefix in ("https://", "http://", "git://", "ssh://"):
        if url.startswith(prefix):
            url = url[len(prefix) :]
            break
    # git@github.com:user/repo → github.com/user/repo
    url = re.sub(r"^[^@]+@([^:]+):", r"\1/", url)
    if url.endswith(".git"):
        url = url[:-4]
    return url.rstrip("/")


def _remote_matches(remote: str, pattern: str) -> bool:
    remote_norm = _normalize_remote(remote)
    pattern_norm = _normalize_remote(pattern)
    if "*" not in pattern_norm:
        return remote_norm == pattern_norm
    regex = re.escape(pattern_norm).replace(r"\*", "[^/]*")
    return bool(re.fullmatch(regex, remote_norm))


def _extract_repo_name(url: str) -> str | None:
    parts = _normalize_remote(url).split("/")
    return parts[-1] if parts and parts[-1] else None
