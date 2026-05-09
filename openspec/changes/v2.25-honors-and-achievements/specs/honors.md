# Spec: Honors and Achievements

Scenarios use WHEN/THEN form. All scenarios are read-only with respect to user
data files — no writes to `ai-sessions.log` or `time.timeclock`.

---

## Rank evaluation

WHEN a user has 0 attributed sessions
THEN their rank is Civilian (level 0)

WHEN a user has exactly 1 attributed session
THEN their rank is Deckhand (level 1)

WHEN a user has exactly 10 attributed sessions
THEN their rank is Able Seafarer (level 2)

WHEN a user has exactly 100 attributed sessions
THEN their rank is Navigator (level 4)

WHEN a user has 99 attributed sessions
THEN their rank is Quartermaster (level 3) and next rank is Navigator

WHEN a user has 1000 or more attributed sessions
THEN their rank is Commodore (level 7) and next_rank is None

WHEN sessions_toward_next is computed for a user at Deckhand with 1 session
THEN sessions_toward_next == next_rank.sessions_required - 1

---

## Watch streak

WHEN there are no completed watches
THEN watch_streak == 0

WHEN a watch was completed today and yesterday and the day before
THEN watch_streak == 3

WHEN a watch was completed today and two days ago (gap yesterday)
THEN watch_streak == 1 (only today counts)

WHEN a watch was completed only yesterday (not today)
THEN watch_streak == 0 (streak must end on as_of date)

---

## Clean watches

WHEN all sessions on a watch day are attributed AND have tokens_available == True
THEN that day is counted as a clean watch day

WHEN any session on a watch day is unattributed OR has tokens_available == False
THEN that day is NOT counted as a clean watch day

---

## Gold stripe

WHEN _clean_watch_streak >= 30
THEN gold_stripe_earned == True

WHEN _clean_watch_streak < 30
THEN gold_stripe_earned == False

---

## Medals

### Eight Bells
WHEN at least one completed watch exists (timeclock i/o pair)
THEN the Eight Bells medal is earned

WHEN no watches exist
THEN Eight Bells is NOT earned

### Full Sail
WHEN at least one watch has duration_minutes >= 90
THEN Full Sail is earned

WHEN all watches have duration_minutes < 90
THEN Full Sail is NOT earned

### Order of the Clean Manifest
WHEN at least one clean watch day exists
THEN the Order of the Clean Manifest is earned

### Lighthouse
WHEN any session has attr_method == "backfill"
THEN the Lighthouse medal is earned

### Signal Master
WHEN sessions from 3 or more distinct tool values exist
THEN Signal Master is earned

WHEN sessions from fewer than 3 distinct tools exist
THEN Signal Master is NOT earned

### Harbor Master
WHEN the `invoices/` directory exists in project_dir AND contains at least one file
THEN Harbor Master is earned

WHEN `invoices/` does not exist or is empty
THEN Harbor Master is NOT earned

### Fair Winds
WHEN _clean_watch_streak >= 7
THEN Fair Winds is earned

### Rescue at Sea
WHEN adrift_now == 0 AND backfilled_count >= 5
THEN Rescue at Sea is earned

---

## Proof score

WHEN there are no sessions
THEN proof_score == 100 (vacuously perfect)

WHEN all sessions are attributed AND all have tokens_available == True
THEN proof_score == 100

WHEN half of sessions are attributed and half have tokens (same half)
THEN proof_score == round(0.5 * 0.6 + 0.5 * 0.4) * 100 == 50

Formula: round((attributed/total * 0.6 + with_tokens/total * 0.4) * 100)

---

## `halyard honors` CLI

WHEN the command is run in a directory with no Halyard project
THEN it exits with code 1 and prints an error

WHEN the command is run in a valid project
THEN it prints a Rich panel with rank, progress bar, stripes, proof score, and medals

WHEN no medals have been earned
THEN it prints "No medals yet — complete watches to start earning honors."

WHEN all ranks are listed
THEN the current rank is marked with a ▶ marker and bold cyan style

---

## Captain's Quarters dashboard panel

WHEN the dashboard is rendered
THEN the Captain's Quarters panel appears in the grid as a full-width panel

WHEN the user is at Commodore rank
THEN the panel shows "✦ Highest rank achieved" instead of a progress bar

WHEN medals are earned
THEN each medal appears with icon, name, and description; the title attribute
     contains the full detail text for hover access

WHEN no medals are earned
THEN the panel shows "No medals yet" placeholder text
