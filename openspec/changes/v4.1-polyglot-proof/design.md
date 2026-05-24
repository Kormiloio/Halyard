# Design Doc: v4.1 Polyglot Proof

## 1. Schema Validation
We will use a Pydantic model (`IngestPayload`) to define the structure of the `/v1/ingest` endpoint.
- Support exactly one of:
  - `{"line": "s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd> [key=value ...]"}`
  - `{"fields": {"start": "...", "end": "...", "tool": "...", "model": "...", "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.001, "...optional registry keys...": "..."}}`
- Structured `fields` MUST contain the seven required session fields and MUST
  reject unknown keys. Optional keys are derived from `ai_log._FIELDS` to avoid a
  second schema registry.
- Error messages will be returned as JSON: `{"error": "..."}` with HTTP 400 for
  malformed JSON, missing required fields, invalid field types, invalid session
  line syntax, and unknown structured keys.
- A rejected payload MUST NOT append anything to `ai-sessions.log`.

Implementation note: `IngestPayload` now lives in `hub_server.py`; raw lines are
parsed through the canonical session-line parser, while structured fields are
converted to `AiSession` after required-field, unknown-key, and type validation.

## 2. Dynamic Spec Generation
The `halyard spec` command will not be a static file. It will iterate over `ai_log._FIELDS` to generate the "Optional Fields" section of the Markdown output. This ensures the spec is always in sync with the code.
- The command prints Markdown to stdout and exits without requiring a Halyard
  project directory.
- The generated spec documents both `s` session records and `a` amendment records.
- Tests assert that every key in `_FIELDS` appears in the generated optional
  fields table.

Implementation note: `cli_spec.generate_ai_sessions_spec()` owns the Markdown
generator and is registered as top-level `halyard spec`.

## 3. Sample Emitter
Create `samples/emit-session.sh` as a documented example for the README and the public spec.
- The sample uses only POSIX shell, `date`, and `curl`.
- The sample emits the raw `line` shape because it is the lowest common
  denominator for non-Python tools.

Implementation note: `samples/emit-session.sh` is executable and covered by the
v4.1 reference-emitter test.
