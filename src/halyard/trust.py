"""Session trust labels — pure helpers used by OSS dashboards and reports.

Trust labels classify how confident Halyard is in a session's cost figure:

- ``captured`` — direct per-call cost was returned by the provider's API.
- ``allocated`` — cost came from an ``ai-plans.toml`` subscription
  allocation, not a per-call charge.
- ``missing`` — no cost data and no allocation; treat as $0 with caveats.
- ``mixed`` — an aggregate that combines two or more of the above.

These functions take only :class:`halyard.ai_log.AiSession` — no
``org.toml`` dependency — so they live in the OSS core. The
``halyard_enterprise`` package re-uses them for org-level rollups.
"""

from __future__ import annotations

from halyard.ai_log import AiSession


def session_trust(s: AiSession) -> str:
    """Derive a trust label from a session's billing and cost fields."""
    if s.cost_usd > 0:
        if s.billing == "credits":
            return "allocated"
        return "captured"
    if s.credits is not None and s.credits > 0:
        return "allocated"
    return "missing"


def aggregate_trust(labels: list[str]) -> str:
    """Reduce a list of trust labels to a single aggregate label."""
    unique = set(labels)
    if not unique:
        return "missing"
    if len(unique) == 1:
        return next(iter(unique))
    return "mixed"
