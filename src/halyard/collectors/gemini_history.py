"""Gemini CLI history file parser.

Reads ~/.gemini/tmp/{slug}/chats/session-*.json to extract per-model token counts,
tool call stats, and accurate multi-model cost for a completed session.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from halyard.pricing import calculate_cost

_GEMINI_TMP = Path.home() / ".gemini" / "tmp"
_GEMINI_HISTORY = Path.home() / ".gemini" / "history"


@dataclass
class GeminiModelStats:
    model: str
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    thinking_tokens: int = 0
    tool_calls: int = 0
    tool_errors: int = 0


@dataclass
class GeminiSessionSummary:
    session_id: str
    start: datetime
    end: datetime
    model_stats: list[GeminiModelStats] = field(default_factory=list)

    # Derived — populated by _derive()
    dominant_model: str = ""
    total_input: int = 0
    total_output: int = 0
    total_cache: int = 0
    total_tool_calls: int = 0
    total_tool_errors: int = 0
    cost_usd: float = 0.0

    def _derive(self) -> None:
        if not self.model_stats:
            return
        dominant = max(self.model_stats, key=lambda s: s.output_tokens)
        self.dominant_model = dominant.model
        self.total_input = sum(s.input_tokens for s in self.model_stats)
        self.total_output = sum(s.output_tokens for s in self.model_stats)
        self.total_cache = sum(s.cache_tokens for s in self.model_stats)
        self.total_tool_calls = sum(s.tool_calls for s in self.model_stats)
        self.total_tool_errors = sum(s.tool_errors for s in self.model_stats)
        self.cost_usd = sum(
            calculate_cost(
                s.model,
                # thinking tokens billed as input
                input_tokens=s.input_tokens + s.thinking_tokens,
                output_tokens=s.output_tokens,
                cache_read=s.cache_tokens,
            )
            for s in self.model_stats
        )


def parse_session_file(path: Path) -> GeminiSessionSummary | None:
    """Parse a Gemini CLI history JSON. Returns None on any error."""
    try:
        data: dict[str, object] = json.loads(path.read_text())
    except Exception:
        return None

    try:
        session_id = str(data.get("sessionId") or "")
        start_raw = data.get("startTime") or ""
        end_raw = data.get("lastUpdated") or ""
        messages = data.get("messages") or []

        if not session_id or not isinstance(messages, list):
            return None

        start = _parse_iso(str(start_raw))
        end = _parse_iso(str(end_raw))
        if start is None or end is None:
            return None

        # Aggregate per-model stats
        stats_by_model: dict[str, GeminiModelStats] = {}
        for msg in messages:
            if not isinstance(msg, dict) or msg.get("type") != "gemini":
                continue
            model = str(msg.get("model") or "unknown")
            tokens = msg.get("tokens") or {}
            if not isinstance(tokens, dict):
                tokens = {}
            tool_calls_raw = msg.get("toolCalls") or []
            if not isinstance(tool_calls_raw, list):
                tool_calls_raw = []

            if model not in stats_by_model:
                stats_by_model[model] = GeminiModelStats(model=model)
            s = stats_by_model[model]
            s.requests += 1
            inp = int(tokens.get("input") or 0)
            cached = int(tokens.get("cached") or 0)
            s.cache_tokens += cached
            # net input = reported input minus cached (Gemini reports gross input)
            s.input_tokens += max(0, inp - cached)
            s.output_tokens += int(tokens.get("output") or 0)
            s.thinking_tokens += int(tokens.get("thoughts") or 0)
            for tc in tool_calls_raw:
                if not isinstance(tc, dict):
                    continue
                s.tool_calls += 1
                if tc.get("status") == "error":
                    s.tool_errors += 1

        summary = GeminiSessionSummary(
            session_id=session_id,
            start=start,
            end=end,
            model_stats=list(stats_by_model.values()),
        )
        summary._derive()
        return summary

    except Exception:
        return None


def find_session_file(session_id: str) -> Path | None:
    """Find the history JSON for a session by its ID prefix."""
    prefix = session_id[:8]
    matches: list[Path] = []
    for candidate in _GEMINI_TMP.glob(f"*/chats/session-*-{prefix}.json"):
        matches.append(candidate)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    return max(matches, key=lambda p: p.stat().st_mtime)


def find_all_session_files() -> list[Path]:
    """Return all session JSON files across all project slugs."""
    return list(_GEMINI_TMP.glob("*/chats/session-*.json"))


def project_dir_for_slug(slug: str) -> Path | None:
    """Read ~/.gemini/history/{slug}/.project_root. Returns None if absent."""
    pointer = _GEMINI_HISTORY / slug / ".project_root"
    if not pointer.exists():
        return None
    try:
        return Path(pointer.read_text().strip())
    except Exception:
        return None


def _parse_iso(s: str) -> datetime | None:
    """Parse ISO 8601 string with or without trailing Z."""
    try:
        return (
            datetime.fromisoformat(s.replace("Z", "+00:00"))
            .astimezone(tz=None)
            .replace(tzinfo=None)
        )
    except Exception:
        return None
