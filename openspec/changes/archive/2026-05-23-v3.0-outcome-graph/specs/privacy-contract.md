# Spec: Privacy Contract for the v3.0 Outcome Graph

The v3.0 outcome graph adds three new classes of local-system access
that did not previously exist in Halyard:

1. Running `gh` on the user's machine with the user's credentials.
2. Running `git` against the user's working trees.
3. Reading the user's shell history file (opt-in).

This spec pins the privacy contract for each. It is a hard contract:
violating any of these requirements MUST cause a release to be held.

## Requirement: No source code, prompt text, or transcript content leaves
any collector, ever.

Every outcome collector — `git_outcome`, `gh_outcome`, `shell_history`,
`attempt_tracker` — MUST emit only one of the following data classes:

- Integer counts (commits, code lines added, code lines removed, test
  runs, attempt counts).
- Bounded enum values (`merged | open | closed | none`).
- Bounded identifiers (`owner/repo#<int>`, branch names, ISO
  timestamps).

Source code, prompt text, transcript content, full file paths beyond the
top-level project directory, environment variables, secrets, shell
arguments, file contents, and diffs MUST NOT appear in any emitted
value.

### Scenario: Source code in a commit message does not leak

WHEN a session's window contains a commit whose body includes verbatim
source code or pasted file contents
THEN the only fields that appear in any session's `a` amendment or
SQLite row are `commit_count` (an integer), `code_added` (an integer),
and `code_removed` (an integer)
AND the commit hash, the commit subject, and the commit body are NOT
written to the log, the cache, or any report output.

### Scenario: A secret in shell history is not captured

WHEN the user's `~/.zsh_history` contains a line like
`OPENAI_API_KEY=sk-... pytest tests/test_secret.py`
THEN `shell_history.count_test_runs_in_window` increments its return
value by 1 (the line is a test run)
AND the line, its tokens, its hash, or any substring of it MUST NOT be
written to the log, the cache, or any other output. Only the integer
count leaves the function.

## Requirement: Outcome collection is opt-out at the project level and
opt-in for the most sensitive source (shell history).

The `[outcomes]` table in `halyard.toml` MUST control every collector:

```toml
[outcomes]
enabled = true               # default: true. Disables ALL collectors when false.
shell_history = false        # default: false. Must be true to read shell history.
```

### Scenario: `enabled = false` disables all outcome collection

WHEN `halyard.toml` contains `[outcomes]\nenabled = false`
THEN every CLI surface (`halyard outcome sync`, `halyard outcome
report`, `halyard outcome attribute`) MUST refuse to run with a clear
message
AND every passive render path (dashboard Leverage panel, TUI outcomes
row, invoice appendix PR refs) MUST not invoke `gh`, `git`, or
`shell_history`.

### Scenario: `shell_history = false` (default) blocks history reads

WHEN `[outcomes]\nshell_history` is unset or false
THEN `shell_history.count_test_runs_in_window` MUST be a no-op (return
0) when called from any outcome sync path
AND no file under `~/.bash_history`, `~/.zsh_history`, `$HISTFILE`, or
`~/.local/share/fish/fish_history` is opened.

## Requirement: Collectors fail closed on permission errors.

A `PermissionError`, `FileNotFoundError`, missing `gh`, missing `git`,
or any other access failure MUST be treated as "signal unavailable"
(silent skip), not as a fatal error and not as a partial leak.

### Scenario: Missing `gh` does not crash a sync

WHEN `gh` is not on PATH
THEN `halyard outcome sync` prints a single hint line and exits cleanly
AND no partial PR data, no stale cache entry, and no exception trace is
emitted.

### Scenario: Unreadable shell history is silent

WHEN the shell history file exists but is mode 0600 owned by a different
user (e.g. on a shared dev box)
THEN `shell_history.count_test_runs_in_window` returns 0
AND no `PermissionError` traceback is shown to the user.

## Requirement: A privacy fuzz test asserts the no-leak contract.

The test suite MUST contain a randomized fuzz test that:

- Generates a large set of synthetic AI sessions whose `branch`,
  `pr_ref`, and other fields contain randomly injected potentially-
  sensitive substrings (paths, secrets, code-like strings).
- Runs every outcome collector and every report rendering path.
- Asserts that none of the injected substrings appears in the
  rendered output, the SQLite cache, the log file, or stderr.

### Scenario: Fuzz test catches a regression

WHEN a future change accidentally writes a session's branch into a
report row that previously displayed only PR state
THEN the privacy fuzz test fails with a diff showing which injected
substring leaked into which output
AND the failing assertion names the responsible collector and surface.
