# Org Identity Spec

## Requirement: org and team mapping

The org admin dashboard MUST support a file-based org identity model that maps
contributors to teams and teams to departments.

### Scenario: org.toml defines the org hierarchy

- WHEN `org.toml` exists at the Halyard hub root
- THEN the dashboard reads org name, departments, and teams from it
- AND does not require an external identity provider

### Scenario: user-to-team mapping by git email

- WHEN a contributor's `ai-sessions.log` includes a `user=` field
- THEN the dashboard resolves that user to a team via the `org.toml` mapping
- AND falls back to "(unassigned)" if the user is not listed

### Scenario: machine-generated org.toml from GitHub/SCIM

- WHEN an admin generates `org.toml` from a GitHub org or SCIM directory
- THEN the format is identical to a hand-edited file
- AND Halyard treats both as equally authoritative

---

## Requirement: normalized org event schema

The org admin dashboard MUST define a normalized event schema that can be
produced from any local `ai-sessions.log` without changing the local format.

### Scenario: metadata-only sync

- WHEN a local session record is normalized for the org dashboard
- THEN the normalized record includes:
  - org_id, team_id, user_id (resolved from org.toml)
  - project_id (from project= field)
  - tool, model, source, billing
  - start, end (ISO timestamps)
  - input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
  - cost_usd, allocated_usd (from ledger at sync time)
  - trust (captured / calculated / allocated / inferred / missing)
  - attribution_state (confirmed / inferred / unattributed)
  - tags (list of key:value strings, stripped of any prompt or code content)
- AND the normalized record does NOT include prompt text, code content,
  file paths, or session transcripts

### Scenario: local log semantics preserved

- WHEN sessions are synced
- THEN the local `ai-sessions.log` is not modified
- AND the normalized record carries a `local_log_line_hash` for deduplication
- AND re-syncing an already-synced record is idempotent

### Scenario: session without org.toml resolution

- WHEN a session cannot be resolved to a team (user not in org.toml)
- THEN the normalized record sets team_id to "(unassigned)"
- AND the session is still synced — it appears in governance as a coverage gap

---

## `org.toml` Schema

```toml
[org]
id = "acme-corp"           # required; slug used as foreign key in records
name = "Acme Corp"         # display name

[[department]]
id = "engineering"
name = "Engineering"

[[team]]
id = "auth-team"
name = "Auth"
department_id = "engineering"

[[member]]
email = "alice@acme.example"   # matches git config user.email
team_id = "auth-team"
display_name = "Alice"         # optional; used in dashboard
```
