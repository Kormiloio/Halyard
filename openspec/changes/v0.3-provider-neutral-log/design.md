# Design: v0.3 — Provider-Neutral `halyard log`

## Architecture

`halyard log` keeps the local data layer as the source of truth and treats
model providers as interchangeable reasoning engines. The deterministic `local`
provider remains available with no network or API key. Model-backed providers
call the same local tools and return the same `LogQueryResponse` shape.

## Tool Schema Sharing

`src/halyard/log_agent.py` owns the shared `_TOOLS` list. The Anthropic provider
passes those tool definitions directly. The OpenAI-compatible provider adapts
the same entries through `_tools_for_openai()`, wrapping each schema as:

```python
{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
```

This keeps tool names, descriptions, and input schemas in one place while
allowing each SDK to receive its expected wire format.

## Provider Dispatch

`run_log_query()` accepts `agent`, `model`, and `base_url` overrides. If `agent`
is omitted, it loads `~/.halyard/config.toml` and uses `log.default_agent`.
Provider-specific defaults are resolved at dispatch time:

- `local`: deterministic local summary, no model or base URL.
- `claude`: Anthropic SDK using `model` or `log.claude_model`.
- `openai`: OpenAI-compatible SDK using `model` or `log.openai_model`, plus
  `base_url` or `log.openai_base_url`.

The CLI validates user-facing provider names before dispatch so mistakes fail
with a concise error.

## Configuration

`src/halyard/log_config.py` loads personal defaults from
`~/.halyard/config.toml`:

```toml
[log]
default_agent = "openai"
openai_base_url = "http://localhost:11434/v1"
openai_model = "llama3.3"
claude_model = "claude-3-5-sonnet-20241022"
```

Missing files and missing keys use built-in defaults. Unknown
`default_agent` values warn and fall back to `local`. CLI flags override config
values.

## OpenAI-Compatible Provider

The provider imports `openai` lazily with `importlib.import_module()` so the base
installation does not require the optional dependency. It requires
`OPENAI_API_KEY` only when the base URL is OpenAI's hosted API. Local or custom
OpenAI-compatible endpoints may run with a placeholder key because servers such
as Ollama ignore it.

The OpenAI loop mirrors the Claude loop:

1. Send system and user messages with the shared tools.
2. Execute requested tool calls locally through `_execute_tool()`.
3. Append tool results to the conversation.
4. Stop after a final model message or fail after three turns.

If the endpoint rejects tool use, Halyard raises `LogAgentError` with guidance
to choose another model or use `--agent local`.
