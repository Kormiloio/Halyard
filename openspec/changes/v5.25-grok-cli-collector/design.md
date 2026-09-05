# Design: v5.25 — Grok CLI Collector

> **Phase 0 complete (2026-08-10).** A real session was run and the
> on-disk layout inspected. The vendor docs were right about the directory
> shape and wrong about where usage lives; corrections below.

## Phase 0 findings

### 1. Session layout is as documented

```
~/.grok/sessions/<url-encoded-cwd>/<session-id>/
  summary.json          # rich metadata — the primary source
  updates.jsonl         # ACP stream; carries the only token counter
  chat_history.jsonl    # raw messages          ← never read
  events.jsonl          # tracing: phases, tool calls, MCP init
  prompt_context.json, resources_state.json, system_prompt.txt
  announcement_state.json, terminal/
~/.grok/sessions/session_search.sqlite   # local search index
```

Observed group: `%2FUsers%2F…%2FNautilus`; session id
`019febb6-13af-7382-8595-be0246e25bf8` (UUIDv7, as documented).

### 2. `signals.json` does not exist

`17-sessions.md` documents `signals.json` as holding "token usage,
tool/turn counters". **There is no such file** in a real session
directory. The design's original plan to read it as the authoritative
token source is void. Treat the vendor docs as a hint, never as a
contract — this is the second doc/reality mismatch in two collectors
(Antigravity's `transcriptPath` was the first).

### 3. `summary.json` is the primary source, and it is rich

```json
{
  "info": {"id": "019febb6-…", "cwd": "/Users/…/Nautilus"},
  "session_summary": "Full Project Source Code Review",
  "created_at": "2026-08-10T12:46:46.269749Z",
  "updated_at": "2026-08-10T12:47:48.264174Z",
  "last_active_at": "2026-08-10T12:47:48.264174Z",
  "num_messages": 33,
  "num_chat_messages": 18,
  "current_model_id": "grok-4.5",
  "git_root_dir": "/Users/…/Nautilus/",
  "git_remotes": ["https://github.com/mcamaj/Nautilus.git"],
  "head_commit": "2c8a817…",
  "head_branch": "agent/add-200-day-learning-voyage",
  "agent_name": "grok-build-plan",
  "reasoning_effort": "high",
  "sandbox_profile": "off"
}
```

Consequences, all simplifying:

- **A real model id** (`grok-4.5`), unlike Antigravity's `"auto"`.
- **`info.cwd` is authoritative for attribution.** The planned
  URL-decode of the group directory name, and the `.cwd` fallback for the
  255-byte hashed-slug case, are both **unnecessary** — read `cwd`
  directly. Keep group-name decoding only as a last resort if `cwd` is
  ever missing.
- **Git outcome metadata for free**: `git_remotes`, `head_branch`,
  `head_commit` map onto `remote`, `branch`, and commit-window logic
  without shelling out to git.
- Timestamps are ISO-8601 **UTC with `Z`** and microseconds — same
  local-conversion requirement as Antigravity.

### 4. Tokens exist, but only as an undifferentiated total

The only usage figure anywhere is in `updates.jsonl`, at
`params._meta.totalTokens`:

```json
{"totalTokens": 4272, "eventId": "…-44", "agentTimestampMs": 1786366034619,
 "promptId": "…", "streamStartMs": …, "turnStartMs": …,
 "updateType": "AgentThoughtChunk", "chunkId": 42}
```

It is cumulative and monotonic across the session (4272 → 13649 → …
→ 29951). There is **no input/output split and no cache breakdown**.

This forces two decisions:

**a. The "never read `updates.jsonl`" rule needs narrowing, not keeping.**
The original design barred that file outright to protect content. But the
token counter only lives there. Revised rule: read **only**
`params._meta.totalTokens` — a single integer — and never `params.update`,
which is where message content lives. This still satisfies
non-negotiable 5 (metadata, not content), and a test must assert no
content field is ever touched.

**b. Cost cannot be computed, so it is not claimed.**
Halyard prices input and output at different rates
(`grok-3` is 3.00/15.00 per Mtok). With only a total, any cost figure
requires inventing an input/output ratio — that is a guess wearing a
number's clothes, and non-negotiable 6 forbids dressing it as observed.

Independently, `grok-4.5` is **not in `pricing.py`** at all (only `grok-3`
and `grok-3-mini`), so even a split would not price today.

And the account is subscription-authenticated (`grok login`, no
`XAI_API_KEY`), so per-token cost is not what the user is billed anyway.

**Decision:** emit `billing=credits`, `cost_usd=0`, real
`total tokens`, `tokens_available=true`. This is the Codex/Cursor shape
already in the ledger (161 `billing=credits` rows today), and
`sum_spend`'s `api_only` filter excludes it from spend on the
`billing != "api"` condition — the same quarantine v5.24 relies on, but
here with genuine token counts behind it.

### 5. Recording a total-only token count — resolved

`input_tokens=0, output_tokens=total` is out: it lies about the split.

**The `extra` passthrough is also out, and the v2.75 contract is what
rules it out.** That archived proposal states plainly: "OSS writes nothing
into `extra`; it only *preserves* what another writer put there", and
"`extra` is opaque passthrough; it is never interpreted, scored, or
trusted by OSS surfaces." `extra` exists so a *foreign* writer
(Halyard-Enterprise's `cost_center=`, a newer Halyard, a third-party
emitter) can round-trip through this parser. An OSS collector writing
`grok_total_tokens=` there would break the first clause, and any report
surface reading it back would break the second.

**Decision: a first-class `total_tokens` field on `AiSession`,** added
through the `FieldSpec` registry. This is the format's normal growth
path — `api_seconds`/`tool_seconds` (v2.67), `client_surface`/
`commit_count` (v2.24), and the v2.32 interaction counts all arrived this
way. Non-negotiable 2 governs *publishing* a Halyard-owned spec, not
extending one.

Requirements that come with it:

- Row in the `Optional fields` table in `cli_spec.py` — that is the
  published spec surface, and it must not drift from the registry.
- `compare=False` semantics reviewed: the field must not disturb the
  content-addressed session id / hash used as the amendment join key.
- Backward compat: an older parser must ignore the token; a newer one
  must round-trip a row that lacks it.
- **`tokens_available` must not be reused for this.** Today it implies
  input *and* output are meaningful, and `_tool_buckets_for_report` sums
  `input + output + cache` when it is set — a total-only row would
  contribute 0 to that sum while claiming tokens are available. Give
  `total_tokens` its own presence semantics and teach the report bucket
  to prefer it when the split is absent.

## Capture path: hooks primary, importer as backfill

Unchanged and now better supported: Grok's native hook surface
(`~/.grok/hooks/*.json`, always trusted) is primary; the session-directory
importer backfills. Both key on the session id, so
`job_id = grok:{session_id}` deduplicates.

The external OTEL stream stays rejected — a third writer for the same
sessions, activated by a shell-global env var.

## P0 — contamination (unchanged, and already mitigated live)

Grok's `[compat.claude] hooks` and `[compat.cursor] hooks` default to
`true`, so it runs hooks out of `~/.claude/settings.json` and
`~/.cursor/hooks.json` — exactly where Halyard installs. On the reference
machine this was mitigated on 2026-08-09 by setting both to `false` in
`~/.grok/config.toml`; `grok inspect` then reports the Halyard entries as
`[disabled]` and both cells as `hooks OFF (config)`.

Still to ship:

- `doctor` detection of the hazard on machines that have not set it.
- Defence in depth: `claude_code.py` / `cursor.py` must refuse a
  foreign-harness payload rather than write a wrong-tool row.
- The `sessions` compat cell (`on` by default for cursor, claude, **and**
  codex) is a second borrowing vector; docs say it stays inert without a
  `resume-*` skill. Confirm, and decide whether `doctor` covers it.

## Collector shape

```python
_GROK_HOME    = Path(os.environ.get("GROK_HOME", Path.home() / ".grok"))
_SESSIONS_DIR = _GROK_HOME / "sessions"
_HOOKS_FILE   = _GROK_HOME / "hooks" / "halyard.json"
_IMPORTED_STATE = Path.home() / ".halyard" / "grok-imported"
```

- `tool = "grok"`, `job_id = grok:{session_id}`,
  `telemetry_source = "grok-session"`, `telemetry_trust = "observed"`
  (real model, real timestamps, real token total).
- Read `summary.json` fully; read `updates.jsonl` **only** for
  `_meta.totalTokens`. Never open `chat_history.jsonl`.
- Attribution from `info.cwd`; outcome from `git_remotes` / `head_branch`
  / `head_commit`.
- Growth-aware state from the first commit:
  `{session_id → high-water mark}` where the mark is `updated_at` or the
  `updates.jsonl` size. `/resume` and `--continue` grow a session in
  place; `--fork-session` creates a new id with a parent reference and so
  is a new row.

## Testing

- Golden-file: `summary.json` + `updates.jsonl` → expected `s` row.
- Token total read from `_meta`, cumulative max not sum.
- **Content safety:** `chat_history.jsonl` never opened; `params.update`
  never read.
- UTC→local conversion under a non-UTC `TZ`.
- Idempotence; growth supersedes; fork creates a distinct row.
- Hook + importer covering one session → one row.
- **Contamination:** a Grok-shaped payload delivered to `cc-hook` /
  Cursor commands writes no row.
- Attribution: Claude Code + Cursor + Grok fixtures → three rows, three
  tools, zero duplicates.
- Spend: `billing=credits` rows excluded from budget and invoice spend.
- `GROK_HOME` override respected.
- v5.23 duplicate canary quiet on a mixed-tool ledger.
- `perf_ceiling` for timing; no wall-clock literals.
