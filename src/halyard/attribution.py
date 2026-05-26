"""Attribution confidence — the project-attribution moat made visible.

Cost carries trust labels (captured/calculated/allocated/inferred)
surfaced everywhere. Project attribution had no equivalent and the
collector ``attr_method`` collapsed the whole inference chain into a
single ``"git"``. This derives a confidence band from the recorded
rung so a timer-attributed session and a guessed auto-slug session are
no longer indistinguishable.

Ordering (strongest → weakest):
  timer   — active `halyard start` (the user declared it)
  mapped  — explicit repos.toml mapping / Cursor workspace root
  toml    — halyard.toml [project].slug walk-up
  auto    — derived git/<repo> slug (a guess)
  unknown — attributed but provenance not determinable (e.g. legacy
            backfill/manual amendments)
  none    — unattributed (no project)

Legacy ``attr_method=git`` rows resolve to ``auto`` — the safe lower
bound. Confidence is never inflated for an old guess.
"""

from __future__ import annotations

import tomllib
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from halyard.ai_log import AiSession

# v5.8: read-time project canonicalization. One logical project can accrue
# several slug forms in the append-only log over time (e.g. a git-auto
# `git/<repo>` slug vs. the canonical `client:project`); this user-defined map
# merges them at read time so every surface groups by one slug. The log is
# never rewritten — this is reinterpretation only.
#
# v5.11: two sources. The committed `<project_dir>/project-aliases.toml` is the
# shared, version-controlled baseline; the per-machine `~/.halyard` file is an
# optional local override. They merge as {**committed, **home} so a machine can
# locally re-point an alias without editing the shared file.
_ALIASES_PATH = Path.home() / ".halyard" / "project-aliases.toml"
_ALIASES_FILENAME = "project-aliases.toml"

AttributionConfidence = Literal["timer", "mapped", "toml", "auto", "unknown", "none"]

_RUNG_TO_CONFIDENCE: dict[str, AttributionConfidence] = {
    "timer": "timer",
    "repo-map": "mapped",
    "ws_root": "mapped",  # Cursor workspace root — stronger than bare git
    "toml": "toml",
    "git-auto": "auto",
    "git": "auto",  # legacy catch-all → safe lower bound, never "mapped"
    "backfill": "unknown",
    "manual": "unknown",
}

# Display order for mixes (strongest first).
CONFIDENCE_ORDER: tuple[AttributionConfidence, ...] = (
    "timer",
    "mapped",
    "toml",
    "auto",
    "unknown",
    "none",
)


def attribution_confidence(session: AiSession) -> AttributionConfidence:
    """Confidence band for one session's project attribution."""
    if not session.project:
        return "none"
    return _RUNG_TO_CONFIDENCE.get(session.attr_method or "", "unknown")


def attribution_mix(sessions: Iterable[AiSession]) -> dict[AttributionConfidence, int]:
    """Session counts per confidence band, ordered strongest → weakest.

    Only non-zero bands are included; iteration order follows
    ``CONFIDENCE_ORDER`` so callers can render a stable summary.
    """
    counts: Counter[AttributionConfidence] = Counter(attribution_confidence(s) for s in sessions)
    return {band: counts[band] for band in CONFIDENCE_ORDER if counts[band]}


def format_attribution_mix(sessions: Iterable[AiSession]) -> str:
    """One-line summary, e.g. ``timer 12 · mapped 4 · auto 3 · adrift 2``."""
    mix = attribution_mix(sessions)
    if not mix:
        return "no sessions"
    label = {
        "timer": "timer",
        "mapped": "mapped",
        "toml": "toml",
        "auto": "auto",
        "unknown": "unknown",
        "none": "adrift",
    }
    return " · ".join(f"{label[b]} {n}" for b, n in mix.items())


# ---------------------------------------------------------------------------
# v5.8: project alias canonicalization (read-time)
# ---------------------------------------------------------------------------


# Cached by both files' (path, mtime): parse_sessions is the hottest read path
# and is called per-project across reports/dashboard, so re-parsing the TOML
# every call is wasteful. A write (set_project_alias) bumps an mtime → next load
# re-reads. A missing file contributes a None mtime, so its later creation also
# invalidates the cache.
_AliasSig = tuple[str, float | None]
_alias_cache: tuple[tuple[_AliasSig, _AliasSig], dict[str, str]] | None = None


def _alias_file_sig(path: Path) -> _AliasSig:
    try:
        return (str(path), path.stat().st_mtime)
    except OSError:
        return (str(path), None)


def _read_alias_file(path: Path) -> dict[str, str]:
    """Parse one alias file's ``[aliases]`` table; ``{}`` if missing/invalid."""
    try:
        data = tomllib.loads(path.read_text())
    except (tomllib.TOMLDecodeError, OSError):
        return {}
    aliases = data.get("aliases", {})
    if not isinstance(aliases, dict):
        return {}
    return {k: v for k, v in aliases.items() if isinstance(k, str) and isinstance(v, str)}


def load_project_aliases(project_dir: Path | None = None) -> dict[str, str]:
    """Return the source-slug → canonical-slug map (``{}`` if none).

    Merges the committed ``<project_dir>/project-aliases.toml`` (shared baseline)
    with the per-machine ``~/.halyard/project-aliases.toml`` (local override
    wins). Tolerant: missing/invalid files yield an empty map rather than raising
    on the read path. Cached by both files' mtimes.
    """
    global _alias_cache
    committed_path = (project_dir / _ALIASES_FILENAME) if project_dir is not None else None
    home_sig = _alias_file_sig(_ALIASES_PATH)
    committed_sig: _AliasSig = (
        _alias_file_sig(committed_path) if committed_path is not None else ("", None)
    )
    cache_key = (home_sig, committed_sig)
    if _alias_cache is not None and _alias_cache[0] == cache_key:
        return _alias_cache[1]

    committed = _read_alias_file(committed_path) if committed_path is not None else {}
    home = _read_alias_file(_ALIASES_PATH)
    result = {**committed, **home}  # local override wins over committed baseline
    _alias_cache = (cache_key, result)
    return result


def canonical_project(slug: str | None, aliases: dict[str, str]) -> str | None:
    """Resolve *slug* to its canonical form, following alias chains.

    Follows ``A → B → C`` to the end with a cycle guard, so a chained alias map
    never splits one logical project across two buckets. ``None`` stays None.
    """
    if slug is None:
        return None
    seen: set[str] = set()
    cur = slug
    while cur in aliases and cur not in seen:
        seen.add(cur)
        cur = aliases[cur]
    return cur


def set_project_alias(source: str, canonical: str, project_dir: Path | None = None) -> None:
    """Add or update one ``source → canonical`` alias, persisting the map.

    Writes to the committed ``<project_dir>/project-aliases.toml`` when a project
    dir is given (so the alias lands in version control), else the per-machine
    ``~/.halyard`` file. Only the target file's own entries are rewritten — the
    other source is never folded in.
    """
    global _alias_cache
    import tomli_w

    target = (project_dir / _ALIASES_FILENAME) if project_dir is not None else _ALIASES_PATH
    aliases = _read_alias_file(target)
    aliases[source] = canonical
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"aliases": dict(sorted(aliases.items()))}
    target.write_bytes(tomli_w.dumps(payload).encode())
    _alias_cache = None  # invalidate; next load re-reads both sources
