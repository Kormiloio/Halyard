# Behavior Spec: Polyglot Proof (v4.1)

## R1: Ingestion Schema Validation
The Hub MUST validate ingested sessions against a strict schema.

**Scenario: Tool emits malformed structured session**
- GIVEN the Hub is running
- WHEN a tool sends a POST to `/v1/ingest` with `fields` missing required fields (e.g., no `start`)
- THEN the Hub MUST return `400 Bad Request`
- AND the response body MUST be JSON with an `error` key
- AND the Hub MUST NOT append the session to the log.

**Scenario: Tool emits valid structured session**
- GIVEN the Hub is running
- WHEN a tool sends a POST to `/v1/ingest` with a valid `fields` object
- THEN the Hub MUST return `200 OK`
- AND the Hub MUST append exactly one session to the log.

**Scenario: Tool emits unknown structured field**
- GIVEN the Hub is running
- WHEN a tool sends a POST to `/v1/ingest` with `fields` containing an unknown key
- THEN the Hub MUST return `400 Bad Request`
- AND the Hub MUST NOT append the session to the log.

## R2: Public Spec Command
Halyard MUST provide a way to view the data format specification.

**Scenario: User requests data spec**
- WHEN the user runs `halyard spec`
- THEN Halyard MUST print a Markdown document describing the `s` and `a` line formats
- AND the output MUST include a table of all current optional field keys (derived from `_FIELDS`).

## R3: Reference Emission
A user MUST be able to emit telemetry using standard tools like `curl`.

**Scenario: Shell script emission**
- GIVEN the Hub is running
- WHEN the user runs `curl -X POST http://localhost:4318/v1/ingest -d '{"line": "s ..."}'`
- THEN the Hub MUST accept and log the session.

**Scenario: Reference script exists**
- WHEN a user reads `samples/emit-session.sh`
- THEN it MUST demonstrate a working `curl` payload for `/v1/ingest`
- AND it MUST avoid any Python dependency.

## Validation
- `tests/test_v41_polyglot.py::test_hub_ingest_accepts_structured_fields`
- `tests/test_v41_polyglot.py::test_hub_ingest_rejects_missing_required_structured_field`
- `tests/test_v41_polyglot.py::test_hub_ingest_rejects_unknown_structured_field`
- `tests/test_v41_polyglot.py::test_hub_ingest_rejects_invalid_raw_line`
- `tests/test_v41_polyglot.py::test_hub_ingest_still_accepts_raw_line`
- `tests/test_v41_polyglot.py::test_spec_command_includes_all_registered_optional_fields`
- `tests/test_v41_polyglot.py::test_reference_shell_emitter_exists_without_python_dependency`
