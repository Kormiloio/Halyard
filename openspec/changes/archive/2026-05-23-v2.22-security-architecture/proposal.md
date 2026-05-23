# Proposal: v2.22 — Security Architecture

## Why this change

Sage's architectural security review identified three medium-severity
design-level risks that were not covered by Adrian's targeted scan (v2.20).
Where Adrian found exploitable paths in the existing implementation, Sage
identified structural gaps: places where the system's *design* produces
a class of risk, not just a specific bug.

The three findings:

- **D-3 (org.toml integrity):** `org.toml` is loaded on every run but there
  is no change detection. If an attacker or misconfiguration silently alters
  the org mapping between runs, historical sessions may be re-attributed to
  the wrong client without any warning. The system has no awareness that the
  authoritative source of truth has changed.

- **D-4 (plist XML injection):** `service.py` constructs the launchd plist
  by string interpolation, including `project_dir` values that can contain
  characters meaningful to XML (`<`, `>`, `&`). A project directory with such
  characters would produce a malformed or exploitable plist.

- **D-5 (pricing table hash pinning):** The remote pricing table is fetched
  and accepted without verification. A network attacker or a server-side
  mistake could serve a modified pricing table, silently altering cost
  calculations.

In addition, Sage identified 10 test coverage gaps where the existing
test suite does not exercise important edge cases in the core data path.
These gaps do not indicate known bugs, but they leave the system relying on
correctness-by-inspection in areas where the cost of a bug is high (session
data integrity, attribution accuracy, financial calculations).

## What this change does

### D-4: Plist XML injection (highest priority)

`service.py` will use `xml.sax.saxutils.escape()` on all interpolated strings
before inserting them into the plist XML template. This is a standard library
function with no new dependencies.

### D-3: org.toml change detection

When `org.toml` is loaded, a SHA-256 hash of its content is computed and
compared against the hash stored in `~/.halyard/org-hash.txt` from the
previous run. If the hashes differ, a warning is logged:

```
[halyard] Warning: org.toml has changed since last run. Historical sessions
may be re-attributed on next sync. Review changes with 'halyard org diff'.
```

The new hash is stored for the next run regardless (the warning is
informational, not blocking).

### D-5: Pricing table hash pinning

When the remote pricing table is fetched, the response body is hashed
(SHA-256) and compared against the last-known-good hash stored in
`~/.halyard/pricing-hash.txt`. If the hashes differ, a warning is printed
before the new table is accepted. The new hash is not persisted until the
user explicitly accepts the new table (or it can be auto-accepted in a future
policy flag).

### Test coverage gaps (10 items)

Sage identified the following gaps. Each will be covered by a new test:

1. **Session round-trip fidelity:** write a session → parse → assert all
   fields identical.
2. **`~/.halyard/active` concurrent-write simulation:** two writes in flight,
   reader always returns a complete slug.
3. **Partial active file read:** truncated write → `read_active_project`
   returns `None`, not a malformed slug.
4. **org.toml change detection:** hash changes between runs produce a warning.
5. **Attribution cascade priority:** timer attribution takes precedence over
   git inference when both are present at session end.
6. **Plist XML injection:** `project_dir` with `<`, `>`, `&` characters
   produces valid XML in the generated plist.
7. **Gemini session-id 8-char prefix collision:** two sessions with matching
   8-character prefixes are attributed independently.
8. **Pricing table partial-fetch:** a truncated HTTP response does not
   overwrite the local pricing table.
9. **`read_sessions` tool limit parameter:** a large `limit` value does not
   cause OOM or excessive query time.
10. **`_validate_base_url` with localhost variants:** `127.0.0.1`, `localhost`,
    `::1` all accepted; port variants (`:8080`, etc.) work correctly.

## What this change does NOT do

- No changes to the log format.
- No new user-facing commands (the hash-diff warning uses existing stderr
  output conventions).
- No cloud or network dependencies — pricing-hash.txt is local state.

## Key decisions

**Why xml.sax.saxutils over a templating approach for the plist?**

The plist is a small, well-defined XML structure. `saxutils.escape()` is
standard library, zero new dependencies, and closes the injection risk with
minimal code change. A full XML templating approach would be over-engineering
for a file with three interpolated values.

**Why warn rather than block on hash change?**

For org.toml: blocking on hash change would prevent legitimate updates from
taking effect without user intervention — an operational burden. Warnings
preserve visibility without creating friction.

For pricing: blocking would require a user confirmation flow that doesn't yet
exist. The warning-then-accept model is the right first step; a policy flag
can be added later.

**Why store hashes in ~/.halyard/ rather than alongside the source files?**

org.toml and the pricing table may be read-only or version-controlled. Storing
the hash in `~/.halyard/` keeps the runtime state separate from the
configuration, consistent with the existing convention for all agent state.

## Success criteria

- Plist generation with `project_dir` containing `<`, `>`, `&` produces
  valid XML (verified by XML parser).
- org.toml hash mismatch produces a visible warning on the next run.
- Pricing table fetch with a changed body produces a visible warning before
  accepting the new table.
- All 10 test coverage gaps have passing tests.
- ruff and mypy report no new errors.
