"""Configuration loader for halyard log provider defaults."""

from __future__ import annotations

import tomllib
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

_LOG_CONFIG_FILE = Path.home() / ".halyard" / "config.toml"
_OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_VALID_AGENTS = frozenset({"local", "claude", "openai"})

LogAgentName = Literal["local", "claude", "openai"]


@dataclass(frozen=True)
class LogConfig:
    default_agent: LogAgentName = "local"
    openai_base_url: str = _OPENAI_DEFAULT_BASE_URL
    openai_model: str = "gpt-4o"
    claude_model: str = "claude-3-5-sonnet-20241022"


def load_log_config(config_file: Path | None = None) -> LogConfig:
    """Load ~/.halyard/config.toml [log] section; return defaults if absent."""
    path = config_file if config_file is not None else _LOG_CONFIG_FILE
    if not path.exists():
        return LogConfig()

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    raw_section = data.get("log", {})
    section: dict[str, Any] = raw_section if isinstance(raw_section, dict) else {}

    raw_agent = section.get("default_agent", "local")
    if not isinstance(raw_agent, str) or raw_agent not in _VALID_AGENTS:
        warnings.warn(
            f"unknown log.default_agent '{raw_agent}' in config — using local.",
            stacklevel=2,
        )
        raw_agent = "local"

    return LogConfig(
        default_agent=cast(LogAgentName, raw_agent),
        openai_base_url=section.get("openai_base_url", _OPENAI_DEFAULT_BASE_URL),
        openai_model=section.get("openai_model", "gpt-4o"),
        claude_model=section.get("claude_model", "claude-3-5-sonnet-20241022"),
    )
