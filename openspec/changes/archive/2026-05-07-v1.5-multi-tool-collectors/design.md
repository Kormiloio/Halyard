# Design: Multi-Tool Collectors and Ambient Capture

## Collector architecture

Every collector follows the same contract:

1. Read a payload (from stdin as JSON, or from a file on disk).
2. Resolve a `project_dir`: try `find_project_dir(start=cwd)` first, then
   fall back to `find_hub()`. If neither resolves, return 0 silently.
3. Check that `project_dir / ai-sessions.log` exists (project initialised).
4. Build an `AiSession` with project attribution from: active timer →
   git inference → `None`.
5. Append to `project_dir / ai-sessions.log`.

The fallback chain is the core of ambient capture. The order matters:

```
find_project_dir(start=cwd)  →  find_hub()  →  drop
```

If the developer is inside a Halyard project tree, that project's log gets
the session (same as v1). Otherwise the hub absorbs it. Only if no hub is
configured does the session get dropped — and `halyard hub` makes this
condition visible.

---

## Codex collector (`collectors/codex_app.py`)

Codex Desktop writes JSONL session files at:
`~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<uuid>.jsonl`

Each file is a single session. Events of interest:

| Event type    | Relevant fields                                          |
|---------------|----------------------------------------------------------|
| `session_meta`| `payload.cwd`, `payload.timestamp` (session start)      |
| `turn_context`| `payload.cwd`, `payload.model`                           |
| `event_msg`   | `payload.type == "token_count"` → `payload.info.total_token_usage` |

Token usage fields in `total_token_usage`:
- `input_tokens` — total input (includes cached)
- `cached_input_tokens` — cached portion
- `output_tokens` — output

Net input = `input_tokens - cached_input_tokens`. Codex billing is
`billing=credits` (bundled plan); `cost_usd=0.0`.

Sessions with `output_tokens == 0` are skipped (plugin-init sessions).

**Deduplication state:** `~/.halyard/codex-imported` — one session UUID
per line. On each import run, already-seen UUIDs are skipped and new ones
are appended atomically.

**Import command:** `halyard import-codex [--dry-run] [--all]`

---

## Gemini CLI collector (`collectors/gemini_cli.py`)

Gemini CLI fires three hook types relevant to session recording:

```
SessionStart → [N × AfterModel] → AfterAgent
```

One `AfterAgent` = one completed turn. Multiple turns may occur within a
single Gemini CLI session (the process stays alive between prompts).

### The token accumulation problem

`AfterAgent` contains only text output — no token counts. Token data comes
from `AfterModel`, which fires once per API call within a turn.

Gemini's `usageMetadata` is **cumulative across the conversation**: each
`AfterModel` event's `promptTokenCount` includes the full conversation
history, not just the new prompt. `candidatesTokenCount` is per-call.

State accumulated in `~/.halyard/gc-session` (JSON) across the three hooks:

| State key      | Update rule                                             |
|----------------|---------------------------------------------------------|
| `turn_start`   | Set by `SessionStart`, reset by `AfterAgent`            |
| `session_id`   | Set by `SessionStart`                                   |
| `cwd`          | Set by `SessionStart`                                   |
| `model`        | Set by `AfterModel`, kept for `AfterAgent`              |
| `prompt_tokens`| `max(current, new promptTokenCount)` — largest wins     |
| `output_tokens`| `sum(candidatesTokenCount)` across all AfterModel calls |
| `cache_tokens` | `max(current, new cachedContentTokenCount)`             |

At `AfterAgent`:
```
net_input  = prompt_tokens - cache_tokens
cost_usd   = calculate_cost(model, net_input, output_tokens, cache_read=cache_tokens)
billing    = "api"
```

`_reset_state()` clears token accumulators and advances `turn_start` for the
next turn, but preserves `session_id` and `cwd`.

### Install command

`halyard install-gemini-hook` writes to `~/.gemini/settings.json`:
```json
{
  "hooks": {
    "SessionStart": [{"matcher": "*", "hooks": [{"name": "halyard", "type": "command", "command": "<exe> gc-session"}]}],
    "AfterModel":   [{"matcher": "*", "hooks": [{"name": "halyard", "type": "command", "command": "<exe> gc-model"}]}],
    "AfterAgent":   [{"matcher": "*", "hooks": [{"name": "halyard", "type": "command", "command": "<exe> gc-hook"}]}]
  }
}
```

---

## Cursor collector (`collectors/cursor.py`)

Cursor fires two hooks:

| Hook                | Entry point          | Payload                         |
|---------------------|----------------------|---------------------------------|
| `beforeSubmitPrompt`| `cursor-session`     | (timing only — no payload used) |
| `stop`              | `cursor-hook`        | Claude Code Stop payload + Cursor extras |

Additional Cursor fields in the `stop` payload:

| Field             | Use                                                  |
|-------------------|------------------------------------------------------|
| `cursor_version`  | Presence indicates Cursor fired the hook             |
| `workspace_roots` | VS Code workspace folders — used for project lookup  |
| `user_email`      | For future multi-user attribution                    |

