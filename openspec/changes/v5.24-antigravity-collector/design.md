# Design: v5.24 — Antigravity Collector

> **Phase 0 complete (2026-08-09).** A real 40-minute conversation was run
> and the on-disk format inspected. Three assumptions in the first draft
> were wrong; they are corrected below and the old text is not preserved.
> Remaining unknown: multi-workspace and multi-conversation behaviour
> (only one conversation exists so far).

## Phase 0 findings

### 1. `conversations/` is SQLite wrapping binary protobuf — not the target

`~/.gemini/antigravity/conversations/<cascade-id>.db` (+ `-wal`, `-shm`),
SQLite in WAL mode, 3.8 MB after one conversation. Schema:

| Table | Rows | Content |
|---|---|---|
| `trajectory_meta` | 1 | `trajectory_id`, `cascade_id`, `trajectory_type`, `source` — the only plain-text columns in the file |
| `steps` | 302 | all payloads `blob` |
| `gen_metadata` | 145 | `data` blob + `size` int |
| `executor_metadata` | 4 | blob |
| `parent_references`, `trajectory_metadata_blob`, `battle_mode_infos` | 1–4 | blob |

Every payload is **binary protobuf with no published schema** (wire tags
visible: `0x12`, `0x22` length-delimited, embedded UUID strings). A
`strings` sweep across all blob tables found **no** model name and no
token or usage field.

**Decision: do not parse this database.** It is the infeasibility case the
first draft anticipated. Byte-scraping an undocumented protobuf schema
that the vendor can rev silently is exactly the fragility this codebase
has been burned by elsewhere.

The `gen_metadata.size` column grows monotonically (1035, 1040, 1049 …)
and is the only numeric that could plausibly be a token counter. It is
*not* evidence of one — treat as a curiosity, not a data source.

### 2. There *is* a documented hook surface — the first draft said otherwise

`~/.gemini/antigravity/builtin/skills/agy-customizations/docs/hooks.md`
documents `hooks.json` in a customization root (e.g. `.agents/hooks.json`).

Events: `PreToolUse`, `PostToolUse`, `PreInvocation`, `PostInvocation`,
`Stop`. Handlers are merged and run sequentially per event.

Common payload on stdin:

```json
{
  "conversationId": "…",
  "workspacePaths": ["/path/to/workspace"],
  "transcriptPath": "…/transcript.jsonl",
  "artifactDirectoryPath": "…/artifacts",
  "modelName": "auto"
}
```

Documented limitations: `type: "command"` only (no HTTP), and **hooks run
synchronously and block the agent loop**. The second is a hard constraint
— a slow Halyard hook stalls the user's agent. Budget accordingly and
keep the Stop handler to an append.

### 3. The real capture target is a clean JSONL transcript

