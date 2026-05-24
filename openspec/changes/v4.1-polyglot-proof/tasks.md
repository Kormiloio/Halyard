# Tasks: v4.1 Polyglot Proof

## Phase 1: API Stabilization
- [x] 1.1 Create `IngestPayload` Pydantic model in `hub_server.py`.
- [x] 1.2 Update `_handle_ingest` to use Pydantic validation.
- [x] 1.3 Add tests for schema validation (positive and negative cases).

## Phase 2: Public Spec
- [x] 2.1 Implement `halyard spec` CLI command.
- [x] 2.2 Create the Markdown generator that iterates over `_FIELDS`.
- [x] 2.3 Verify `halyard spec` output matches the latest field registry.

## Phase 3: Reference
- [x] 3.1 Create `samples/emit-session.sh`.
- [x] 3.2 Add a "Polyglot Ingestion" section to `README.md`.

## Phase 4: Post-review fixes
- [x] 4.1 Security: `/v1/ingest` and `/v1/traces` had no auth while the timer/presence
      endpoints required a token, letting any local process (or a browser via DNS-rebinding
      / CSRF) inject fabricated billing rows. Added a loopback `Host`-header check on both
      ingest endpoints (no token required, so external OTel collectors / polyglot emitters
      keep working). Mirrors the dashboard's Host allowlist.
