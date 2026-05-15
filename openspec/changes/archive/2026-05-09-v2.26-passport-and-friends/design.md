# Design: v2.26 Passport and Friends of the Sea

## Passport

Pure read layer over `ai-sessions.log`. `build_service_record()` in
`achievements.py` already receives the full session list — passport stamps are
computed there alongside medals. No new files, no new data.

```python
# In achievements.py
PASSPORT_STAMPS: dict[str, tuple[str, str]] = {
    "claude-code": ("Claude Code", "🤖"),
    "cursor":      ("Cursor",      "🖱️"),
    "gemini-cli":  ("Gemini CLI",  "♊"),
    "codex":       ("Codex",       "📦"),
    "manual":      ("Manual",      "✏️"),
}
_PASSPORT_DEFAULT = ("Unknown", "🔧")

def _evaluate_passport(sessions: list[AiSession]) -> list[PassportStamp]:
    seen: dict[str, PassportStamp] = {}
    for s in sessions:
        if s.tool not in seen:
            name, icon = PASSPORT_STAMPS.get(s.tool, (_PASSPORT_DEFAULT[0], _PASSPORT_DEFAULT[1]))
            name = name if s.tool in PASSPORT_STAMPS else s.tool
            seen[s.tool] = PassportStamp(tool=s.tool, name=name, icon=icon)
    return list(seen.values())
```

`ServiceRecord` gets a new field: `passport: list[PassportStamp]`.

## Friends of the Sea

### Data file: voyages.toml

Plain TOML, one `[[voyage]]` array entry per project slug. Written atomically
(tmp → rename). The file is in the project directory alongside `halyard.toml`.

```toml
[[voyage]]
slug = "acme:auth"
target_sessions = 50
inactivity_days = 14
stage = "making_headway"
started_at = "2026-04-01"
completed_at = ""
creature = ""
creature_trait = ""
```

### New module: `src/halyard/voyages.py`

```
voyages.py
  VoyageEntry      dataclass — one row in voyages.toml
  VoyageStage      str enum — not_started / anchors_aweigh / making_headway /
                              rounding_the_mark / flying_colors / moored
  PassportStamp    frozen dataclass — tool, name, icon (moved here from achievements)
  read_voyages(project_dir) -> list[VoyageEntry]
  write_voyages(project_dir, entries) — atomic write
  compute_stage(sessions, target) -> VoyageStage
  assign_creature(project_slug, sessions, all_completed) -> tuple[str, str]
                                                            (emoji, trait_name)
  check_auto_complete(project_dir, sessions_by_project) -> list[str]
                                                           (slugs newly completed)
  voyage_for_slug(entries, slug) -> VoyageEntry  (returns default if not found)
```

### Creature assignment implementation

```python
def assign_creature(slug, sessions, all_completed_counts) -> tuple[str, str]:
    total = len(sessions)
    # 1. Whale — highest count of all completed
    if total == max(all_completed_counts.values(), default=0) and total > 0:
        return "🐋", "Massive project"
    # 2. Sea Turtle — spans 3+ months
    if sessions and (sessions[-1].end - sessions[0].start).days >= 90:
        return "🐢", "Long voyage"
    # 3. Dolphin — 0 unattributed
    if sessions and all(s.project for s in sessions):
        return "🐬", "Clean run"
    # 4. Octopus — 3+ tools
    if len({s.tool for s in sessions}) >= 3:
        return "🦑", "Multi-tool"
    # 5. Clownfish — ≤15 sessions, fully attributed
    if total <= 15 and all(s.project for s in sessions):
        return "🐠", "Small but complete"
    # 6. Shark — 5+ sessions in one day
    from collections import Counter
    day_counts = Counter(s.start.date() for s in sessions)
    if day_counts and max(day_counts.values()) >= 5:
        return "🦈", "Intense sprint"
    # 7. Coral Reef — 5+ concurrent active projects (checked at build time)
    # passed in as a flag
    # 8. Seal — fallback
    return "🦭", "Playful"
```

### Auto-complete check

Called from `build_dashboard_state()` and at `halyard voyage` list time.
Checks each non-complete project: if most recent session > inactivity_days ago,
marks it complete and assigns creature. Writes voyages.toml atomically.

### CLI commands

Three new commands under the `voyage` group (like `service`):

```
halyard voyage          — list all project voyage stages
halyard voyage complete <project>  — manually mark complete
halyard voyage set <project> [--sessions N] [--inactivity N] [--creature EMOJI]
```

### Dashboard panels

**Friends of the Sea panel** — new full-width panel on The Bridge, after Captain's
Quarters. Shows completed projects as creature cards. Active projects show their
current stage label and progress (e.g., "Making Headway — 12 / 50 sessions").

**Captain's Quarters** — passport row added below medals showing earned stamp icons
with tool names.

## Trade-offs

| Option | Decision | Reason |
|--------|----------|--------|
| Store voyage state in projects.toml | Separate voyages.toml | Keeps projects.toml for identity; voyages.toml for lifecycle state |
| Compute stages on every render | Yes | Stateless, always correct, negligible cost |
| Whale check vs all-time vs current render | All completed projects at render time | Simple, no historical tracking needed |
| Creature reassignment | Allowed via --creature flag | User knows their project better than the heuristic |
