# OpenSpec Proposal: v4.1 Polyglot Proof & Public Spec

## 1. Why
Now that the Hub is built, we need to prove that it can actually accept telemetry from tools not written in Python. This version stabilizes the ingestion API and publishes the internal log format as a public specification, inviting community integration.

## 2. What
- **Stabilize `/v1/ingest`:** Define and validate the JSON schema for the ingestion endpoint.
- **`halyard spec` command:** A new CLI command that prints the public Markdown specification of the `ai-sessions.log` format.
- **Reference Emitter:** A tiny shell script emitter (`halyard-emit.sh`) demonstrating how to send telemetry to the Hub using `curl`.

## 3. Implementation High-Level
- Update `HubServer` to validate incoming JSON against a Pydantic model.
- Add a script to `assets/` or `samples/` for reference.
- Add a new CLI command to `cli_config` or a new `cli_spec`.
