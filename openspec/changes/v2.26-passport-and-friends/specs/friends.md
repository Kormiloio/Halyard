# Spec: Friends of the Sea

## voyages.toml

WHEN `voyages.toml` does not exist in the project directory
THEN all voyage functions treat all projects as having default settings
     (target_sessions=20, inactivity_days=14, stage=not_started)

WHEN `voyages.toml` exists with a voyage entry for slug "acme:auth"
THEN that project uses the configured target_sessions and inactivity_days

## Voyage stage computation

WHEN a project has no sessions
THEN its stage is "not_started"

WHEN a project has at least 1 session AND sessions < 25% of target
THEN its stage is "anchors_aweigh"

WHEN sessions >= 25% of target AND < 50%
THEN its stage is "making_headway"

WHEN sessions >= 50% of target AND < 75%
THEN its stage is "rounding_the_mark"

WHEN sessions >= 75% of target AND < 100%
THEN its stage is "flying_colors"

WHEN sessions >= target
THEN the project is automatically marked complete ("moored")

WHEN the most recent session for a project is older than inactivity_days
AND the project is not already complete
THEN the project is automatically marked complete ("moored")

WHEN a project is marked complete
THEN its creature is evaluated and stored in voyages.toml

## Creature assignment

WHEN a project is marked complete, creature is assigned by first matching rule:

1. 🐋 Whale — this project has the highest session count of all completed projects
2. 🐢 Sea Turtle — first session to last session spans 3+ calendar months
3. 🐬 Dolphin — zero unattributed sessions throughout the project's life
4. 🦑 Octopus — 3 or more distinct tool values used on this project
5. 🐠 Clownfish — total sessions ≤ 15 AND zero unattributed sessions
6. 🦈 Shark — at least one day with 5+ sessions for this project
7. 🪸 Coral Reef — user had 5+ distinct active projects concurrently at any point
8. 🦭 Seal — fallback; always matches

WHEN the user runs `halyard voyage set <project> --creature 🐬`
THEN the creature field in voyages.toml is updated to the provided value
     (overrides automatic assignment)

## halyard voyage (list)

WHEN `halyard voyage` is run with a valid project directory
THEN it lists all known projects with their current stage, session count,
     target, and creature (if complete)

WHEN a project has no voyage entry in voyages.toml
THEN it appears with default settings and stage computed from sessions

## halyard voyage complete

WHEN `halyard voyage complete acme:auth` is run
AND the project exists in ai-sessions.log
THEN the project is marked complete in voyages.toml, creature is assigned,
     and the user sees a completion card with the creature and trait

WHEN the project is already complete
THEN the command prints "acme:auth is already moored." and exits 0

## halyard voyage set

WHEN `halyard voyage set acme:auth --sessions 50` is run
THEN voyages.toml is updated with target_sessions=50 for that project

WHEN `halyard voyage set acme:auth --inactivity 7` is run
THEN voyages.toml is updated with inactivity_days=7 for that project

WHEN `halyard voyage set acme:auth --creature 🐬` is run
THEN voyages.toml is updated with creature="🐬" for that project

## Friends of the Sea panel (dashboard)

WHEN the dashboard is rendered and at least one project is complete
THEN the Friends of the Sea panel appears with creature cards for each
     completed project (creature icon, slug, completion date, trait name)

WHEN no projects are complete
THEN the panel shows "No voyages complete yet — keep sailing."

WHEN the dashboard is rendered
THEN active projects show their current voyage stage with the nautical term
     (e.g., "Making Headway — 12 / 50 sessions")
