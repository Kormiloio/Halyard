"""Org identity — org.toml model, parser, and identity resolution.

org.toml lives at the Halyard hub root and maps contributors (by git email)
to teams and departments.  All org-level rollup work reads from this file.
"""

from __future__ import annotations

import hashlib
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

ORG_TOML_FILENAME = "org.toml"
ORG_NOTES_POLICY_DEFAULT = False

Trust = Literal["captured", "calculated", "allocated", "inferred", "missing", "mixed"]
AttributionState = Literal["confirmed", "inferred", "unattributed"]


# ---------------------------------------------------------------------------
# org.toml models
# ---------------------------------------------------------------------------


class OrgInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    name: str = ""


class Department(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    name: str = ""


class Team(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    name: str = ""
    department_id: str = ""


class Member(BaseModel):
    model_config = ConfigDict(frozen=True)
    email: str
    team_id: str
    display_name: str = ""


class OrgConfig(BaseModel):
    """Parsed representation of org.toml."""

    model_config = ConfigDict(frozen=True)

    org: OrgInfo
    departments: tuple[Department, ...] = ()
    teams: tuple[Team, ...] = ()
    members: tuple[Member, ...] = ()

    # derived: email → Member (built once)
    _email_index: dict[str, Member] = {}

    def model_post_init(self, _context: object) -> None:
        object.__setattr__(self, "_email_index", {m.email.lower(): m for m in self.members})

    def resolve_user(self, email: str) -> tuple[str, str]:
        """Return (user_id, team_id) for a git email.

        Falls back to (email, "(unassigned)") when the email is not in the
        member list.
        """
        member = self._email_index.get(email.lower())
        if member is None:
            return email, "(unassigned)"
        return member.email, member.team_id

    def team_name(self, team_id: str) -> str:
        for t in self.teams:
            if t.id == team_id:
                return t.name
        return team_id

    def department_for_team(self, team_id: str) -> str:
        for t in self.teams:
            if t.id == team_id:
                return t.department_id
        return ""

    def sync_notes_enabled(self) -> bool:
        return ORG_NOTES_POLICY_DEFAULT


def read_org_config(hub_dir: Path) -> OrgConfig | None:
    """Read org.toml from the hub directory. Returns None if absent."""
    path = hub_dir / ORG_TOML_FILENAME
    if not path.exists():
        return None
    data = tomllib.loads(path.read_text())
    return OrgConfig(
        org=OrgInfo.model_validate(data["org"]),
        departments=[Department.model_validate(d) for d in data.get("department", [])],
        teams=[Team.model_validate(t) for t in data.get("team", [])],
        members=[Member.model_validate(m) for m in data.get("member", [])],
    )


# ---------------------------------------------------------------------------
# Normalized org event schema
# ---------------------------------------------------------------------------


class OrgSession(BaseModel):
    """Normalized metadata record produced from a local ai-sessions.log line.

    Never contains prompt text, code content, file paths, or transcripts.
    """

    model_config = ConfigDict(frozen=True)

    # identity
    org_id: str
    team_id: str
    user_id: str

    # attribution
    project_id: str = ""
    attribution_state: AttributionState = "unattributed"

    # session metadata
    tool: str
    model: str
    source: str = ""
    billing: str = "api"
    start: datetime
    end: datetime

    # token counts
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    # cost
    cost_usd: float = 0.0
    allocated_usd: float = 0.0

    # trust
    trust: Trust = "missing"

    # tags (key:value strings only — no prompt/code content)
    tags: tuple[str, ...] = ()

    # deduplication — SHA-256 of the raw log line
    local_log_line_hash: str = ""

    @property
    def duration_minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60


def _compute_org_trust(direct: float, allocated: float, billing: str) -> Trust:
    """Map session cost figures to an org-level trust label."""
    if direct > 0 and allocated > 0:
        return "mixed"
    if direct > 0:
        return "captured"
    if allocated > 0:
        return "allocated"
    if billing == "api":
        return "captured"  # zero-cost API session (free tier / cached)
    return "missing"  # seat/credits billing but no plan configured


def normalize_session(
    raw_line: str,
    session: object,  # AiSession
    org_config: OrgConfig,
) -> OrgSession:
    """Produce an OrgSession from a raw log line and its parsed AiSession.

    Resolves team/user identity from org_config.  Strips note= content
    unless the org policy permits it (always stripped in this function —
    the caller decides whether to include note in tags).
    """
    from halyard.ai_log import AiSession

    s: AiSession = session  # type: ignore[assignment]

    user_id, team_id = org_config.resolve_user(s.user or "")

    # attribution state
    tags = [t for t in s.tags if not t.startswith("note:")]
    if s.project:
        inferred = any(t == "attribution:inferred" for t in tags)
        attribution_state: AttributionState = "inferred" if inferred else "confirmed"
    else:
        attribution_state = "unattributed"

    # cost figures
    allocated = 0.0
    if s.billing != "api" and s.credits is not None:
        allocated = s.credits

    # trust label (maps ledger "unallocated" → org "missing")
    trust = _compute_org_trust(s.cost_usd, allocated, s.billing)

    return OrgSession(
        org_id=org_config.org.id,
        team_id=team_id,
        user_id=user_id,
        project_id=s.project or "",
        attribution_state=attribution_state,
        tool=s.tool,
        model=s.model,
        source=s.source or "",
        billing=s.billing,
        start=s.start,
        end=s.end,
        input_tokens=s.input_tokens,
        output_tokens=s.output_tokens,
        cache_read_tokens=s.cache_read or 0,
        cache_write_tokens=s.cache_write or 0,
        cost_usd=s.cost_usd,
        allocated_usd=allocated,
        trust=trust,
        tags=tuple(tags),
        local_log_line_hash=hashlib.sha256(raw_line.encode()).hexdigest(),
    )
