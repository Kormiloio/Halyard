"""v2.24 outcome metadata — PR resolution, outcome reporting, manual attribution."""

from __future__ import annotations

import json
import sqlite3
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
    # session.end is local-naive; the gh createdAt is UTC. Normalize the
    # session time to UTC-naive too, otherwise the delta is wrong by the
    # local UTC offset and the closest-PR pick can be off by hours.
    session_end_utc = session.end.astimezone(UTC).replace(tzinfo=None)
    for pr in prs:
        created_str = pr.get("createdAt", "")
        with suppress(ValueError, TypeError):
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            if created.tzinfo is not None:
                created = created.astimezone(UTC).replace(tzinfo=None)
            delta = abs(session_end_utc - created)
            if best_delta is None or delta < best_delta:
                best = pr
                best_delta = delta
    return best


# ---------------------------------------------------------------------------
# pr_cache SQLite helpers
# ---------------------------------------------------------------------------


def _cache_get(
    conn: sqlite3.Connection,
    cache_key: str,
) -> list[dict[str, object]] | None:
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
            result: list[dict[str, object]] = json.loads(row["payload"])
            return result
    return None


def _cache_set(
    conn: sqlite3.Connection,
    cache_key: str,
    prs: list[dict[str, object]],
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
# v3.1 review-friction enrichment
#
# Phase-0 findings (design.md): `gh pr view --json comments` returns only
# issue/timeline comments, NOT inline review-thread comments, so the full
# comment count needs a SECOND call (`gh api .../pulls/<n>/comments`).
# Counts/enum only — never a comment body, PR title, branch, or author.
# Every failure mode fails closed to "field absent" (None), never 0.
# ---------------------------------------------------------------------------

_VALID_REVIEW_DECISIONS = {"APPROVED", "CHANGES_REQUESTED", "REVIEW_REQUIRED"}


@dataclass
class ReviewFriction:
    review_comments: int | None = None
    review_rounds: int | None = None
    time_to_merge_s: int | None = None
    review_decision: str | None = None


def _pr_ref_to_repo_number(
    pr_ref: str,
    remote: str | None,
) -> tuple[str, str] | None:
    """Split owner/repo#N (or #N + remote) into (repo, number); None if invalid."""
    if "#" not in pr_ref:
        return None
    repo_part, number_str = pr_ref.rsplit("#", 1)
    repo = repo_part or (_remote_to_repo(remote or "") if remote else None)
    if not repo or not number_str.isdigit():
        return None
    return repo, number_str


def gh_pr_view(
    pr_ref: str,
    remote: str | None,
) -> dict | None:  # type: ignore[type-arg]
    """`gh pr view <n> --json …` with a privacy-restricted field list.

    The field list deliberately excludes body/title/author. Returns the
    parsed JSON object, or None on any failure (fail closed).
    """
    rn = _pr_ref_to_repo_number(pr_ref, remote)
    if rn is None:
        return None
    repo, number = rn
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                number,
                "--repo",
                repo,
                "--json",
                "number,state,createdAt,mergedAt,reviewDecision,reviews,comments",
            ],
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return data if isinstance(data, dict) else None
    except (OSError, FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def gh_pr_inline_comment_count(
    pr_ref: str,
    remote: str | None,
) -> int | None:
    """Count inline review-thread comments via the pulls/<n>/comments API.

    Reduced to a length only — no body/author/path is read. Returns None
    on any failure (e.g. 404 when the ref is not a PR); the caller treats
    None as "unknown", never 0.
    """
    rn = _pr_ref_to_repo_number(pr_ref, remote)
    if rn is None:
        return None
    repo, number = rn
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/pulls/{number}/comments",
                "--jq",
                "length",
            ],
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT,
        )
        if result.returncode != 0:
            return None
        return int(result.stdout.strip())
    except (OSError, FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None


def _parse_ts(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    with suppress(ValueError, TypeError):
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(UTC).replace(tzinfo=None)
        return dt
    return None


def parse_friction(
    pr_view: dict | None,  # type: ignore[type-arg]
    inline_comment_count: int | None,
) -> ReviewFriction:
    """Reduce a `gh pr view` payload + inline count to four signals.

    Fail-closed: any field that cannot be derived from present, well-typed
    keys is left None (never defaulted to 0). `review_comments` requires
    BOTH the issue-comment list and the inline count, so a failed second
    call leaves only that field absent while the other three survive.
    """
    fr = ReviewFriction()
    if pr_view is None:
        return fr

    reviews = pr_view.get("reviews")
    if isinstance(reviews, list):
        fr.review_rounds = sum(
            1 for r in reviews if isinstance(r, dict) and r.get("state") == "CHANGES_REQUESTED"
        )

    comments = pr_view.get("comments")
    issue_comments = len(comments) if isinstance(comments, list) else None
    if issue_comments is not None and inline_comment_count is not None:
        fr.review_comments = issue_comments + inline_comment_count

    decision = pr_view.get("reviewDecision")
    if decision in _VALID_REVIEW_DECISIONS:
        fr.review_decision = decision

    if str(pr_view.get("state", "")).upper() == "MERGED":
        created = _parse_ts(pr_view.get("createdAt"))
        merged = _parse_ts(pr_view.get("mergedAt"))
        if created is not None and merged is not None:
            delta = round((merged - created).total_seconds())
            if delta >= 0:
                fr.time_to_merge_s = delta

    return fr


def _friction_cache_get(
    conn: sqlite3.Connection,
    cache_key: str,
) -> ReviewFriction | None:
    """Return cached friction. Merged-PR entries are permanently valid
    (friction is immutable post-merge); others honour the TTL."""
    row = conn.execute(
        "SELECT payload, fetched_at FROM pr_cache WHERE cache_key = ?",
        (cache_key,),
    ).fetchone()
    if row is None:
        return None
    with suppress(ValueError, KeyError, TypeError, json.JSONDecodeError):
        data = json.loads(row["payload"])
        is_merged = data.get("pr_state") == "merged"
        fresh = False
        fetched_at_str: str = row["fetched_at"]
        with suppress(ValueError):
            fetched_at = datetime.fromisoformat(fetched_at_str)
            fresh = datetime.now() - fetched_at < timedelta(hours=_CACHE_TTL_HOURS)
        if is_merged or fresh:
            return ReviewFriction(
                review_comments=data.get("review_comments"),
                review_rounds=data.get("review_rounds"),
                time_to_merge_s=data.get("time_to_merge_s"),
                review_decision=data.get("review_decision"),
            )
    return None


def _friction_cache_set(
    conn: sqlite3.Connection,
    cache_key: str,
    friction: ReviewFriction,
    pr_state: str,
) -> None:
    payload = {
        "review_comments": friction.review_comments,
        "review_rounds": friction.review_rounds,
        "time_to_merge_s": friction.time_to_merge_s,
        "review_decision": friction.review_decision,
        "pr_state": pr_state,
    }
    conn.execute(
        """
        INSERT OR REPLACE INTO pr_cache (cache_key, payload, fetched_at)
        VALUES (?, ?, ?)
        """,
        (cache_key, json.dumps(payload), datetime.now().isoformat()),
    )
    conn.commit()


def _resolve_friction(
    conn: sqlite3.Connection,
    pr_ref: str,
    pr_state: str,
    remote: str | None,
) -> ReviewFriction:
    """Friction for one PR: cache → ≤2 gh calls → cache. Fail-closed.

    A total failure of the primary `gh pr view` call is NOT cached, so a
    transient outage retries on the next sync rather than poisoning a
    (potentially permanent, if merged) cache entry with all-None.
    """
    cache_key = f"{remote or ''}:{pr_ref}:friction"
    cached = _friction_cache_get(conn, cache_key)
    if cached is not None:
        return cached

    pr_view = gh_pr_view(pr_ref, remote)
    inline = gh_pr_inline_comment_count(pr_ref, remote)
    friction = parse_friction(pr_view, inline)

    if pr_view is not None:
        _friction_cache_set(conn, cache_key, friction, pr_state)
    return friction


# ---------------------------------------------------------------------------
# Resolution algorithm
# ---------------------------------------------------------------------------


@dataclass
class ResolutionResult:
    session_hash: str
    pr_ref: str | None
    pr_state: str
    resolved_at: str
    review_comments: int | None = None
    review_rounds: int | None = None
    time_to_merge_s: int | None = None
    review_decision: str | None = None


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
    # v3.1: enrich at most once per unique PR ref per sync (the pr_cache
    # adds cross-sync reuse on top). Gate the gh calls on availability so
    # a missing gh leaves friction absent without erroring (R3).
    gh_ok = gh_available()
    friction_memo: dict[str, ReviewFriction] = {}

    try:
        # Group by branch to minimise gh calls
        by_branch: dict[str, list[AiSession]] = {}
        for s in candidates:
            by_branch.setdefault(s.branch or "", []).append(s)

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
                    session_hash=_session_line_hash(s),
                    pr_ref=pr_ref,
                    pr_state=pr_state,
                    resolved_at=resolved_at,
                )

                if pr_ref and gh_ok:
                    friction = friction_memo.get(pr_ref)
                    if friction is None:
                        friction = _resolve_friction(conn, pr_ref, pr_state, remote)
                        friction_memo[pr_ref] = friction
                    result.review_comments = friction.review_comments
                    result.review_rounds = friction.review_rounds
                    result.time_to_merge_s = friction.time_to_merge_s
                    result.review_decision = friction.review_decision

                results.append(result)

                if not dry_run:
                    _write_amendment(project_dir, result)
                    _upsert_outcome(conn, result)

        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    return results


def _session_line_hash(session: AiSession) -> str:
    """Return the hash of the original raw `s` log line for this session.

    Uses AiSession._raw_hash (set at parse time before amendment folding) so
    that the hash matches the actual line in the file. Falls back to hashing
    the serialized form for sessions not created by parse_sessions (e.g. tests).
    """
    return session._raw_hash or session_hash(session.to_log_line())


def _write_amendment(project_dir: Path, result: ResolutionResult) -> None:
    log_path = project_dir / "ai-sessions.log"
    if not log_path.exists():
        return
    parts = [f"a {result.session_hash}"]
    if result.pr_ref:
        parts.append(f"pr_ref={result.pr_ref}")
    parts.append(f"pr_state={result.pr_state}")
    parts.append(f"outcome_resolved_at={result.resolved_at}")
    if result.review_comments is not None:
        parts.append(f"review_comments={result.review_comments}")
    if result.review_rounds is not None:
        parts.append(f"review_rounds={result.review_rounds}")
    if result.time_to_merge_s is not None:
        parts.append(f"time_to_merge_s={result.time_to_merge_s}")
    if result.review_decision:
        parts.append(f"review_decision={result.review_decision}")
    line = " ".join(parts)
    with locked_file(log_path, "a") as f:
        f.write(line + "\n")


def _upsert_outcome(conn, result: ResolutionResult) -> None:  # type: ignore[no-untyped-def]
    # COALESCE on the friction columns so a friction-free write (e.g.
    # manual `outcome attribute`, or a sync where gh was unavailable)
    # never wipes friction already enriched by a previous sync.
    conn.execute(
        """
        INSERT INTO outcomes (
            session_id, pr_ref, pr_state, resolved_at,
            review_comment_count, review_round_trips,
            time_to_merge_seconds, review_decision
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            pr_ref = excluded.pr_ref,
            pr_state = excluded.pr_state,
            resolved_at = excluded.resolved_at,
            review_comment_count = COALESCE(
                excluded.review_comment_count, outcomes.review_comment_count),
            review_round_trips = COALESCE(
                excluded.review_round_trips, outcomes.review_round_trips),
            time_to_merge_seconds = COALESCE(
                excluded.time_to_merge_seconds, outcomes.time_to_merge_seconds),
            review_decision = COALESCE(
                excluded.review_decision, outcomes.review_decision)
        """,
        (
            result.session_hash,
            result.pr_ref,
            result.pr_state,
            result.resolved_at,
            result.review_comments,
            result.review_rounds,
            result.time_to_merge_s,
            result.review_decision,
        ),
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
    # v3.1 review-friction medians (None when the bucket has no data).
    median_time_to_merge_s: int | None = None
    median_review_comments: int | None = None


def _bucket_friction(lst: list[AiSession]) -> tuple[int | None, int | None]:
    from halyard.leverage import _median_int

    ttm = [s.time_to_merge_s for s in lst if s.time_to_merge_s is not None]
    rc = [s.review_comments for s in lst if s.review_comments is not None]
    return _median_int(ttm), _median_int(rc)


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

    def _captured(label: str, key: str) -> OutcomeBucket:
        lst = buckets[key]
        ttm, rc = _bucket_friction(lst)
        return OutcomeBucket(
            label=label,
            session_count=len(lst),
            total_cost=sum(s.cost_usd for s in lst),
            trust="captured",
            median_time_to_merge_s=ttm,
            median_review_comments=rc,
        )

    return [
        _captured("Shipped (PR merged)", "merged"),
        _captured("In-flight (PR open)", "open"),
        _captured("Abandoned (PR closed)", "closed"),
        _captured("No PR detected", "none"),
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
    matched = [s for s in sessions if _session_line_hash(s).startswith(session_id_prefix)]
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
        session_hash=_session_line_hash(session),
        pr_ref=pr_ref,
        pr_state=pr_state,
        resolved_at=resolved_at,
    )
    _write_amendment(project_dir, result)

    try:
        from halyard.db import DbError, get_db

        conn = get_db()
        try:
            _upsert_outcome(conn, result)
            conn.commit()
        finally:
            conn.close()
    except DbError:
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
