# Design: AI Session Log Schema (`ai-sessions.log`)

## The core decision

One append-only plain-text file. One line per session. Human-readable,
git-diffable, parseable by a shell one-liner. Consistent with Halyard's
existing `time.timeclock` ethos.

---

## Format

```
; Halyard AI session log — spec: https://halyard.dev/spec/ai-sessions/v1
; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd> [key=value ...]

s 2026-05-06T10:30:00 2026-05-06T11:15:00 claude-code claude-opus-4-7 45230 8920 2.3400 project=acme:auth-migration
s 2026-05-06T14:00:00 2026-05-06T14:22:00 claude-code claude-sonnet-4-6 12450 3210 0.4200 project=acme:auth-migration
s 2026-05-06T16:00:00 2026-05-06T16:05:00 openai-api gpt-4o 3200 800 0.0560 project=globex:reporting
```

### Record marker

Lines beginning with `s` are session records. Lines beginning with `;` are
comments and are ignored by parsers. Blank lines are ignored. Any other line
prefix is reserved for future record types.

### Positional fields (required, space-separated)

| Position | Field           | Format                        | Example                  |
|----------|-----------------|-------------------------------|--------------------------|
| 1        | `start`         | `YYYY-MM-DDTHH:MM:SS` local   | `2026-05-06T10:30:00`    |
| 2        | `end`           | `YYYY-MM-DDTHH:MM:SS` local   | `2026-05-06T11:15:00`    |
| 3        | `tool`          | slug (see registry below)     | `claude-code`            |
| 4        | `model`         | provider model ID             | `claude-opus-4-7`        |
| 5        | `input_tokens`  | integer                       | `45230`                  |
| 6        | `output_tokens` | integer                       | `8920`                   |
| 7        | `cost_usd`      | decimal, 4 places             | `2.3400`                 |

### Optional key=value pairs (any order, after positional fields)

Unknown keys MUST be silently ignored by parsers. This is the extensibility
contract: new keys added in future versions will not break old parsers.

| Key                | Type                           | Description                                                                 |
|--------------------|--------------------------------|-----------------------------------------------------------------------------|
| `project`          | `client:project` slug          | Attribution. Omit for unattributed work.                                    |
| `user`             | string, no spaces              | For enterprise multi-user. Omit for solo.                                   |
| `cache_read`       | integer                        | Anthropic prompt cache read tokens.                                         |
| `cache_write`      | integer                        | Anthropic prompt cache write tokens.                                        |
| `tokens_available` | `true` \| `false`              | Set `false` when the tool does not expose token counts (e.g. ChatGPT web). |
| `billing`          | `api` \| `seat` \| `credits`   | How the tool charges. Default `api`. See billing section below.             |
| `credits`          | decimal, 4 places              | Units consumed for credit-based tools (Antigravity, etc.).                  |
| `job_id`           | UUID or string, no spaces      | Links multiple session records belonging to one agentic job.                |
| `source`           | `hook` \| `proxy` \| `sdk` \| `manual` | How this record was captured. Used for deduplication.              |
| `tags`             | comma-separated strings        | Arbitrary labels: `tags=review,refactor`                                    |
| `note`             | string, underscores for spaces | Free-text: `note=initial_auth_spike`                                        |

### Cost field

Cost is **snapshotted at capture time** using the model's pricing at the
moment of the call. This is a deliberate design choice: model pricing changes
frequently. A log entry from 2026-05 must remain accurate in 2028 without
requiring a pricing-table lookup against a moving target.

Halyard ships a built-in pricing table (updated with each release). The
collector writes `cost_usd` at write time. If pricing is unknown for a model,
write `0.0000` and set `tokens_available=false` in the optional fields.

### Billing models

Not all tools charge per token. Three billing models are supported:

**`billing=api` (default)** — Per-token or per-call pricing. `input_tokens`,
`output_tokens`, and `cost_usd` are meaningful. This is Anthropic API, OpenAI
API, DeepSeek, Mistral, Grok, etc.

**`billing=credits`** — The tool charges in opaque credits (e.g. Antigravity
AI credits, Cursor credits when using their hosted quota). Write
`input_tokens=0 output_tokens=0` and use `credits=<amount>` for the units
consumed. `cost_usd` should reflect the USD equivalent of credits consumed if
known (e.g. Antigravity: 2500 credits = $25, so 100 credits = $1.0000).

**`billing=seat`** — Flat monthly seat license (e.g. GitHub Copilot). There
is no meaningful per-session token count. Write
`input_tokens=0 output_tokens=0 cost_usd=0.0000 billing=seat`. Cost
attribution for seat tools happens in the analytics layer (monthly fee ÷
sessions in the billing period), not at capture time.

---

## Tool registry

Standard tool slugs. Collectors MUST use these identifiers when applicable.
New tools SHOULD follow the pattern `<vendor>-<product>` or `<vendor>-api`.

### AI coding IDEs and assistants

