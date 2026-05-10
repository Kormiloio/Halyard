# Proposal: v2.29 — Pre-Ship Hardening

## Why this change

A PhD-level architecture and security review was conducted on 2026-05-10 in
preparation for the public OSS launch. Seven issues were identified that must be
resolved before the HN / Reddit / Lobsters post goes out. These are not
theoretical risks — they are concrete paths to data corruption, silent billing
errors, and a hard crash on Windows that would make the first comment on every
post "doesn't work on my machine."

This changeset addresses all seven in priority order. Nothing here is a new
feature. Everything here is making Halyard safe to put in front of strangers.

---

## Issue 1 — Windows crash on import (CRITICAL)

### Problem

`ai_log.py` line 5 imports `fcntl` at module level:

```python
import fcntl
```

`fcntl` is a POSIX-only module. It does not exist on Windows. `pyproject.toml`
declares Python 3.11–3.13 with no platform restriction. The README says nothing
about OS requirements. Any user on Windows who runs `pipx install halyard`
receives an unrecoverable `ImportError: No module named 'fcntl'` on the first
CLI command.

### Fix

Two-part:

1. In `ai_log.py`, guard the `fcntl` import with a `sys.platform` check and
   provide a no-op fallback lock context manager for non-POSIX platforms. This
   means Windows users lose concurrent write safety but get a working tool with
   a one-time warning rather than a crash.

2. In `pyproject.toml`, add
   `"Operating System :: POSIX"` and
   `"Operating System :: MacOS"` classifiers so PyPI surfaces the limitation.
   Add a one-line note to the README install section.

### Design decision

We do not attempt full Windows support in v2.29. File locking on Windows
requires `msvcrt.locking` or the `portalocker` package — a non-trivial change
to the concurrency model. The goal here is: no crash, clear explanation, and a
safe degraded mode for the minority of Windows users who install the tool.

---

## Issue 2 — TOML injection via f-string interpolation (MAJOR)

### Problem

Two files build TOML by interpolating user-controlled values directly into
f-strings with no escaping:

**`voyages.py`** (lines ~99–125):
```python
lines.append(f'slug = "{e.slug}"')
lines.append(f'stage = "{e.stage}"')
lines.append(f'creature = "{e.creature}"')
lines.append(f'creature_trait = "{e.creature_trait}"')
```

**`git_context.py`** (line ~178):
```python
lines.append(f'"{k}" = "{v}"')
```

`e.slug` and `v` are project slugs that come from parsed log data. A log entry
whose `project=` value contains a double-quote or newline — possible if a
malicious tool writes to the shared hub log, or if the user manually edits a
log — produces a corrupted or adversarially structured TOML file. On the next
read, `tomllib.loads` raises a `TOMLDecodeError` and Halyard fails to start
until the file is deleted.

A crafted slug like:
```
evil"\n[[voyage]]\nslug="injected
```
would write a syntactically valid TOML block that injects a phantom voyage entry.

### Fix

Replace all manual TOML serialization in both files with `tomli_w.dumps()`.
`tomli_w` is already a declared dependency. The library correctly escapes all
string values including quotes, newlines, and backslashes.

Before:
```python
lines = [f'slug = "{e.slug}"', f'stage = "{e.stage}"']
path.write_text("\n".join(lines))
```

After:
```python
import tomli_w
data = {"slug": e.slug, "stage": e.stage}
path.write_bytes(tomli_w.dumps(data).encode())
```

The full TOML structure in both files must be built as a Python dict/list and
serialized in one call.

---

## Issue 3 — Pricing hash bypass (MAJOR)

### Problem

`pricing.py` line 237 calls `_check_pricing_hash(body)` but discards the
return value:

```python
_check_pricing_hash(body)   # bool return value ignored
new_data = json.loads(body)
...
```

`_check_pricing_hash` prints a warning to `sys.stderr` when the table hash
has changed since the last accepted update, but it never stops the update from
proceeding. A supply-chain attacker who compromises the GitHub raw URL — or a
developer who makes an accidental change to `pricing.json` — gets their table
silently accepted. The only indication is a stderr line that most users running
`halyard update-pricing` in a terminal will scroll past.

For a tool that calculates what to bill clients, a silent pricing table swap is
a billing integrity failure.

### Fix

When `_check_pricing_hash` detects a changed hash:

