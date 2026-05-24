# Behavior Spec: Hub Architecture (v4.0)

## R1: Hub Ingestion
The Hub MUST accept AI sessions via a local OTLP/HTTP endpoint.

**Scenario: Tool emits telemetry to active Hub**
- GIVEN the Halyard Hub is running on `127.0.0.1:4318`
- WHEN a tool sends a GenAI OTLP span to the Hub
- THEN the Hub MUST validate the metadata against the `AiSession` schema
- AND the Hub MUST append the session to `ai-sessions.log` within 50ms
- AND the Hub MUST NOT block the tool's response.

## R2: Platform Portability
Halyard MUST support service management on macOS, Linux, and Windows.

**Scenario: Installing service on Linux**
- GIVEN Halyard is running on a Linux system with `systemd`
- WHEN the user runs `halyard service install`
- THEN Halyard MUST generate a `halyard.service` unit file
- AND Halyard MUST enable and start the service via `systemctl`.

## R3: Exclusive Writer / Contention
The Hub MUST eliminate file-locking contention.

**Scenario: Concurrent tool emissions**
- GIVEN two tools emit telemetry simultaneously to the Hub
- WHEN the Hub receives both requests
- THEN the Hub MUST queue the writes and append them sequentially to the log
- AND no `flock` errors should be visible to the tools.