| Slug          | Description                                         | Billing default |
|---------------|-----------------------------------------------------|-----------------|
| `claude-code` | Anthropic Claude Code CLI                           | `api`           |
| `antigravity` | Google Antigravity IDE (multi-model: Gemini, Claude, GPT) | `credits` |
| `cursor`      | Cursor IDE (multi-model)                            | `credits`       |
| `windsurf`    | Codeium Windsurf IDE                                | `credits`       |
| `copilot`     | GitHub Copilot                                      | `seat`          |
| `amazon-q`    | Amazon Q Developer (formerly CodeWhisperer)         | `seat`          |
| `aider`       | Aider open-source CLI                               | `api`           |
| `continue`    | Continue.dev IDE extension                          | `api`           |
| `cody`        | Sourcegraph Cody                                    | `seat`          |

### AI APIs (direct)

| Slug            | Description                              | Billing default |
|-----------------|------------------------------------------|-----------------|
| `claude-api`    | Anthropic API (SDK or proxy)             | `api`           |
| `openai-api`    | OpenAI API (SDK or proxy)                | `api`           |
| `gemini-api`    | Google Gemini API                        | `api`           |
| `deepseek-api`  | DeepSeek API                             | `api`           |
| `grok-api`      | xAI Grok API                             | `api`           |
| `mistral-api`   | Mistral API                              | `api`           |
| `together-api`  | Together AI (hosts open-source models)   | `api`           |
| `groq-api`      | Groq (fast inference API)                | `api`           |
| `openrouter`    | OpenRouter (multi-provider router)       | `api`           |
| `cohere-api`    | Cohere API                               | `api`           |

### AI agents and platforms

| Slug        | Description                                              | Billing default |
|-------------|----------------------------------------------------------|-----------------|
| `factory`   | Factory.ai Droids (agent-native dev platform)            | `credits`       |
| `devin`     | Cognition Devin (autonomous software engineer)           | `credits`       |
| `openclaw`  | OpenClaw (open-source autonomous agent, multi-model)     | `api`           |

### AI chat interfaces (web — limited token visibility)

| Slug           | Description                          | Billing default |
|----------------|--------------------------------------|-----------------|
| `chatgpt-web`  | ChatGPT web interface                | `seat`          |
| `claude-web`   | Claude.ai web interface              | `seat`          |
| `perplexity`   | Perplexity AI                        | `seat`          |
| `gemini-web`   | Gemini web interface                 | `seat`          |

### Local and self-hosted models (zero API cost)

| Slug        | Description                          | Billing default |
|-------------|--------------------------------------|-----------------|
| `ollama`    | Ollama local model runner            | `api`           |
| `lm-studio` | LM Studio local model runner         | `api`           |

### Halyard infrastructure

| Slug              | Description                                       |
|-------------------|---------------------------------------------------|
| `halyard-proxy`   | Halyard API proxy (tool not identified by proxy)  |
| `unknown`         | Fallback — tool could not be identified           |

---

## Why this format and not alternatives

### Why not JSONL?

JSONL is the obvious choice for structured append-only logs. We rejected it
because:

1. `grep`, `awk`, and `cut` work naturally on the positional format without
   needing `jq`.
2. The file reads naturally without tooling — open it in any editor, you
   understand it immediately.
3. Consistency with `time.timeclock` matters to the audience. A user who
   understands one file understands the other.

JSONL remains the right choice for the cloud sync wire format. The collector
writes positional plain text locally; the sync layer serializes to JSONL for
transport. These are different concerns.

### Why not extend `time.timeclock`?

hledger timeclock has a fixed schema: `i`/`o` lines with a timestamp and
account name. Adding token counts would require either comments (fragile,
not machine-readable) or a Halyard-specific extension that breaks
compatibility with the broader hledger ecosystem.

`time.timeclock` tracks human time. `ai-sessions.log` tracks AI usage. They
are related but distinct. Both belong in the project directory. `halyard
report` joins them.

### Why not SQLite?

See non-negotiable #2 in `openspec/project.md`. Plain text is the contract.

---

## Deduplication: tool-wraps-tool

Some tools route through other tools. OpenClaw calls `claude-api` or
`openai-api` under the hood. If both the OpenClaw collector and the Halyard
API proxy are active simultaneously, two records are written for the same
tokens — one attributed to `openclaw`, one to `claude-api`.

Deduplication rules for the analytics layer:

1. Two records within a 30-second window with matching `input_tokens`,
   `output_tokens`, and `model` are candidates for deduplication.
2. Prefer the record with `source=hook` over `source=proxy`.
3. If both are `source=proxy`, prefer the record whose `tool` is more
   specific (e.g. `openclaw` over `halyard-proxy`).
4. The discarded record is not deleted from the log — it is flagged
   `deduplicated=true` in the analytics layer only. The raw file is
   append-only and never modified.

Collectors SHOULD set `source=` to enable accurate deduplication.

## Long-running agentic jobs

Tools like Factory Droids and Devin run for hours and generate many API
calls. The Halyard proxy writes one `s` record per idle-timeout window
(default 5 minutes). To link these into a logical job, collectors SHOULD
generate a `job_id` at job start (UUID or human-readable slug) and include
it in every `s` record for that job.

