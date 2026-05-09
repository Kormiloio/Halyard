# Spec: v2.24 — AiSession Data Model Changes

## New fields on AiSession

```python
branch: str | None = None           # git branch at session close; trust: captured
commit_count: int | None = None     # commits in session window; trust: captured
code_removed: int | None = None     # lines removed (numstat); trust: calculated
# code_added already exists; extended to all collectors
```

Trust label rules:
- `branch` — `captured` when set from `current_branch()` call; `None` when
  not in a git repo
- `commit_count` — `captured` when set from `commits_in_window()`;
  `None` on git error or timeout
- `code_added` / `code_removed` from Gemini history — `captured`
- `code_added` / `code_removed` from git numstat on Claude/Cursor/Codex —
  `calculated`

## Serialization

Log line additions (written at session close, positional fields unchanged):

```
s <start> <end> <tool> <model> <in_tok> <out_tok> <cost> branch=<name> commit_count=<n> code_added=<n> code_removed=<n> ...
```

All new fields are optional key=value pairs. Absent means `None`; parsers
must not fail on absence.

## Parser migration: branch tag → branch field

`parse_sessions` already handles key=value pairs. Add `branch` to the
`case` dispatch in the KV loop. On read, if `branch=` key is present, use
it. If absent, scan `tags` for an entry matching `branch:*` and promote it
(for backward compatibility with pre-v2.24 log lines). Write path never
emits `branch:` in `tags` after v2.24.

## New fields: pr_ref and pr_state (written by `halyard outcome sync`)

These are never written at session close. They arrive as amendment records:

```
a <session_hash> pr_ref=<owner/repo#nnn> pr_state=<merged|closed|open|none>
```

`parse_sessions` already folds amendment records. Add `pr_ref` and
`pr_state` to the `Amendment.allowed_keys` set and to `AiSession`.

```python
pr_ref: str | None = None           # e.g. "Kormiloio/Halyard#42"
pr_state: str | None = None         # merged | closed | open | none
outcome_resolved_at: str | None = None  # ISO timestamp when resolved
```

## SQLite cache additions (requires v2.18 migration framework)

Migration v1 → v2 adds:

```sql
ALTER TABLE sessions ADD COLUMN branch TEXT;
ALTER TABLE sessions ADD COLUMN commit_count INTEGER;
ALTER TABLE sessions ADD COLUMN code_removed INTEGER;
ALTER TABLE sessions ADD COLUMN pr_ref TEXT;
ALTER TABLE sessions ADD COLUMN pr_state TEXT;
ALTER TABLE sessions ADD COLUMN outcome_resolved_at TEXT;

CREATE TABLE IF NOT EXISTS outcomes (
    session_id TEXT PRIMARY KEY,
    pr_ref TEXT,
    pr_state TEXT,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS pr_cache (
    cache_key TEXT PRIMARY KEY,   -- "<owner>/<repo>/<branch>"
    payload TEXT,                 -- JSON from gh pr list
    fetched_at TEXT               -- ISO timestamp
);
```

TTL for `pr_cache`: entries older than 1 hour are re-fetched on next
`halyard outcome sync` run.
