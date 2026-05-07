# Proposal: v0.3 — Provider-Neutral `halyard log`

## Why this change

`halyard log --agent claude` works well, but it hardcodes Anthropic as the only
model-backed reasoning provider. This creates vendor lock-in in a product whose
core ethos is local-first and open.

The feedback from three independent AI tool evaluations converged on the same
point: since Halyard queries only local metadata (no prompt content, no code),
users should be able to run the agent against any OpenAI-compatible endpoint —
including a local Ollama instance — at zero cost, with full privacy.

This is especially relevant for the local-first user who doesn't have or want an
Anthropic API key. The `local` provider (deterministic string-matching) handles
simple queries, but more complex questions ("what did I spend on auth-migration
vs feature-flags, broken down by model?") need a reasoning layer. A local LLM
via Ollama gives those users that reasoning without any cloud dependency.

## What this change does

### Provider abstraction

`log_agent.py` currently has two providers: `local` (deterministic) and `claude`
(Anthropic SDK). This change adds a third and formalizes the interface:

```
LogAgent = Literal["local", "claude", "openai"]
```

`openai` uses the `openai` Python SDK against any OpenAI-compatible base URL:
- OpenAI's own API (`api.openai.com`) — the default
- Local Ollama (`http://localhost:11434/v1`) via `--base-url`
- Any other compatible endpoint (LM Studio, vLLM, etc.)

The same tool schemas (`read_sessions`, `summarize_by_project`, etc.) work
across all model-backed providers because they follow the OpenAI function-calling
format, which Anthropic also supports via its API.

### New CLI flags

```bash
halyard log --agent openai "what did I spend this month"
halyard log --agent openai --model llama3.3 --base-url http://localhost:11434/v1 "..."
halyard log --agent claude "..."  # unchanged
halyard log "..."                  # local provider, unchanged
```

### Configuration: `~/.halyard/config.toml`

Rather than passing `--agent` and `--base-url` every time, users can set
defaults in `~/.halyard/config.toml`:

```toml
[log]
default_agent = "openai"
openai_base_url = "http://localhost:11434/v1"
openai_model = "llama3.3"
```

CLI flags always override config file values.

### Dependencies

`openai` is an optional extra: `pip install halyard[openai]`. The base install
does not change. The import guard follows the same pattern as the TUI:

```bash
pip install halyard[openai]   # adds openai SDK
pip install halyard[tui]      # adds Textual
pip install halyard[all]      # adds both
```

## What this change does NOT do

- No support for providers that don't implement OpenAI-compatible function
  calling (e.g., raw HuggingFace Inference API). If a model doesn't support
  tool use, the query falls back to the `local` provider with a warning.
- No streaming output. Single-turn response, same as the Claude provider.
- No automatic model selection. The user chooses the model; Halyard doesn't
  try to pick the "best" one for a query.
- No credential storage. API keys stay in environment variables
  (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) or in the shell profile. Halyard
  never writes API keys to disk.

## Key decisions

**Why OpenAI-compatible rather than a multi-provider abstraction (LiteLLM)?**

LiteLLM is a heavyweight dependency (50+ transitive packages) that adds
significant install size. The OpenAI SDK is already the de-facto standard for
this interface and covers the actual use cases:
- OpenAI models → OpenAI SDK against `api.openai.com`
- Local models → OpenAI SDK against Ollama/LM Studio/vLLM base URL
- Anthropic models → Anthropic SDK (already shipped in v0.2)

For a tool that values lean installs, adding LiteLLM to get one extra provider
interface is not the right trade.

**Why `~/.halyard/config.toml` and not project `halyard.toml`?**

API keys and model preferences are personal, not project-specific. They should
not be committed to a project repository. `~/.halyard/config.toml` is personal
state (like `~/.halyard/budgets.toml`) and is never committed.

## Success criteria

- `halyard log --agent openai "summarize this month"` works with `OPENAI_API_KEY` set.
- `halyard log --agent openai --base-url http://localhost:11434/v1 --model llama3.3 "..."` 
  works against a local Ollama instance with no API key required.
- `~/.halyard/config.toml` defaults are respected; CLI flags override them.
- Running with `--agent openai` without the `openai` package installed prints
  a clear install instruction and exits 1.
- All three providers (`local`, `claude`, `openai`) share the same tool schema
  definitions — no duplication.
- The provider selection and config loading are covered by unit tests.