Actual path (**not** the docs' example path — see below):

```
~/.gemini/antigravity/brain/<conversation-id>/.system_generated/logs/transcript.jsonl
```

355 records / 384 KB for one 40-minute session. Every record carries
`step_index`, `source`, `type`, `status`, `created_at`; most also carry
`content`, `tool_calls`, `exit_code`, `thinking`, `truncated_fields`.

Observed enums:

- `type`: `USER_INPUT` (8), `PLANNER_RESPONSE` (174), `RUN_COMMAND` (71),
  `VIEW_FILE` (30), `CODE_ACTION` (24), `LIST_DIRECTORY` (23),
  `GENERIC` (10), `SYSTEM_MESSAGE` (5), `GREP_SEARCH` (4),
  `CHECKPOINT` (2), `CONVERSATION_HISTORY` (2), `ERROR_MESSAGE` (2)
- `source`: `MODEL` (336), `SYSTEM` (11), `USER_EXPLICIT` (8)

`created_at` is ISO-8601 **UTC with a `Z` suffix**
(`2026-08-09T18:58:04Z` → `19:38:32Z`). Halyard's ledger writes local
time — convert, and add a test with a non-UTC `TZ`. Getting this wrong
shifts every Antigravity session by the UTC offset.

**Path warning.** The docs state
`<workspace>/.gemini/antigravity/transcript.jsonl`, and further note the
directory name varies by product surface (`antigravity-cli/`,
`antigravity/`, `antigravity-ide/`). The observed location matches
neither — it is under `brain/<conversation-id>/.system_generated/logs/`.
**Never hardcode a transcript path**: take `transcriptPath` from the hook
payload, and for the importer, glob `brain/*/.system_generated/logs/`.

### 4. No tokens, no model, no cost — anywhere

Neither the transcript nor the protobuf blobs carry token counts, and the
hook payload's `modelName` is `"auto"`, matching the
`MODEL_PLACEHOLDER_M20` seen in `antigravity_state.pbtxt`.

Consequences, which are the crux of this change:

- `input_tok`, `output_tok`, `cost_usd` are **not derivable**. Rows carry
  zero tokens and zero cost, labelled `telemetry_trust=inferred` per
  non-negotiable 6 — never `observed`.
- What *is* derivable and genuinely useful: wall time (first → last
  `created_at`), `user_message_count` (`USER_INPUT`), tool-call counts by
  type, and error counts (`ERROR_MESSAGE` / `error`).
- Spend handling is settled — see § Spend quarantine.

## Observed environment (2026-08-09)

```
~/.gemini/antigravity/
├── conversations/<cascade-id>.db{,-wal,-shm}   # SQLite + protobuf — skip
├── brain/<conversation-id>/.system_generated/logs/transcript.jsonl  # target
├── antigravity_state.pbtxt      # last_selected_agent_model: MODEL_PLACEHOLDER_M20
├── installation_id
└── builtin/skills/agy-customizations/docs/hooks.md   # the hook contract
```

`trajectory_meta.cascade_id` equals the `.db` filename, and equals the
`brain/` directory name — so cascade id, conversation id, and file names
agree, giving a stable session key.

**Lineage note.** "cascade", "trajectory", `trajectory_id` are Windsurf
vocabulary, and `collectors/windsurf.py` already keys on `trajectory_id`
via `post_cascade_response`. Antigravity is Windsurf-derived. That makes
`windsurf.py` the right *structural* model — but it is hook-and-state-file
based and reads no SQLite, so there is no parsing code to reuse.

## Capture path: hooks primary, transcript importer as backfill

| Path | Verdict |
|---|---|
| `Stop` / `PostInvocation` hook | **Primary.** Documented, gives `conversationId` + `transcriptPath` directly, mirrors every other Halyard collector. |
| `transcript.jsonl` importer | **Secondary.** Backfills pre-install history; globs `brain/*/.system_generated/logs/`. |
| `conversations/*.db` | **Rejected.** Undocumented binary protobuf; see Phase 0 finding 1. |

Both key on `conversationId`, so `job_id = antigravity:{conversation_id}`
deduplicates across them.

## Spend quarantine (decided 2026-08-09)

Antigravity rows are captured for **time**, and excluded from **spend**
totals rather than counted as zero. A zero folded into a spend average
silently deflates it; an excluded row does not.

**The existing wire conventions already do most of this.** No new field
is needed:

- `usage.sum_spend(..., api_only=True)` — the default, used by both
  budget and invoicing — already skips any session where
  `billing != "api"` **or** `cost_usd <= 0`. An Antigravity row fails
  both tests, so it is excluded from every spend aggregate the moment it
  is written.
- `ai_log.py` already defines a `TOKENS_AVAILABLE` field type emitting
  `tokens_available=false`. That is precisely this case, and it is what
  distinguishes "no tokens were reported" from "zero tokens were used".
- `billing` uses `BILLING` encoding: `api` is omitted from the wire, any
  other value is written. Codex and Cursor already ship
  `billing=credits`.

So the collector emits:

```
tool=antigravity  input_tok=0  output_tok=0  cost_usd=0.0000
billing=credits  tokens_available=false  telemetry_trust=inferred
```

`billing=credits` is the honest label: Antigravity is subscription-borne,
not per-token API billing — the same reading Codex and Cursor already
use.

**What is *not* free, and is the actual work here:** visibility. Excluded
must not mean invisible, or the user cannot tell whether Antigravity time
was captured at all.

- Dashboard: surface Antigravity time in a **time-only** bucket, visually
  distinct from spend-bearing tools, so the hours are legible without
  implying a cost figure.
- `halyard report` / `usage`: where a per-tool spend column would render
  `$0.00`, render an explicit "n/a — not spend-tracked" instead. A dash
  reads as honest; a zero reads as free.
- `doctor`: when Antigravity rows exist, state that its time is captured
  but its spend is not tracked.

Regression risk to pin with tests: a spend-bearing tool must not
accidentally inherit the quarantine, and Antigravity time must still
reach invoices and timeclock reconciliation — quarantine applies to
spend, not to time.

## Collector shape

```python
_ANTIGRAVITY_DIR = Path.home() / ".gemini" / "antigravity"
_BRAIN_DIR       = _ANTIGRAVITY_DIR / "brain"
_TRANSCRIPT_GLOB = "*/.system_generated/logs/transcript.jsonl"
_HOOKS_FILE      = ".agents/hooks.json"          # customization root
_IMPORTED_STATE  = Path.home() / ".halyard" / "antigravity-imported"
```

- `tool = "antigravity"`, `telemetry_source = "antigravity-transcript"`,
  `telemetry_trust = "inferred"` (fixed — no observed-token path exists).
- Never read `content` or `thinking` fields (non-negotiable 5). The
  collector needs `created_at`, `type`, `source`, `status` only. Assert
  this in a test.
- Resolve the project from `workspacePaths[0]` on the hook path; on the
  importer path, from the transcript's workspace reference if present,
  else leave unattributed for `backfill` to resolve.

## Path ownership

Unchanged from the first draft and still the key structural risk:
`gemini_history.py` reads `~/.gemini/tmp` and `~/.gemini/history`; this
collector reads **only** `~/.gemini/antigravity/`. Add the explicit
exclusion and the two-way isolation test.

## State file: growth-aware from day one

As before (v5.2 / v5.21 / v5.22 all shipped id-set state and all needed a
growth fix): `antigravity-imported` stores
`{conversation_id → high-water mark}`. Here the mark is the transcript's
line count or last `step_index`, both monotonic in the observed data.
Antigravity resumes conversations in place, so growth is the normal case.

## Doctor integration

- App absent → `SKIPPED`.
- Present, no captured rows → `warning`, fix `halyard install-hook-antigravity`.
- Captured but newest `transcript.jsonl` mtime materially newer than the
  newest captured row → lagging warning.
- **New:** when Antigravity rows exist, note in the doctor detail that
  Antigravity contributes time but not spend, so budget figures
  under-count. Silence here would be the dishonest option.

Real command names in every `fix=` string.

## Testing

- Golden-file: sample `transcript.jsonl` → expected `s` row (zero tokens,
  zero cost, `telemetry_trust=inferred`).
- **Timezone:** UTC `created_at` under a non-UTC `TZ` → correct local
  start/end. Pins the off-by-offset bug.
- Content safety: `content` and `thinking` never read.
- Growth: resumed conversation → prior row superseded, not duplicated.
- Idempotence: import twice → one row.
- Isolation: Antigravity fixtures yield zero Gemini rows, and vice versa.
- Path resilience: transcript found via payload `transcriptPath` even
  when it does not match the documented layout.
- Doctor: absent / uncaptured / lagging / current, plus the
  spend-under-count note.
- v5.23 duplicate canary quiet on a mixed-tool ledger.
- `perf_ceiling` for timing assertions; no wall-clock literals.
- Hook handler completes fast enough not to stall the agent loop (hooks
  block synchronously) — assert via `perf_ceiling`, not a literal.
