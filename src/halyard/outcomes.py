"""v2.24 outcome metadata — PR resolution, outcome reporting, manual attribution."""

from __future__ import annotations

import json
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from halyard.ai_log import AiSession, locked_file, parse_sessions, session_hash

# ---------------------------------------------------------------------------
# PR resolution via gh
# ---------------------------------------------------------------------------

_GH_TIMEOUT = 10  # seconds
_CACHE_TTL_HOURS = 1


def gh_available() -> bool:
    """Return True if the `gh` CLI is installed and accessible."""
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def fetch_prs_for_branch(
    branch: str,
    remote: str | None = None,
) -> list[dict]:  # type: ignore[type-arg]
    """Run `gh pr list --head <branch>` and return parsed JSON rows.

    Returns an empty list if gh is unavailable or the call fails.
    """
    cmd = [
        "gh",
        "pr",
        "list",
        "--head",
        branch,
        "--json",
        "number,state,mergedAt,url,createdAt,baseRefName",
        "--limit",
        "5",
    ]
    if remote:
        # Extract owner/repo from remote URL for --repo flag
        repo = _remote_to_repo(remote)
        if repo:
            cmd += ["--repo", repo]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT,
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else []
    except (OSError, FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []


def _remote_to_repo(remote: str) -> str | None:
    """Convert a git remote URL to owner/repo form for gh --repo."""
    remote = remote.strip()
    # git@github.com:owner/repo.git
    if remote.startswith("git@"):
        parts = remote.split(":")
        if len(parts) == 2:
            path = parts[1].removesuffix(".git")
            return path or None
    # https://github.com/owner/repo.git
    for prefix in ("https://github.com/", "http://github.com/"):
        if remote.startswith(prefix):
            path = remote[len(prefix) :].removesuffix(".git")
            return path or None
    return None


def _normalize_pr_ref(number: int, remote: str | None) -> str:
    """Return a canonical pr_ref string like owner/repo#42."""
    if remote:
        repo = _remote_to_repo(remote)
        if repo:
            return f"{repo}#{number}"
    return f"#{number}"


def _best_pr_for_session(
    session: AiSession,
    prs: list[dict],  # type: ignore[type-arg]
) -> dict | None:  # type: ignore[type-arg]
    """Pick the PR whose creation date is closest to session end time."""
    if not prs:
        return None
    best = None
    best_delta: timedelta | None = None
    for pr in prs:
        created_str = pr.get("createdAt", "")
        with suppress(ValueError, TypeError):
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            if created.tzinfo is not None:
                created = created.astimezone(UTC).replace(tzinfo=None)
            delta = abs(session.end - created)
            if best_delta is None or delta < best_delta:
                best = pr
                best_delta = delta
    return best


# ---------------------------------------------------------------------------
# pr_cache SQLite helpers
# ---------------------------------------------------------------------------


def _cache_get(
    conn,  # type: ignore[no-untyped-def]
    cache_key: str,
) -> list[dict] | None:  # type: ignore[type-arg]
    """Return cached PR list if fresher than TTL, else None."""
    row = conn.execute(
        "SELECT payload, fetched_at FROM pr_cache WHERE cache_key = ?",
        (cache_key,),
    ).fetchone()
    if row is None:
        return None
    fetched_at_str: str = row["fetched_at"]
    with suppress(ValueError):
        fetched_at = datetime.fromisoformat(fetched_at_str)
        if datetime.now() - fetched_at < timedelta(hours=_CACHE_TTL_HOURS):
            return json.loads(row["payload"])  # type: ignore[no-any-return]
    return None


def _cache_set(
    conn,  # type: ignore[no-untyped-def]
    cache_key: str,
    prs: list[dict],  # type: ignore[type-arg]
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO pr_cache (cache_key, payload, fetched_at)
        VALUES (?, ?, ?)
        """,
        (cache_key, json.dumps(prs), datetime.now().isoformat()),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Resolution algorithm
# ---------------------------------------------------------------------------


@dataclass
class ResolutionResult:
    session_hash: str
    pr_ref: str | None
    pr_state: str
    resolved_at: str


def resolve_sessions(
    project_dir: Path,
    sessions: list[AiSession],
    *,
    since: date | None = None,
    project_slug: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> list[ResolutionResult]:
    """Resolve sessions to PR refs via gh. Write amendment records unless dry_run.

    Returns the list of ResolutionResults (all sessions that were processed).
    """
    from halyard.db import get_db
    from halyard.git_context import current_remote

    cutoff = since or (date.today() - timedelta(days=30))
    remote = current_remote(project_dir)

    candidates = [
        s
        for s in sessions
        if s.start.date() >= cutoff
        and s.branch is not None
        and (project_slug is None or s.project == project_slug)
        and (force or s.pr_ref is None)
    ]

    if not candidates:
        return []

    conn = get_db()
    results: list[ResolutionResult] = []

    try:
        # Group by branch to minimise gh calls
        by_branch: dict[str, list[AiSession]] = {}
        for s in candidates:
            by_branch.setdefault(s.branch or "", []).append(s)  # type: ignore[arg-type]

        for branch, branch_sessions in by_branch.items():
            cache_key = f"{remote or ''}:{branch}"
            prs = _cache_get(conn, cache_key)
            if prs is None:
                prs = fetch_prs_for_branch(branch, remote)
                _cache_set(conn, cache_key, prs)

            for s in branch_sessions:
                best = _best_pr_for_session(s, prs)
                if best:
                    pr_ref = _normalize_pr_ref(best["number"], remote)
                    raw_state = best.get("state", "open").lower()
                    pr_state = raw_state if raw_state in {"merged", "closed", "open"} else "open"
                else:
                    pr_ref = None
                    pr_state = "none"

                resolved_at = datetime.now().isoformat(timespec="seconds")
                result = ResolutionResult(
                    session_hash=_session_line_hash(project_dir, s),
                    pr_ref=pr_ref,
                    pr_state=pr_state,
                    resolved_at=resolved_at,
                )
                results.append(result)

                if not dry_run:
                    _write_amendment(project_dir, result)
                    _upsert_outcome(conn, result)

        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    return results


def _session_line_hash(project_dir: Path, session: AiSession) -> str:
    """Reconstruct the session hash from a parsed AiSession.

    session_hash() operates on raw log lines. We approximate by serializing
    the session back to its log line and hashing that.
    """
    return session_hash(session.to_log_line())


def _write_amendment(project_dir: Path, result: ResolutionResult) -> None:
    log_path = project_dir / "ai-sessions.log"
    if not log_path.exists():
        return
    parts = [f"a {result.session_hash}"]
    if result.pr_ref:
        parts.append(f"pr_ref={result.pr_ref}")
    parts.append(f"pr_state={result.pr_state}")
    parts.append(f"outcome_resolved_at={result.resolved_at}")
    line = " ".join(parts)
    with locked_file(log_path, "a") as f:
        f.write(line + "\n")


def _upsert_outcome(conn, result: ResolutionResult) -> None:  # type: ignore[no-untyped-def]
    conn.execute(
        """
        INSERT OR REPLACE INTO outcomes (session_id, pr_ref, pr_state, resolved_at)
        VALUES (?, ?, ?, ?)
        """,
        (result.session_hash, result.pr_ref, result.pr_state, result.resolved_at),
    )


# ---------------------------------------------------------------------------
# Outcome report
# ---------------------------------------------------------------------------


@dataclass
class OutcomeBucket:
    label: str
    session_count: int
    total_cost: float
    trust: str | None  # "captured", None


def outcome_report(
    sessions: list[AiSession],
    *,
    since: date | None = None,
    project_slug: str | None = None,
) -> list[OutcomeBucket]:
    """Return sessions bucketed by outcome state."""
    cutoff = since or (date.today() - timedelta(days=30))
    filtered = [
        s
        for s in sessions
        if s.start.date() >= cutoff and (project_slug is None or s.project == project_slug)
    ]

    buckets: dict[str, list[AiSession]] = {
        "merged": [],
        "open": [],
        "closed": [],
        "none": [],
        "unsynced": [],
    }
    for s in filtered:
        if s.pr_state == "merged":
            buckets["merged"].append(s)
        elif s.pr_state == "open":
            buckets["open"].append(s)
        elif s.pr_state == "closed":
            buckets["closed"].append(s)
        elif s.pr_state == "none":
            buckets["none"].append(s)
        else:
            buckets["unsynced"].append(s)

    return [
        OutcomeBucket(
            label="Shipped (PR merged)",
            session_count=len(buckets["merged"]),
            total_cost=sum(s.cost_usd for s in buckets["merged"]),
            trust="captured",
        ),
        OutcomeBucket(
            label="In-flight (PR open)",
            session_count=len(buckets["open"]),
            total_cost=sum(s.cost_usd for s in buckets["open"]),
            trust="captured",
        ),
        OutcomeBucket(
            label="Abandoned (PR closed)",
            session_count=len(buckets["closed"]),
            total_cost=sum(s.cost_usd for s in buckets["closed"]),
            trust="captured",
        ),
        OutcomeBucket(
            label="No PR detected",
            session_count=len(buckets["none"]),
            total_cost=sum(s.cost_usd for s in buckets["none"]),
            trust="captured",
        ),
        OutcomeBucket(
            label="Not synced",
            session_count=len(buckets["unsynced"]),
            total_cost=sum(s.cost_usd for s in buckets["unsynced"]),
            trust=None,
        ),
    ]


# ---------------------------------------------------------------------------
# Manual attribution
# ---------------------------------------------------------------------------


def attribute_session(
    project_dir: Path,
    session_id_prefix: str,
    pr_ref_raw: str,
) -> tuple[bool, str]:
    """Manually attribute a session to a PR ref.

    Returns (success, message).
    """
    from halyard.git_context import current_remote

    sessions = parse_sessions(project_dir)
    matched = [
        s for s in sessions if _session_line_hash(project_dir, s).startswith(session_id_prefix)
    ]
    if not matched:
        return False, f"No session found with ID starting '{session_id_prefix}'"
    if len(matched) > 1:
        return False, f"Ambiguous: {len(matched)} sessions match '{session_id_prefix}'"

    session = matched[0]
    remote = current_remote(project_dir)
    pr_ref = _parse_pr_ref(pr_ref_raw, remote)

    # Fetch current state from gh if available
    pr_state = "open"
    if gh_available():
        prs = _fetch_pr_by_ref(pr_ref, remote)
        if prs:
            raw = prs[0].get("state", "open").lower()
            pr_state = raw if raw in {"merged", "closed", "open"} else "open"

    resolved_at = datetime.now().isoformat(timespec="seconds")
    result = ResolutionResult(
        session_hash=_session_line_hash(project_dir, session),
        pr_ref=pr_ref,
        pr_state=pr_state,
        resolved_at=resolved_at,
    )
    _write_amendment(project_dir, result)

    try:
        from halyard.db import get_db

        conn = get_db()
        try:
            _upsert_outcome(conn, result)
            conn.commit()
        finally:
            conn.close()
    except SystemExit:
        pass  # db not available — plain-text amendment is sufficient

    return True, f"Attributed {result.session_hash[:12]} → {pr_ref} ({pr_state})"


def _parse_pr_ref(raw: str, remote: str | None) -> str:
    """Normalize #42, owner/repo#42, or full GitHub URL to owner/repo#42."""
    raw = raw.strip()
    # Full URL: https://github.com/owner/repo/pull/42
    if "github.com" in raw and "/pull/" in raw:
        parts = raw.rstrip("/").split("/pull/")
        if len(parts) == 2:
            repo_part = parts[0].split("github.com/")[-1]
            return f"{repo_part}#{parts[1]}"
    # Already owner/repo#N
    if "#" in raw and "/" in raw.split("#")[0]:
        return raw
    # Bare #N
    if raw.startswith("#"):
        if remote:
            repo = _remote_to_repo(remote)
            if repo:
                return f"{repo}{raw}"
        return raw
    return raw


def _fetch_pr_by_ref(
    pr_ref: str,
    remote: str | None,
) -> list[dict]:  # type: ignore[type-arg]
    """Fetch a single PR by number using gh api."""
    if "#" not in pr_ref:
        return []
    repo_part, number_str = pr_ref.rsplit("#", 1)
    repo = repo_part or (_remote_to_repo(remote or "") if remote else None)
    if not repo or not number_str.isdigit():
        return []
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/pulls/{number_str}",
                "--jq",
                "{number: .number, state: .state, mergedAt: .merged_at, url: .html_url}",
            ],
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT,
        )
        if result.returncode != 0:
            return []
        return [json.loads(result.stdout)]
    except (OSError, FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
