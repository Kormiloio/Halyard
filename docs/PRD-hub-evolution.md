# PRD — Hub Evolution (v4.1 – v4.3)

## 1. Executive Summary
The transition to the Halyard Hub (v4.0) created a central telemetry broker. This evolution sequence (v4.1 – v4.3) leverages that daemon to solve state fragmentation, improve real-time visibility, and formalize Halyard as a polyglot AI-tracking platform. By moving active state into memory and enabling push-based UI updates, we eliminate filesystem-polling latency and make the dashboard feel like a modern, "alive" command center.

## 2. Product Goals

### G1: Polyglot Ingestion (v4.1)
**Goal:** Enable any tool, written in any language, to record AI sessions with zero Python dependency.
**Success:** A published, stable log and API specification that community members can use to build custom emitters.

### G2: Unified Active State (v4.2)
**Goal:** Eliminate "State Fragmentation" where terminal hooks and IDEs desync on which project is active.
**Success:** The Hub acts as the single source of truth for "What am I working on?", reachable via a fast local HTTP query.

### G3: Instant Response (v4.3)
**Goal:** Remove the "10-second wait" for dashboard updates.
**Success:** Ingested sessions appear in the UI within 500ms of the hook firing, without requiring a full page refresh.

## 3. Key Features

### v4.1: The Polyglot Proof
- **Stable `/v1/ingest` API:** A versioned JSON schema for direct session emission.
- **Public Log Spec:** A human-readable Markdown specification of the `ai-sessions.log` format, derived from the declarative `_FIELDS` registry.
- **Two Emitter Shapes:** `/v1/ingest` accepts either the canonical raw `s ...`
  log line or a structured `fields` object with the seven required session
  fields and known optional metadata keys.
- **Implementation Status:** Complete in v4.1. The Hub validates both payload
  shapes, `halyard spec` prints the generated Markdown contract, and
  `samples/emit-session.sh` demonstrates curl-based emission without Python.

### v4.2: Hub-Managed Active State
- **State In-Memory:** The Hub holds the active project slug, timer start time, and auto-timer presence window.
- **State API:** `GET /v1/state` returns the current project. `POST /v1/state/timer` starts and stops the timer.
- **Zero-Polling hooks:** CLI hooks query the Hub instead of reading `~/.halyard/active`.
- **Implementation Status:** Complete in v4.2. `read_active_project()`,
  `read_active_timer()`, manual timer start/stop, and auto-timer presence all
  attempt Hub state first and retain file-based fallback when the Hub is down.

### v4.3: Real-Time Dashboard
- **SSE Stream:** The Hub provides a `/v1/events` stream for the dashboard.
- **UI Reactivity:** The Bridge dashboard listens for events and updates cards/tables dynamically when a new session is logged.
- **No Full Reload:** The dashboard patches stable DOM regions for session
  ingestion and timer events, preserving scroll position and browser state.
- **Implementation Status:** Complete in v4.3. The Hub exposes an SSE event
  fanout, emits session and timer events, and The Bridge patches dashboard
  fragments without calling `window.location.reload()`.

## 4. User Experience
- **Developer:** Runs a hook; the dashboard (visible on a side monitor) updates instantly with the new session cost and token count. No more manual refreshing.
- **Admin:** Can easily see which project is currently active across all terminal and IDE surfaces because they all agree on the Hub's state.

## 5. Security & Privacy
- **Local-Only:** All new APIs bind strictly to `127.0.0.1`.
- **Token Auth:** State-mutating endpoints (`/v1/state/timer`) require the existing `dashboard.token`.
- **Metadata-Only:** The ingestion API continues to strictly enforce metadata-only capture.
  v4.1 structured ingestion rejects unknown keys so prompt text, code, file
  contents, and other free-form payloads cannot become part of the public API by
  accident.
- **State Mutations:** v4.2 manual timer and auto-presence mutations require
  the dashboard token over loopback and leave direct file fallback available
  when the Hub is unreachable.
- **Realtime Reads:** v4.3 SSE is read-only and unauthenticated on loopback; it
  carries metadata-only event hints and never prompt, code, or transcript data.
