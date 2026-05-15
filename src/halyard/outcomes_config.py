"""Outcomes feature flag — opt-in / opt-out for the v3.0 outcome graph.

The flag lives in ``halyard.toml`` under the top-level ``[outcomes]`` table:

    [outcomes]
    enabled = true              # default: true once a project is initialised
    shell_history = false       # default: false (privacy-sensitive collection)

When ``outcomes.enabled = false`` is set, every CLI surface
(``halyard outcome sync|report|attribute``) and every passive dashboard /
TUI render path MUST treat outcome data as absent — no git/gh shell-outs,
no shell-history scans, no PR-cache writes. Existing ``a`` amendment
records that were written before the flag was disabled remain in the log
and continue to parse, but no new collection happens.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

# Default behaviour when the flag is absent from halyard.toml.
# v3.0 ships outcomes ON by default for new installs; users disable
# explicitly. shell_history defaults OFF because reading the user's shell
# history is privacy-sensitive and warrants explicit opt-in.
_DEFAULTS = {
    "enabled": True,
    "shell_history": False,
}


def read_outcomes_config(project_dir: Path) -> dict[str, bool]:
    """Read the ``[outcomes]`` table from project_dir/halyard.toml.

    Returns a dict with at least ``enabled`` and ``shell_history`` keys.
    Missing keys are filled from defaults. A missing or unreadable
    halyard.toml is treated as "use defaults" (not as an error).
    """
    toml_path = project_dir / "halyard.toml"
    out = dict(_DEFAULTS)
    if not toml_path.exists():
        return out
    try:
        with toml_path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return out
    block = data.get("outcomes") or {}
    if isinstance(block, dict):
        if isinstance(block.get("enabled"), bool):
            out["enabled"] = block["enabled"]
        if isinstance(block.get("shell_history"), bool):
            out["shell_history"] = block["shell_history"]
    return out


def outcomes_enabled(project_dir: Path) -> bool:
    """Shorthand: is outcome collection enabled for this project?"""
    return read_outcomes_config(project_dir)["enabled"]


def shell_history_enabled(project_dir: Path) -> bool:
    """Shorthand: is shell-history test-run detection enabled?

    Disabled by default — shell history can contain secrets and arbitrary
    content. Users must opt in explicitly with
    ``[outcomes]\\nshell_history = true`` in halyard.toml.
    """
    return read_outcomes_config(project_dir)["shell_history"]
