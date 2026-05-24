# OpenSpec Proposal: v5.0 Duplicate-Effort Detection

## 1. Why
To identify and reduce redundant AI spend and potential merge conflicts by surfacing when multiple AI turns overlap on the same git context.

## 2. What
- **Collision Definition:** Two sessions `A` and `B` collide if:
  1. `A.remote == B.remote` AND `A.branch == B.branch`
  2. `A.interval` overlaps `B.interval` (or `B` starts shortly after `A` finished).
- **Engine Implementation:** A new service in the Hub that queries the cache for recent activity on the same branch.
- **Surface:** Update `halyard status` and the Bridge dashboard to show collision warnings.

## 3. Non-Goals
- Content-based similarity detection (e.g., comparing prompts).
- Automatic session merging (sessions remain distinct log entries).
- Multi-user collision detection (limited to the local machine's log visibility in v5.0).