**Project resolution:** `workspace_roots[0]` is the authoritative source.
If `workspace_roots` is non-empty but none of them map to a Halyard project,
return `None` — do not fall back to CWD. (CWD in a Cursor hook context is the
terminal's CWD, not the workspace.) After per-tool resolution fails, the hub
fallback applies normally.

**Billing:** `billing=credits` — Cursor routes through its own backend.
`tokens_available=false` is expected and permanent. `cost_usd=0.0`.

**Duplicate guard in Claude Code:** Claude Code hooks are global and also
fire for Cursor sessions (Cursor uses the Claude Code hook infrastructure
internally). `handle_stop_hook()` in `claude_code.py` checks for
`cursor_version` in the payload and returns early when present, deferring
to the Cursor collector.

### Install command

`halyard install-cursor-hook` writes to `~/.cursor/hooks.json`:
```json
{
  "version": 1,
  "hooks": {
    "beforeSubmitPrompt": [{"command": "<exe> cursor-session"}],
    "stop":               [{"command": "<exe> cursor-hook"}]
  }
}
```

---

## Hub (`hub.py`)

A hub is any Halyard project directory that has been designated as the global
fallback. Its `ai-sessions.log` receives sessions from all tools when no
local project matches.

```
~/.halyard/hub   →  one line: absolute path to the hub directory
```

`find_hub() → Path | None` — reads the pointer, validates the directory
exists, returns `None` otherwise (silently — a missing hub is allowed).

`set_hub(path)` — writes the pointer (created by `halyard init --hub` or
`halyard hub <path>`).

The hub is a normal Halyard project in every other respect: it has a
`halyard.toml`, `ai-sessions.log`, and can be reported on with
`halyard report`. The only special behaviour is being the fallback target.

---

## Git context (`git_context.py`)

### Project inference

```
infer_project(cwd: Path) → str | None
```

1. Run `git -C <cwd> remote get-url origin` (2s timeout).
2. Normalize the URL: strip protocol, convert `git@host:user/repo` form,
   strip `.git` suffix → `host/user/repo`.
3. Check `~/.halyard/repos.toml` `[repos]` table for an explicit match.
   Patterns support `*` as a within-segment wildcard (`github.com/acme/*`).
4. If no explicit match: return `git/<repo-name>` as an auto-slug.
5. If git fails or no remote: return `None`.

```toml
# ~/.halyard/repos.toml
[repos]
"github.com/acmecorp/auth-service" = "acme:auth"
"github.com/acmecorp/*"            = "acme:general"
```

### Branch tagging

```
current_branch(cwd: Path) → str | None
```

Runs `git -C <cwd> branch --show-current` (2s timeout). Returns the branch
name or `None` if not in a repo or on a detached HEAD.

All four collectors attach `tags=[f"branch:{branch}"]` when a branch is
found. This enables `ai-sessions.log` to answer: "what did the
`feature/auth-migration` branch cost?"

### CLI integration

`halyard link-repo <slug>` runs `current_remote()` (git remote of CWD),
calls `register_repo(remote, slug)`, and writes to `~/.halyard/repos.toml`.

---

## Absolute path embedding in install commands

Hooks run in isolated shell environments (Gemini CLI, Cursor, Claude Code all
exec hook commands directly). The `PATH` available to a hook command is often
not the user's shell PATH — `halyard` might not be findable.

All three install commands resolve the executable path at install time via
`_halyard_exe()`:

```python
def _halyard_exe() -> str:
    candidate = Path(sys.argv[0]).resolve()
    if candidate.name in ("halyard", "halyard.exe") and candidate.exists():
        return str(candidate)
    found = shutil.which("halyard")
    if found:
        return str(Path(found).resolve())
    return "halyard"  # fallback: trust PATH at hook-run time
```

Hook configs embed the resolved absolute path (e.g.
`/Users/mario/.local/share/uv/tools/halyard/bin/halyard gc-hook`) rather
than the bare `halyard` command. Re-running the install command after
upgrading Halyard updates the path if it changed.

---

## Token attribution for project-level cost queries

With branch tagging, a query for "AI cost on the auth-migration branch" is
a grep + sum on the log:

```bash
grep "branch:feature/auth-migration" ai-sessions.log \
  | awk '{for(i=1;i<=NF;i++) if($i~/^cost_usd=/) print substr($i,9)}' \
  | awk '{s+=$1} END {print s}'
```

This is the baseline. A future `halyard report --branch <name>` command will
surface this in the CLI.

---

## What was deliberately not built

**Dynamic pricing sync (`halyard update-pricing`):** The pricing table is
snapshot-based. Proposal: a v2 command fetches from a community-maintained
source. Not built here because the snapshot covers current models and the
mechanism (where to fetch from, how to validate, key format) needs its own
spec.

**Budget enforcement:** A per-project `daily_limit_usd` in `halyard.toml`
with a hook that warns or blocks when the limit is reached. Not built here —
the check would need to run synchronously in the hook path, which has
latency implications worth speccing separately.
