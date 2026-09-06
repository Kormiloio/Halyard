"""Git-based project inference for automatic session attribution.

When a session is captured to the hub (no local halyard.toml found), this
module tries to determine which project the work belongs to by inspecting the
git remote of the working directory.

Priority:
  1. halyard.toml [project].slug — walk up from cwd until one is found
  2. Explicit mapping in ~/.halyard/repos.toml  ([repos] section, key = remote pattern)
  3. Auto-derived slug: git/<repo-name>

Users can promote auto-slugs to real project slugs with ``halyard link-repo``.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path

_REPOS_CONFIG = Path.home() / ".halyard" / "repos.toml"
# v5.39: recorded-path → slug. repos.toml matches on git *remotes*, which
# imported sessions do not carry — they record a directory. That directory
# may since have moved (an observed Codex session pointed at a path that no
# longer exists) or may be a repo's *parent* (Junie records the workspace
# root, which held four sibling repos). Neither yields a remote, so the git
# chain returns nothing and the session is unattributable forever.
_PATHS_CONFIG = Path.home() / ".halyard" / "paths.toml"

# v5.16/B09: a git object ref interpolated into a diff argv must be a bare
# hex SHA (4-40 chars). Anything else (e.g. "--output=/path", "-O<file>",
# "--ext-diff") is an attacker-supplied git option, not a ref — reject it.
_GIT_REF_RE = re.compile(r"^[0-9a-fA-F]{4,40}$")


def is_valid_git_ref(ref: str | None) -> bool:
    """True iff ``ref`` is a bare hex git object id (4-40 chars).

    Session-state JSON is attacker-influenceable; a ref that fails this
    check must never reach a git argv (argument-injection -> arbitrary
    file write via ``--output=``/``-O``/``--ext-diff``).
    """
    return bool(ref) and bool(_GIT_REF_RE.fullmatch(ref or ""))


def _slug_from_halyard_toml(cwd: Path) -> str | None:
    """Walk up from cwd looking for a halyard.toml with [project].slug."""
    for directory in (cwd, *cwd.parents):
        candidate = directory / "halyard.toml"
        if candidate.is_file():
            try:
                data = tomllib.loads(candidate.read_text(encoding="utf-8"))
                slug = data.get("project", {}).get("slug")
                if slug:
                    return str(slug)
            except (tomllib.TOMLDecodeError, OSError):
                pass
            return None  # found a halyard.toml but no slug — stop walking
    return None


def infer_project_with_source(cwd: Path) -> tuple[str | None, str | None]:
    """Return (slug, rung) inferred from cwd.

    rung records *which* chain step produced the slug so attribution
    confidence is not collapsed to a single "git":
      - "toml"     — halyard.toml [project].slug walk-up (high)
      - "repo-map" — explicit ~/.halyard/repos.toml mapping (high)
      - "git-auto" — derived git/<repo-name> slug (low)
    Both are None when nothing could be inferred.
    """
    slug = _slug_from_halyard_toml(cwd)
    if slug:
        return slug, "toml"

    remote = _git_remote_url(cwd)
    if remote is None:
        return None, None

    for pattern, mapped in _load_repos_config().items():
        if _remote_matches(remote, pattern):
            return mapped, "repo-map"

    repo_name = _extract_repo_name(remote)
    if repo_name:
        return f"git/{repo_name}", "git-auto"
    return None, None


def infer_project(cwd: Path) -> str | None:
    """Return a project slug inferred from cwd, or None (back-compat)."""
    return infer_project_with_source(cwd)[0]


def head_sha(cwd: Path) -> str | None:
    """Return the current HEAD SHA (short, 12 chars), or None.

    Returns None on detached HEAD with no commits, git not installed, or any
    subprocess error. Never raises.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        sha = result.stdout.strip()
        return sha or None
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError) as exc:
        from halyard.ai_log import log_diagnostic

        log_diagnostic(f"git_context: head_sha failed: {exc}")
        return None


