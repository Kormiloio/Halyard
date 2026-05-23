"""Guided setup helpers for first-run onboarding."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from halyard.ai_log import find_project_dir
from halyard.hub import find_hub

ToolName = str

SUPPORTED_TOOLS: tuple[ToolName, ...] = ("claude", "cursor", "gemini", "windsurf")


@dataclass(frozen=True)
class SetupSelection:
    tools: tuple[ToolName, ...]


@dataclass(frozen=True)
class SetupReadiness:
    project_dir: Path | None
    hub_dir: Path | None

    @property
    def has_destination(self) -> bool:
        return self.project_dir is not None or self.hub_dir is not None


def resolve_selection(
    *,
    all_tools: bool,
    claude: bool,
    cursor: bool,
    gemini: bool,
    windsurf: bool,
    yes: bool,
) -> SetupSelection:
    """Resolve setup flags into a deterministic list of tool slugs."""
    selected: list[ToolName] = []
    if all_tools or (yes and not any((claude, cursor, gemini, windsurf))):
        selected.extend(SUPPORTED_TOOLS)
    else:
        if claude:
            selected.append("claude")
        if cursor:
            selected.append("cursor")
        if gemini:
            selected.append("gemini")
        if windsurf:
            selected.append("windsurf")
    return SetupSelection(tools=tuple(selected))


def readiness(start: Path | None = None) -> SetupReadiness:
    return SetupReadiness(project_dir=find_project_dir(start=start), hub_dir=find_hub())


def tool_label(tool: ToolName) -> str:
    return {
        "claude": "Claude Code",
        "cursor": "Cursor",
        "gemini": "Gemini CLI",
        "windsurf": "Windsurf",
    }.get(tool, tool)


def next_step_text() -> str:
    return "Next: run one AI session, then `halyard doctor --first-capture`."