1. Print the diff summary to stdout (not stderr).
2. Prompt for explicit confirmation: `Accept changed pricing table? [y/N]`.
3. If running non-interactively (no TTY), abort with a non-zero exit code and
   instruct the user to run `halyard update-pricing --accept-changed` to
   override.

Add `--accept-changed` flag to `halyard update-pricing` that skips the prompt
(for CI / scripted use). Without the flag, a changed hash is always an
interactive decision.

---

## Issue 4 — `_session_line_hash` produces wrong hashes (MAJOR)

### Problem

`outcomes.py` lines 255–261 define:

```python
def _session_line_hash(project_dir: Path, session: AiSession) -> str:
    return session_hash(session.to_log_line())
```

`session_hash` in `ai_log.py` is designed to hash the *raw `s` line as it
exists in the log file*. But by the time a session reaches `_session_line_hash`,
`parse_sessions` has already folded all `a` amendment records into it — mutating
fields like `project`, `pr_ref`, `pr_state`. Calling `to_log_line()` on this
mutated object produces a line that differs from the original `s` line in the
file, so its hash is different from what any `a` record references.

Consequence: when `halyard outcome sync` runs on a session that was already
backfill-attributed (project field changed by an `a` record), the amendment it
writes references a hash that `parse_sessions` cannot find when it folds
amendments. The outcome data is written to the log but never read back. The
outcome fields (`pr_ref`, `pr_state`) appear in the log but are silently ignored.

### Fix

`AiSession` must carry the hash of its original `s` line as a read-only field,
set at parse time from the raw log line, before any amendment folding:

```python
@dataclass
class AiSession:
    ...
    _raw_hash: str | None = field(default=None, repr=False, compare=False)
```

In `_parse_session_line` (ai_log.py), set `_raw_hash = session_hash(raw_line)`
immediately after parsing the `s` line, before amendments are applied.

`_session_line_hash` then becomes:

```python
def _session_line_hash(session: AiSession) -> str:
    return session._raw_hash or session_hash(session.to_log_line())
```

Add a regression test covering:
`parse_sessions` → apply amendment → `_session_line_hash` → confirm hash
matches the original `s` line.

---

## Issue 5 — SQLite cache goes stale silently (MAJOR)

### Problem

`db.py` `_sync_sessions` uses `INSERT OR IGNORE` to populate the sessions
table:

```python
cursor.execute(
    "INSERT OR IGNORE INTO sessions VALUES (...)",
    row_values,
)
```

Sessions that receive `a` amendment records *after* the initial sync are never
updated in the cache. For example: a session is synced, later attributed to a
project via `halyard assign-unattributed`, and later still linked to a PR via
`halyard outcome sync`. The cache row retains the original unattributed,
no-PR state indefinitely.

`halyard report --from-cache` and the dashboard's fast-path read silently serve
stale data. There is no way for the user to know the cache is wrong short of
wiping and re-syncing.

### Fix

Change `INSERT OR IGNORE` to `INSERT OR REPLACE` in `_sync_sessions`. This
overwrites the existing row on conflict, so re-running `halyard db sync`
always brings the cache into full agreement with the current log state.

Check whether any downstream code depends on row IDs being stable across
syncs. If so, use `INSERT OR REPLACE` only on the content columns and preserve
the rowid.

Add a test: sync → amend log → re-sync → confirm cache row reflects amendment.

---

## Issue 6 — Datetime timezone inconsistency (MAJOR)

### Problem

`AiSession.start` is a naive `datetime` throughout the system, but different
collectors produce it from different sources:

| Collector | How `start` is set | Actual timezone |
|---|---|---|
| `claude_code.py` | `datetime.now(UTC)` stripped of tzinfo | UTC |
| `cursor.py` | `datetime.now()` | Local |
| `gemini.py` | `datetime.now()` | Local |
| `codex.py` | `datetime.now()` | Local |
| `orchestration.py` (timeclock) | `datetime.now()` | Local |

All sessions land in `AiSession.start` as timezone-naive. Report and budget
filtering compares `session.start.date()` to `datetime.now().date()`. A user in
UTC-5 who has Claude Code sessions and Cursor sessions on the same evening will
see different day-boundary behaviour between the two tools. Invoice line items
can be wrong by one day.

The root cause is in `claude_code.py` `record_session_start()`, which correctly
uses UTC internally for the hooks system but then tries to convert back to local
in `_read_session_state()` with a fragile offset calculation.

