"""Cost center resolution for finance reporting.

Two sources, applied in priority order:
  1. projects.toml  — optional `cost_center` field on each project (highest priority)
  2. org-cost-centers.toml — project_mapping entries, then team_mapping fallback

Unattributed sessions are labelled "(unattributed)" and never assigned a
cost center automatically.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict

ORG_COST_CENTERS_FILENAME = "org-cost-centers.toml"


class ProjectCostMapping(BaseModel):
    model_config = ConfigDict(frozen=True)
    project_slug: str
    cost_center: str


class TeamCostMapping(BaseModel):
    model_config = ConfigDict(frozen=True)
    team_id: str
    cost_center: str


class CostCenterConfig(BaseModel):
    """Parsed org-cost-centers.toml."""

    model_config = ConfigDict(frozen=True)
    project_mappings: tuple[ProjectCostMapping, ...] = ()
    team_mappings: tuple[TeamCostMapping, ...] = ()

    def resolve(self, project_id: str, team_id: str) -> str:
        """Return cost center code, or '' if none configured."""
        for pm in self.project_mappings:
            if pm.project_slug == project_id:
                return pm.cost_center
        for tm in self.team_mappings:
            if tm.team_id == team_id:
                return tm.cost_center
        return ""


def read_cost_center_config(hub_dir: Path) -> CostCenterConfig:
    """Read org-cost-centers.toml from hub_dir. Returns empty config if absent."""
    path = hub_dir / ORG_COST_CENTERS_FILENAME
    if not path.exists():
        return CostCenterConfig()
    data = tomllib.loads(path.read_text())
    return CostCenterConfig(
        project_mappings=[
            ProjectCostMapping.model_validate(m) for m in data.get("project_mapping", [])
        ],
        team_mappings=[TeamCostMapping.model_validate(m) for m in data.get("team_mapping", [])],
    )


def read_project_cost_centers(project_dir: Path) -> dict[str, str]:
    """Return {project_slug: cost_center} from projects.toml cost_center fields."""
    path = project_dir / "projects.toml"
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text())
    result: dict[str, str] = {}
    for p in data.get("project", []):
        slug = p.get("slug", "")
        cc = p.get("cost_center", "")
        if slug and cc:
            result[slug] = cc
    return result


def resolve_cost_center(
    project_id: str,
    team_id: str,
    *,
    project_overrides: dict[str, str],
    org_config: CostCenterConfig,
) -> str:
    """Return the cost center for a session row.

    Priority: projects.toml field > org-cost-centers.toml project mapping
              > org-cost-centers.toml team mapping > ''
    """
    if not project_id:
        return ""
    if project_id in project_overrides:
        return project_overrides[project_id]
    return org_config.resolve(project_id, team_id)