def commits_in_window(cwd: Path, start: datetime, end: datetime) -> int | None:
    """Return the number of commits whose author date falls in [start, end].

    Returns None on any git error, timeout, or if cwd is not a git repo.
    Never raises.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(cwd),
                "log",
                f"--since={start.isoformat()}",
                f"--until={end.isoformat()}",
                "--oneline",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return None
        return sum(1 for line in result.stdout.splitlines() if line.strip())
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError) as exc:
        from halyard.ai_log import log_diagnostic

        log_diagnostic(f"git_context: commits_in_window failed: {exc}")
        return None


def numstat_delta(cwd: Path, sha_at_start: str) -> tuple[int, int] | None:
    """Return (lines_added, lines_removed) from git diff --numstat <sha_at_start> HEAD.

    Binary files (reported as '-') are skipped. Returns None on any git error,
    timeout, or non-zero exit. Never raises.
    """
    summary = numstat_summary(cwd, sha_at_start)
    if summary is None:
        return None
    added, removed, _files = summary
    return added, removed


def numstat_summary(cwd: Path, sha_at_start: str) -> tuple[int, int, int] | None:
    """Return (lines_added, lines_removed, files_touched) from git numstat.

    File names are read only to count changed rows and are never returned.
    Binary files count as touched files, but their line counts are ignored.
    """
    # v5.16/B09: validate the session-derived ref and place it after a literal
    # "--" so git cannot interpret it as an option (arbitrary file write).
    if not is_valid_git_ref(sha_at_start):
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "diff", "--numstat", sha_at_start, "HEAD", "--"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return None
        added = removed = 0
        files = 0
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            files += 1
            if parts[0] == "-" or parts[1] == "-":
                continue
            try:
                added += int(parts[0])
                removed += int(parts[1])
            except ValueError:
                continue
        return added, removed, files
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError) as exc:
        from halyard.ai_log import log_diagnostic

        log_diagnostic(f"git_context: numstat_summary failed: {exc}")
        return None


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
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError) as exc:
        from halyard.ai_log import log_diagnostic

        log_diagnostic(f"git_context: current_branch failed: {exc}")
        return None


def load_paths_config() -> dict[str, str]:
    """Read the recorded-path → slug map."""
    return _read_toml_map(_PATHS_CONFIG, "paths")


def register_path(path: str, project_slug: str) -> None:
    """Add or update one recorded-path → project-slug mapping."""
    import tomli_w

    existing = load_paths_config()
    existing[str(path)] = project_slug
    _PATHS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    _PATHS_CONFIG.write_bytes(tomli_w.dumps({"paths": dict(sorted(existing.items()))}).encode())


def project_for_path(path: str | None) -> str | None:
    """Resolve a recorded path to a slug via the explicit map.

    Exact match only. A prefix rule is tempting — it would let one entry
    cover a whole tree — but the paths that need mapping are precisely the
    ambiguous ones: an observed Junie workspace root contained four sibling
    repositories, so a prefix match would attribute all of their work to
    whichever slug was declared first. Guessing here moves billable tokens
    onto a project the evidence does not support, which is the failure v5.36
    was written to stop.
    """
    if not path:
        return None
    return load_paths_config().get(str(path))


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
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError) as exc:
        from halyard.ai_log import log_diagnostic

        log_diagnostic(f"git_context: _git_remote_url failed: {exc}")
        return None


def _read_toml_map(path: Path, section: str) -> dict[str, str]:
    """Read a ``[section]`` string→string table, degrading to {} on damage.

    Shared by the remote map and the path map (v5.39) so the two cannot
    drift in how they handle a corrupt file: a malformed config disables
    that attribution rung with a warning rather than aborting capture.
    """
    if not path.exists():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        table = data.get(section, {})
        return {k: v for k, v in table.items() if isinstance(k, str) and isinstance(v, str)}
    except tomllib.TOMLDecodeError as e:
        print(
            f"[halyard] Warning: {path} is not valid TOML — "
            f"attribution from it disabled. Run 'halyard doctor' to verify. ({e})",
            file=sys.stderr,
        )
        return {}
    except OSError:
        return {}


def _load_repos_config() -> dict[str, str]:
    return _read_toml_map(_REPOS_CONFIG, "repos")


def _write_repos_config(mapping: dict[str, str]) -> None:
    import tomli_w

    _REPOS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, dict[str, str]] = {"repos": dict(sorted(mapping.items()))}
    _REPOS_CONFIG.write_bytes(tomli_w.dumps(data).encode())


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
