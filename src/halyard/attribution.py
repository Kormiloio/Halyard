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
_ALIASES_PATH = Path.home() / ".halyard" / "project-aliases.toml"

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


def load_project_aliases() -> dict[str, str]:
    """Return the user's source-slug → canonical-slug map (``{}`` if none).

    Tolerant: a missing or invalid file yields an empty map (canonicalization
    becomes a no-op) rather than raising on the read path.
    """
    if not _ALIASES_PATH.exists():
        return {}
    try:
        data = tomllib.loads(_ALIASES_PATH.read_text())
    except (tomllib.TOMLDecodeError, OSError):
        return {}
    aliases = data.get("aliases", {})
    if not isinstance(aliases, dict):
        return {}
    return {k: v for k, v in aliases.items() if isinstance(k, str) and isinstance(v, str)}


def canonical_project(slug: str | None, aliases: dict[str, str]) -> str | None:
    """Resolve *slug* through the alias map (single hop). ``None`` stays None."""
    if slug is None:
        return None
    return aliases.get(slug, slug)


def set_project_alias(source: str, canonical: str) -> None:
    """Add or update one ``source → canonical`` alias, persisting the map."""
    import tomli_w

    aliases = load_project_aliases()
    aliases[source] = canonical
    _ALIASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"aliases": dict(sorted(aliases.items()))}
    _ALIASES_PATH.write_bytes(tomli_w.dumps(payload).encode())
