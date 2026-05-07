# Spec: v0.3 — Provider-Neutral `halyard log`

## Provider selection

### WHEN the user runs `halyard log "query"` with no `--agent` flag
AND `~/.halyard/config.toml` does not set `log.default_agent`
THEN the `local` deterministic provider is used. No API key required.

### WHEN the user runs `halyard log --agent claude "query"`
THEN the Anthropic SDK provider is used (v0.2 behaviour, unchanged).

### WHEN the user runs `halyard log --agent openai "query"`
THEN the OpenAI-compatible provider is used against the default base URL
(`https://api.openai.com/v1`) with `OPENAI_API_KEY`.

### WHEN the user runs `halyard log --agent openai --base-url http://localhost:11434/v1 "query"`
THEN the OpenAI-compatible provider is used against the specified local endpoint.
No `OPENAI_API_KEY` is required when `--base-url` points to a local server.

### WHEN `~/.halyard/config.toml` has `[log] default_agent = "openai"` and the user
runs `halyard log "query"` with no `--agent` flag
THEN the `openai` provider is used as if `--agent openai` was passed.
CLI flags override config file values.

---

## OpenAI-compatible provider

### WHEN `--agent openai` is used and the `openai` package is not installed
THEN the command prints:
`The openai package is required for --agent openai. Install it with:
  pip install halyard[openai]`
and exits with code 1.

### WHEN `--agent openai` is used against the default base URL and `OPENAI_API_KEY` is not set
THEN the command prints:
`OPENAI_API_KEY not set. Set it or use --base-url to point to a local server.`
and exits with code 1.

### WHEN `--agent openai` is used with `--base-url` pointing to a local server
AND `OPENAI_API_KEY` is not set
THEN the command proceeds without an API key (local servers typically don't require one).

### WHEN the OpenAI-compatible provider makes a tool call
THEN it uses the same tool schemas (`read_sessions`, `summarize_by_project`, etc.)
as the Claude provider. No duplication of schema definitions.

### WHEN the model at the specified endpoint does not support function calling
THEN the command prints:
`The model 'X' does not support tool use. Try a different model or use --agent local.`
and exits with code 1.

### WHEN the OpenAI-compatible provider returns a valid structured response
THEN it is normalised into `LogQueryResponse` using the same post-processing
as the Claude provider. `response.agent` is set to `"openai"`.

---

## `~/.halyard/config.toml`

### WHEN `~/.halyard/config.toml` does not exist
THEN all config values use their defaults (same as current behaviour).

### WHEN `~/.halyard/config.toml` has `[log] default_agent = "claude"`
THEN `halyard log "query"` uses the Claude provider by default.

### WHEN `~/.halyard/config.toml` has `[log] openai_base_url = "http://localhost:11434/v1"`
AND the user runs `halyard log --agent openai "query"` with no `--base-url` flag
THEN the configured base URL is used.

### WHEN `~/.halyard/config.toml` has a key with an invalid value (e.g., unknown agent name)
THEN the command prints a warning: `Warning: unknown log.default_agent 'xyz' in config — using local.`
and continues with the `local` provider.

---

## CLI flags

| Flag | Description |
|------|-------------|
| `--agent <local\|claude\|openai>` | Provider to use (overrides config default) |
| `--model <id>` | Model identifier (provider-specific; overrides config default) |
| `--base-url <url>` | Base URL for OpenAI-compatible endpoint (default: OpenAI API) |

All existing `halyard log` flags (`--json`, `--period`, `--tool`, `--project`,
`--model-filter`, `--branch`) are unchanged.
