# Behavior Spec: Real-Time Dashboard (v4.3)

## R1: Event Stream
The Hub MUST provide a real-time event stream.

**Scenario: Listening for events**
- GIVEN the Hub is running
- WHEN a client connects to `GET /v1/events`
- THEN the Hub MUST keep the connection open
- AND the Hub MUST send keep-alive comments while the connection is open.

## R2: Session Ingestion Event
The Hub MUST notify listeners when a new session is recorded.

**Scenario: Real-time update**
- GIVEN a dashboard is connected to the event stream
- WHEN a new AI session is ingested via `/v1/ingest`
- THEN the Hub MUST emit a `session_ingested` event to all stream listeners
- AND the dashboard MUST patch the ledger table without calling
  `window.location.reload()`.

## R3: Timer Update Event
The Hub MUST notify listeners when active timer state changes.

**Scenario: Real-time timer card update**
- GIVEN a dashboard is connected to the event stream
- WHEN a timer starts or stops through the Hub
- THEN the Hub MUST emit a `timer_updated` event
- AND the dashboard MUST patch the active timer card without a full page reload.

## R4: Graceful Degradation
The dashboard MUST remain functional without the event stream.

**Scenario: Hub is down**
- GIVEN the Hub is NOT running
- WHEN the dashboard is opened
- THEN the dashboard MUST fallback to its standard static rendering
- AND no intrusive error messages should be shown to the user.

## Validation
- `tests/test_v43_realtime_dashboard.py::test_dashboard_uses_fragment_patching_not_page_reload`
- `tests/test_v43_realtime_dashboard.py::test_event_stream_delivers_emitted_event`
- `tests/test_v43_realtime_dashboard.py::test_timer_mutation_emits_timer_updated`
- Related regression gate: `tests/test_v42_hub_state.py`,
  `tests/test_v41_polyglot.py`, `tests/test_v4_hub_server.py`, and
  `tests/test_dashboard.py`.