### Fix

Standardize on **local-naive time** throughout `AiSession`:

1. `claude_code.py` `record_session_start()`: store start as local time
   (`datetime.now()`) instead of UTC. Remove the UTC conversion in
   `_read_session_state()`.
2. `_read_session_state()`: simplify — stop trying to detect and convert UTC
   timestamps. Read the stored ISO string and parse it as local naive.
3. Audit all four collectors and `orchestration.py` to confirm they all use
   `datetime.now()` (local naive) for `AiSession.start` and `AiSession.end`.
4. Add a test that constructs sessions in UTC-offset environments and confirms
   `session.start.date()` always matches the local calendar date.

**Why local-naive, not UTC-aware?** The log format is local time (the timeclock
entries are human-readable local times, the `ai-sessions.log` lines are local
time). Switching to UTC-aware would require a log format migration. Local-naive
is consistent with the existing file format and the user's mental model
("I worked on Tuesday evening").

---

## Issue 7 — No OS declaration (MAJOR for OSS release)

### Problem

`pyproject.toml` has no `Operating System` classifiers. The README install
section says nothing about platform requirements. Windows users discover the
`fcntl` crash only after installation. macOS-only shell commands (`launchctl`,
plist files) are referenced in the service install code without documentation.

### Fix

1. Add to `pyproject.toml` classifiers:
   ```
   "Operating System :: MacOS",
   "Operating System :: POSIX",
   "Operating System :: POSIX :: Linux",
   ```
2. Add to README install section:
   > **Platform:** macOS and Linux. Windows is not supported (file locking
   > requires POSIX `fcntl`). WSL2 works.
3. Add a platform check to `halyard doctor` output — flag Windows as
   unsupported and suggest WSL2.

---

## Files changed

| File | Change |
|---|---|
| `src/halyard/ai_log.py` | Platform guard on `fcntl` import; `_raw_hash` field on `AiSession`; set hash in `_parse_session_line` |
| `src/halyard/outcomes.py` | `_session_line_hash` uses `session._raw_hash`; remove `project_dir` arg |
| `src/halyard/db.py` | `INSERT OR IGNORE` → `INSERT OR REPLACE` in `_sync_sessions` |
| `src/halyard/voyages.py` | Replace f-string TOML with `tomli_w.dumps()` |
| `src/halyard/git_context.py` | Replace f-string TOML with `tomli_w.dumps()` |
| `src/halyard/pricing.py` | Abort or prompt on hash change; add `--accept-changed` flag |
| `src/halyard/cli.py` | `--accept-changed` flag on `update-pricing` command |
| `src/halyard/collectors/claude_code.py` | Store start as local naive; simplify `_read_session_state` |
| `src/halyard/collectors/cursor.py` | Confirm uses `datetime.now()` — no change expected |
| `src/halyard/collectors/gemini.py` | Confirm uses `datetime.now()` — no change expected |
| `src/halyard/collectors/codex.py` | Confirm uses `datetime.now()` — no change expected |
| `pyproject.toml` | Add OS classifiers |
| `README.md` | Add platform note to install section |
| `tests/test_outcomes.py` | Regression test for `_session_line_hash` round-trip |
| `tests/test_db.py` | Test: sync → amend → re-sync confirms cache update |
| `tests/test_pricing.py` | Test: changed hash prompts / aborts without `--accept-changed` |
| `tests/test_platform.py` | Test: `fcntl` guard produces no-op on non-POSIX; platform check in doctor |

---

## Success criteria

1. `pipx install halyard && halyard init` on Windows produces a clear, friendly
   error message — not an `ImportError` traceback.
2. `halyard update-pricing` with a changed hash prints the diff and prompts.
   Without `--accept-changed`, it exits non-zero if not confirmed.
3. A voyage with `slug = 'evil"]\n[[voyage]]'` produces valid, parseable TOML.
4. `halyard outcome sync` on a backfill-attributed session writes an amendment
   that `parse_sessions` correctly folds back in on the next read.
5. `halyard db sync` run after a log amendment updates the cache row to reflect
   the amended values.
6. Sessions from `claude_code` and `cursor` on the same evening fall on the
   same calendar date in all reports.
7. `halyard doctor` on Windows outputs an explicit "platform not supported"
   warning.
8. All 921 existing tests continue to pass; ≥ 12 new tests added.
