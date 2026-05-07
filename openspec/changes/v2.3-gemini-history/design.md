# Design: v2.3 — Gemini History Enrichment

## History file layout

```
~/.gemini/tmp/{project-slug}/chats/session-{ISO-timestamp}-{session-id-prefix}.json
~/.gemini/history/{project-slug}/.project_root   ← absolute path of the project dir
```

The `session-id-prefix` is the first 8 characters of the UUID `sessionId` field inside
the file. The project slug is derived by Gemini CLI from the working directory.

### Session JSON schema (relevant fields)

```json
{
  "sessionId": "c6b5c24b-501f-4b9a-9122-562aab0b7465",
  "projectHash": "bcf1...",
  "startTime": "2026-04-21T20:30:24.223Z",
  "lastUpdated": "2026-04-21T22:22:03.047Z",
  "messages": [
    {
      "id": "...",
      "timestamp": "2026-04-21T20:30:42.356Z",
      "type": "gemini",
      "content": "...",
      "tokens": {
        "input": 12827,
        "output": 44,
        "cached": 8130,
        "thoughts": 30,
        "tool": 0,
        "total": 12901
      },
      "model": "gemini-3-flash-preview",
      "toolCalls": [
        {
          "id": "...",
          "name": "run_shell_command",
          "status": "success"
        }
      ]
    }
  ]
}
```

Only messages with `"type": "gemini"` contain token data. User and info messages are
ignored.

---

## New module: `src/halyard/collectors/gemini_history.py`

Shared parsing logic used by both the hook enrichment and the importer.

```python
@dataclass
class GeminiModelStats:
    model: str
    requests: int
    input_tokens: int
    output_tokens: int
    cache_tokens: int
    thinking_tokens: int
    tool_calls: int
    tool_errors: int

@dataclass
class GeminiSessionSummary:
    session_id: str
    start: datetime
    end: datetime
    model_stats: list[GeminiModelStats]   # one entry per distinct model
    # Derived convenience fields
    dominant_model: str                    # model with most output tokens
    total_input: int                       # net input (excluding cache) across all models
    total_output: int
    total_cache: int
    total_tool_calls: int
    total_tool_errors: int
    cost_usd: float                        # sum of calculate_cost() per model

def parse_session_file(path: Path) -> GeminiSessionSummary | None:
    """Parse a Gemini CLI history JSON file. Returns None on any parse error."""

def find_session_file(session_id: str) -> Path | None:
    """Search ~/.gemini/tmp/*/chats/ for a file whose name contains the session_id prefix."""

def find_all_session_files() -> list[Path]:
    """Return all session JSON files across all project slugs."""

def project_dir_for_slug(slug: str) -> Path | None:
    """Read ~/.gemini/history/{slug}/.project_root. Returns None if absent."""
```

### Cost calculation

For each `GeminiModelStats` entry:
```python
cost += calculate_cost(
    model=stats.model,
    input_tokens=stats.input_tokens,   # already excludes cache
    output_tokens=stats.output_tokens,
    cache_read=stats.cache_tokens,
)
```

Thinking tokens (`tokens.thoughts`) are counted as additional input tokens for cost
purposes: `net_input = input_tokens - cache_tokens + thinking_tokens`. The Gemini CLI
shutdown summary does not include thinking tokens in cost; we err on the side of accuracy.

### Dominant model selection

```python
dominant = max(model_stats, key=lambda s: s.output_tokens)
```

---

## Changes to `src/halyard/collectors/gemini_cli.py`

### `handle_agent_stop()` enrichment

Current flow: uses accumulated state from `_read_state()`.

New flow:
1. Read accumulated state as before.
2. Call `find_session_file(state["session_id"])`.
3. If found: call `parse_session_file()`, use the returned `GeminiSessionSummary` for
   token counts, dominant model, cost, and tool call tags.
4. If not found: fall back to accumulated state (existing behaviour preserved).

```python
tags = [f"branch:{branch}"] if branch else []

summary = None
if session_id := state.get("session_id"):
    history_path = find_session_file(session_id)
    if history_path:
        summary = parse_session_file(history_path)

if summary:
    model = summary.dominant_model
    input_tokens = summary.total_input
    output_tokens = summary.total_output
    cache_tokens = summary.total_cache
    cost = summary.cost_usd
    if summary.total_tool_calls:
        tags.append(f"tools:{summary.total_tool_calls}")
    if summary.total_tool_errors:
        tags.append(f"tool_errors:{summary.total_tool_errors}")
else:
    # existing accumulated-state path
    ...
```

---

## `halyard import-gemini` CLI command

```
$ halyard import-gemini
Scanning ~/.gemini/tmp for sessions...
Found 23 sessions. 18 already imported. Importing 5 new sessions.
  2026-04-17 17:44  gemini-3-flash-preview  in=306k out=1.9k  $0.0423  orbit
  2026-04-21 20:30  gemini-3-flash-preview  in=223k out=989   $0.0311  orbit
  ...
5 sessions imported.
```

Flags:
- `--dry-run` — show what would be imported without writing
- `--all` — scan all projects (default: current project only)
- `--project PROJECT_DIR` — specify a project directory explicitly

### Deduplication

Uses `job_id=gemini:{session_id}` on the log line. Before importing any session, scan
the target log for existing lines with that `job_id`. Skip if found.

### Project attribution

For each session file, look up `project_dir_for_slug(slug)` from
`~/.gemini/history/{slug}/.project_root`. If the project dir contains a `halyard.toml`,
append to that project's `ai-sessions.log`. Otherwise fall back to hub.

---

## `ai-sessions.log` additions

No new fields. New data expressed through existing fields:

| Data | Field |
|------|-------|
| Canonical model | `model` |
| Dominant-model net input | `input_tokens` |
| Dominant-model output | `output_tokens` |
| Cache read | `cache_read` |
| Summed multi-model cost | `cost_usd` |
| Tool call count | `tags=tools:N` |
| Tool error count | `tags=tool_errors:N` |
| Session identity | `job_id=gemini:{session_id}` |

---

## Error handling

| Scenario | Behaviour |
|----------|-----------|
| History file not found at hook time | Fall back to accumulated state |
| History file malformed JSON | Fall back to accumulated state |
| No `.project_root` for a slug | Skip that project during import |
| Project dir has no `halyard.toml` | Fall back to hub |
| Session already imported | Skip (dedup by job_id) |
| History file for session_id matches multiple files | Use most recently modified |