```
s 2026-05-06T09:00:00 2026-05-06T09:05:00 factory claude-opus-4-7 22400 4100 1.1200 project=acme:auth-migration job_id=droid-refactor-auth-001 source=proxy
s 2026-05-06T09:05:30 2026-05-06T09:10:00 factory claude-haiku-4-5 8200 1800 0.0420 project=acme:auth-migration job_id=droid-refactor-auth-001 source=proxy
```

`halyard report` can then aggregate by `job_id` to show total cost and
duration for the logical job alongside the individual session breakdown.

## Multi-session and multi-model considerations

### Sub-minute sessions

Claude Code sessions can be very short (a single prompt). Sessions under 60
seconds are valid and MUST be recorded. `start` and `end` may have the same
value if the session duration rounds to zero seconds.

### Sessions crossing midnight

`start` and `end` may be on different calendar dates. Parsers MUST handle
this. Duration is always `end - start`.

### Multiple models in one session (future)

Some tools use different models within a single session (e.g. a router that
uses Haiku for classification and Opus for generation). v1 records the
**primary model** — the one with the highest token count. Future versions may
introduce an `m` (model-segment) sub-record. Parsers that ignore unknown
record types will handle this gracefully.

---

## Parser contract

A compliant parser MUST:

1. Ignore lines that do not start with a known record marker (`s`, future
   markers).
2. Ignore lines starting with `;` or that are blank.
3. Silently ignore unknown `key=value` pairs in optional fields.
4. Not fail on a `cost_usd` of `0.0000`.
5. Not assume `project=` is present — unattributed sessions are valid.

A compliant writer MUST:

1. Append to the file, never overwrite.
2. Write `cost_usd` as a decimal with exactly 4 places.
3. Write timestamps in `YYYY-MM-DDTHH:MM:SS` local time, no timezone suffix.
4. Use only registered tool slugs where applicable, `unknown` otherwise.

---

## File header

Every `ai-sessions.log` file MUST begin with these two comment lines:

```
; Halyard AI session log — spec: https://halyard.dev/spec/ai-sessions/v1
; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd> [key=value ...]
```

The spec URL is the stable reference for this format. When the schema
version increments, the URL changes and old files remain valid under their
original spec.

---

## Example: a full day's log

```
; Halyard AI session log — spec: https://halyard.dev/spec/ai-sessions/v1
; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd> [key=value ...]

; --- 2026-05-06 ---
s 2026-05-06T09:15:00 2026-05-06T09:47:00 claude-code claude-opus-4-7 38420 7210 1.9800 project=acme:auth-migration
s 2026-05-06T10:30:00 2026-05-06T11:15:00 claude-code claude-opus-4-7 45230 8920 2.3400 project=acme:auth-migration cache_read=22000
s 2026-05-06T11:20:00 2026-05-06T11:22:00 claude-code claude-sonnet-4-6 4100 920 0.0610 project=acme:auth-migration note=quick_clarification
s 2026-05-06T14:00:00 2026-05-06T14:22:00 claude-api claude-sonnet-4-6 12450 3210 0.4200 project=globex:reporting tags=prototype
s 2026-05-06T16:00:00 2026-05-06T16:05:00 openai-api gpt-4o 3200 800 0.0560 project=globex:reporting note=competitor_comparison
```

---

## What `halyard init` will write

```
; Halyard AI session log — spec: https://halyard.dev/spec/ai-sessions/v1
; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd> [key=value ...]
```

Two lines. Nothing else. The file is valid and empty of records.

---

## Open questions (to be resolved in specs/)

1. **Timezone handling for enterprise.** Multi-user organizations may need
   UTC timestamps for consistent aggregation across timezones. Proposal:
   add optional `tz=UTC` key in v1, make UTC the default in the enterprise
   cloud sync config.

2. **Pricing table format and update cadence.** The built-in pricing table
   needs a spec. Proposal: a TOML file shipped with Halyard, updated on
   release, with a `halyard update-pricing` command for out-of-band updates.
   Local models (`ollama`, `lm-studio`) always have `cost_usd=0.0000` and
   are excluded from the pricing table.

3. **Session boundary for the API proxy.** The proxy captures individual API
   calls. How are these aggregated into session records? Proposal: a
   configurable idle timeout (default 5 minutes) — calls within the window
   are merged into one `s` record.

4. **Seat-licensed cost attribution.** For `billing=seat` tools (Copilot,
   Amazon Q, Claude.ai web), per-session cost is meaningless at capture time.
   Proposal: `halyard report` accepts a `--seat-costs` config that maps
   `tool=monthly_usd` and divides by session count in the billing period to
   produce a blended per-session cost for reporting purposes only.

5. **Credit exchange rates.** Antigravity and similar tools price in credits
   that may change over time. Proposal: a `credits_pricing.toml` alongside
   `pricing.toml` that maps `tool → (credits_per_usd, as_of_date)`, with
   the same `halyard update-pricing` command keeping it current.
