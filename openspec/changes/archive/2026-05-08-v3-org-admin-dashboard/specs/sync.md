# Sync and Operations Spec

## Requirement: push-only sync

The org dashboard MUST use a push-only sync model where contributors control
when their data is uploaded.

### Scenario: contributor syncs their data

- WHEN a contributor runs `halyard sync`
- THEN their local session records are normalized and uploaded to the
  configured org endpoint
- AND the local `ai-sessions.log` is not modified
- AND the sync records the last-synced timestamp per log file

### Scenario: idempotent sync

- WHEN the same session is synced twice
- THEN the second sync is a no-op (detected via line hash)
- AND the dashboard does not show duplicate sessions

### Scenario: partial sync on network failure

- WHEN the network fails mid-sync
- THEN already-uploaded records are not re-sent on the next sync
- AND the sync resumes from the last successfully uploaded record

---

## Requirement: privacy boundary in sync

### Scenario: default sync content

- WHEN a session is synced with default settings
- THEN the uploaded record contains only metadata fields (see org-identity.md
  for the normalized schema)
- AND the `note=` field is excluded unless the org policy explicitly enables it
- AND no prompt, code, file path, or transcript content is ever included

### Scenario: org policy disabling note sync

- WHEN an org admin sets `sync_notes = false` in `org.toml`
- THEN all `note=` fields are stripped from normalized records before upload

---

## Requirement: 500-user reporting shape

The org dashboard MUST be designed to handle at least 500 active users without
degrading common query performance.

### Scenario: monthly team rollup at 500 users

- GIVEN 500 users each averaging 20 sessions per day for one month (~300k sessions)
- WHEN a manager queries their 20-person team's monthly spend
- THEN the query resolves in under one second
- AND the result is consistent (no stale reads within a 5-minute window)

### Scenario: org-level summary at 500 users

- WHEN a CIO opens the monthly org overview
- THEN total sessions, spend, tool mix, and active user count render
  without requiring a full table scan at query time
- AND pre-aggregated monthly snapshots are stored per team and per org

---

## Requirement: sync failure and retry states

### Scenario: sync endpoint unavailable

- WHEN the org endpoint returns a 5xx or is unreachable
- THEN `halyard sync` exits with an error and prints the failure reason
- AND no partial state is written locally
- AND the user can re-run sync safely

### Scenario: sync conflict (org key changed)

- WHEN the org endpoint rejects records due to an org ID mismatch
- THEN `halyard sync` prints a clear error naming the conflict
- AND does not silently discard records

---

## Requirement: export API and CSV

### Scenario: CSV export from CLI

- WHEN a user runs `halyard export --period 2026-05 --format csv`
- THEN the output is a well-formed CSV matching the cost center export schema
  defined in cost-centers.md
- AND the file is written to `exports/2026-05-<org>.csv` by default

### Scenario: audit export includes trust labels

- WHEN any export is generated
- THEN the trust column is always included
- AND cannot be omitted

---

## Requirement: retention and audit

### Scenario: session record retention

- WHEN sessions are synced to the org dashboard
- THEN records are retained for at least 12 months by default
- AND an admin can configure a longer retention period

### Scenario: audit log of sync events

- WHEN a sync occurs
- THEN the org dashboard records who synced, when, and how many records
  were uploaded
- AND this audit log is separate from the session data and is not deletable
  by contributors

### Scenario: GDPR-style user data removal

- WHEN an admin removes a user from the org
- THEN the org dashboard can purge that user's session records
- AND the purge is logged in the audit trail
- AND the contributor's local `ai-sessions.log` is not affected
