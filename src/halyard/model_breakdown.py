"""Per-model usage breakdown for multi-model sessions (v2.61).

One agent session can use several models (router/main/subagent). The
session line keeps a single primary ``model``; the optional
``model_breakdown`` token carries the per-model split so cost and
per-model rollups are correct instead of attributing the whole
session to one model.

Grammar (usage form):

    model:in/out/cr/cw ( "|" model:in/out/cr/cw )*

Back-compat: the legacy count form (``model:3|other:1`` — no ``/``)
is *not* parsed as usage. ``parse`` returns ``None`` for anything that
is not wholly usage-form, so callers safely fall back to the
single-model path (no wrong attribution, ever).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from halyard.ai_log import AiSession
from halyard.pricing import calculate_cost


@dataclass(frozen=True)
class ModelSeg:
    model: str
    input_tokens: int
    output_tokens: int
    cache_read: int
    cache_write: int


def encode(segs: Iterable[ModelSeg]) -> str:
    """Render segments to the usage-form token (no whitespace/`=`)."""
    return "|".join(
        f"{s.model}:{s.input_tokens}/{s.output_tokens}/{s.cache_read}/{s.cache_write}"
        for s in segs
        if s.model
    )


def parse(token: str | None) -> list[ModelSeg] | None:
    """Parse a usage-form breakdown, or ``None`` if not wholly usage-form.

    Any malformed/legacy/truncated segment ⇒ ``None`` (degrade to the
    single-model path — never a half-parsed, wrong-cost attribution).
    """
    if not token:
        return None
    segs: list[ModelSeg] = []
    for part in token.split("|"):
        if ":" not in part:
            return None
        model, _, nums = part.partition(":")
        if not model:
            return None
        fields = nums.split("/")
        if len(fields) != 4:
            return None  # legacy count form or truncated → bail
        try:
            i, o, cr, cw = (int(x) for x in fields)
        except ValueError:
            return None
        if min(i, o, cr, cw) < 0:
            return None
        segs.append(ModelSeg(model, i, o, cr, cw))
    return segs or None


def cost_of(token: str | None) -> float | None:
    """Σ per-model cost for a usage-form breakdown, else ``None``."""
    segs = parse(token)
    if segs is None:
        return None
    return float(
        sum(
            calculate_cost(s.model, s.input_tokens, s.output_tokens, s.cache_read, s.cache_write)
            for s in segs
        )
    )


def primary_model(segs: list[ModelSeg]) -> str:
    """The segment with the greatest cost share (tie: tokens, then name)."""

    def key(s: ModelSeg) -> tuple[float, int, str]:
        c = calculate_cost(s.model, s.input_tokens, s.output_tokens, s.cache_read, s.cache_write)
        return (c, s.input_tokens + s.output_tokens, s.model)

    return max(segs, key=key).model


def iter_model_usage(
    session: AiSession,
) -> list[tuple[str, int, int, int, int, float]]:
    """(model, in, out, cr, cw, cost) per model.

    Multi-model (usage-form breakdown present) → one tuple per
    segment, each costed independently. Otherwise a single tuple from
    the session's own fields + its recorded cost — byte-identical to
    the pre-v2.61 single-model attribution.
    """
    segs = parse(session.model_breakdown)
    if segs is not None:
        return [
            (
                s.model,
                s.input_tokens,
                s.output_tokens,
                s.cache_read,
                s.cache_write,
                float(
                    calculate_cost(
                        s.model, s.input_tokens, s.output_tokens, s.cache_read, s.cache_write
                    )
                ),
            )
            for s in segs
        ]
    return [
        (
            session.model,
            session.input_tokens,
            session.output_tokens,
            session.cache_read or 0,
            session.cache_write or 0,
            session.cost_usd,
        )
    ]
