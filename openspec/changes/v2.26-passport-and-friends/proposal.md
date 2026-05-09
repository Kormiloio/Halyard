# v2.26 — Passport and Friends of the Sea

## Why

v2.25 introduced ranks, stripes, and medals — rewarding the user as a proof-keeper.
This change adds two complementary layers:

- **Passport** — a collection of stamps, one per AI tool ever used. Celebrates the
  breadth of your AI toolkit. Earned automatically on first captured session per tool.

- **Friends of the Sea** — a collection of sea creatures, one per completed project.
  Each creature reflects the personality of that project's voyage. Rewards finishing
  and documenting work, not just accumulating sessions.

The philosophy carries over from v2.25: **reward behavior Halyard already measures**.
No new data collection. Both features are read-only views over `ai-sessions.log`,
`time.timeclock`, and `projects.toml`.

## Passport

A stamp is earned the first time a session is captured from a given AI tool. The
passport lives in the Captain's Quarters panel (alongside medals) and the
`halyard honors` CLI output.

**Known tools and their stamps:**

| Tool key | Name | Icon |
|----------|------|------|
| claude-code | Claude Code | 🤖 |
| cursor | Cursor | 🖱️ |
| gemini-cli | Gemini CLI | ♊ |
| codex | Codex | 📦 |
| manual | Manual entry | ✏️ |
| unknown | Unknown tool | 🔧 |

Any tool key not in the table gets a generic 🔧 stamp with the raw tool name.

## Friends of the Sea

### Voyage lifecycle

Each project goes through nautical voyage stages based on progress toward a
session-count target:

| Stage | Nautical term | Trigger |
|-------|--------------|---------|
| Not started | — | No sessions yet |
| Started | Anchors Aweigh | First session logged |
| Early progress | Making Headway | ≥25% of target sessions |
| Halfway | Rounding the Mark | ≥50% of target sessions |
| Final stretch | Flying Colors | ≥75% of target sessions |
| Complete | Shipshape · Moored | Target hit OR inactivity trigger |

### Auto-completion

A project is automatically marked complete when no sessions have been logged for
**14 consecutive days** (configurable per project via `projects.toml`). The user
can also complete a project early with `halyard voyage complete <project>`.

### Voyage target

The default target is **20 sessions** for new projects. This can be overridden
per project in `projects.toml` or via `halyard voyage set <project>` with
quick-select presets:

Sessions: 10 / 25 / 50 / 100 / 250
Duration: 1w / 1m / 3m / 6m (converts to an estimated session count based on
the project's current session rate, or uses a flat estimate if no data yet).

### Sea creature assignment

One creature per completed project, evaluated at completion time. First matching
trait wins (priority order):

| Creature | Trait | Condition |
|----------|-------|-----------|
| 🐋 Whale | Massive project | Most sessions of all your completed projects |
| 🐢 Sea Turtle | Long voyage | Project spanned 3+ calendar months |
| 🐬 Dolphin | Clean run | Attribution 100% throughout (0 unattributed sessions) |
| 🦑 Octopus | Multi-tool | 3+ distinct AI tools used on this project |
| 🐠 Clownfish | Small but complete | ≤15 sessions, fully attributed |
| 🦈 Shark | Intense sprint | 5+ sessions in a single day |
| 🪸 Coral Reef | Ecosystem builder | User had 5+ active projects concurrently |
| 🦭 Seal | Playful | Most sessions logged in a single day across this project |

Default fallback (no trait matches): 🦭 Seal.

The user can reassign the creature after the fact via `halyard voyage set <project>
--creature <emoji>` if the automatic assignment feels wrong.

### Data storage

Voyage state is stored in a new file: `voyages.toml` in the project directory.

```toml
# Halyard voyages — one entry per tracked project slug

[[voyage]]
slug = "acme:auth"
target_sessions = 50
inactivity_days = 14
stage = "making_headway"
started_at = "2026-04-01"
completed_at = ""
creature = ""

[[voyage]]
slug = "acme:api"
target_sessions = 20
inactivity_days = 14
stage = "moored"
started_at = "2026-03-15"
completed_at = "2026-04-28"
creature = "🐬"
```

### Friends of the Sea panel (The Bridge)

A new full-width panel on The Bridge showing all completed projects as creature
cards: creature emoji, project slug, completion date, and the trait that earned it.

### CLI

- `halyard voyage` — list all project voyages with current stage
- `halyard voyage complete <project>` — manually mark a project complete
- `halyard voyage set <project>` — set/edit target sessions, inactivity days, or creature

## What does NOT change

- `ai-sessions.log` — read only
- `time.timeclock` — read only
- No new collector behavior
- `projects.toml` — read only (voyage config lives in `voyages.toml`)

## Deferred

- Per-milestone creature awards (one per waypoint vs one per project)
- Passport visual as a grid/stamp-book layout (v1 is a list in Captain's Quarters)
- TUI Chart Room passport/friends pane
