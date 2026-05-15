# v2.25 — Honors and Achievements

## Why

Halyard tracks a lot of data — sessions, attribution, tokens, cost — but gives
users no feedback about how they are improving as proof-keepers. There's no sense
of progress, identity, or milestones. Users who are doing the right things (clean
attribution, consistent watches, high proof scores) have no way to see that
reflected back at them.

The honors system rewards the behavior Halyard already measures. It does not
introduce new data collection. It is a read-only view onto the existing
`ai-sessions.log` and `time.timeclock` files.

The design philosophy: **reward clean proof, not raw hours.** A user who works
one clean, attributed, token-captured watch per day outranks someone who logs
ten sessions with no attribution. Quantity without quality does not advance rank.

This feature was designed with accessibility in mind: the nautical terminology
has plain-English parentheticals in the CLI, and every achievement has a
click-for-description interaction on the web dashboard.

## What changes

### New module: `src/halyard/achievements.py`

Defines the data model and all computation:

- `RankDef` — a rank definition (level, name, icon, flavor text, description,
  sessions required)
- `Medal` — an achievement definition (key, name, icon, brief description,
  full detail text)
- `ServiceRecord` — computed state for a user: current rank, next rank progress,
  watch streak, clean watches, gold stripe, earned medals, proof score
- `build_service_record(project_dir, sessions)` — reads timeclock + sessions,
  computes the full service record
- Internal helpers: `_extract_watches`, `_watch_streak`, `_clean_watch_streak`,
  `_evaluate_rank`, `_evaluate_medals`, `_compute_proof_score`

### New CLI command: `halyard honors`

Displays the user's full service record in a Rich terminal panel:
- Current rank with icon, name, and flavor text
- Progress bar toward next rank (attributed session count / threshold)
- Stripe count (1 per 7-day watch streak, up to 4 standard + gold at 30)
- All earned medals with description and detail text
- Rank ladder showing all 8 ranks with the current one highlighted

### New dashboard panel: Captain's Quarters

Added to The Bridge (web dashboard) as a full-width panel:
- Rank icon, name, flavor text, and progress bar toward next rank
- Stripe bar with gold stripe indicator if earned
- Medal list with hover-for-detail (title attribute)
- Compact rank ladder sidebar

## What does NOT change

- `ai-sessions.log` — read only, no new fields written
- `time.timeclock` — read only
- No new config files or data formats
- No new collector behavior

## Ranks (identity progression)

| Level | Name | Icon | Sessions required |
|-------|------|------|-------------------|
| 0 | Civilian | ⚓ | 0 (unranked) |
| 1 | Deckhand | 🪢 | 1 |
| 2 | Able Seafarer | ⛵ | 10 |
| 3 | Quartermaster | 📋 | 50 |
| 4 | Navigator | 🧭 | 100 |
| 5 | First Mate | 🔭 | 250 |
| 6 | Captain | 🎖️ | 500 |
| 7 | Commodore | 🏅 | 1000 |

Rank is based on **attributed** session count only. Unattributed sessions do not
advance rank.

## Stripes (reliability/consistency)

- 1 stripe per 7-day watch streak (consecutive calendar days with ≥1 completed
  `halyard start → stop` cycle), up to 4 standard stripes
- Gold stripe: 30+ consecutive clean-watch days (every session on those days
  is attributed + has tokens available)

## Medals (proof moments)

| Key | Name | Icon | Trigger |
|-----|------|------|---------|
| eight_bells | Eight Bells | 🔔 | ≥1 completed watch |
| full_sail | Full Sail | ⛵ | ≥1 watch lasting ≥90 minutes |
| clean_manifest | Order of the Clean Manifest | 📋 | ≥1 day with 0 adrift |
| lighthouse | Lighthouse | 🏮 | ≥1 session attributed via backfill |
| signal_master | Signal Master | 🚩 | Sessions captured from ≥3 distinct AI tools |
| harbor_master | Harbor Master | ⚓ | ≥1 file in `invoices/` directory |
| fair_winds | Fair Winds | 🌬️ | 7+ consecutive clean-watch days |
| rescue | Rescue at Sea | 🆘 | adrift_now == 0 and backfilled ≥5 |

## Deferred (future versions)

- **Passport** — a stamp per AI tool used (visual collection). Requires a
  dedicated UI surface beyond the current dashboard panels.
- **Friends of the Sea** — project completion sea creatures (whale, sea turtle,
  coral reef). Requires a "project completed" signal not yet in the data model.
- **TUI Chart Room** — achievements pane in the TUI. Deferred until TUI matures.
- **Fair Winds / Rescue medals** — the current approximations are correct for v1;
  a future version may use per-watch attribution tracking for more precision.
