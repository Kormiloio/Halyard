# PRD — Halyard Hub (v4.0)

## 1. Executive Summary
Halyard's current architecture requires every tool (VS Code, CLI) to be a direct writer to the local filesystem. This creates performance bottlenecks, cross-platform friction, and deployment complexity. Halyard Hub (v4.0) transitions to a Daemon-Broker model where tools "emit" telemetry to a local background service (The Hub). This removes the need for file-locking in the tool execution path and unblocks non-macOS platforms.

## 2. Target Audience
- **The Solo Developer:** Who wants zero-latency AI capture.
- **The Multi-Platform User:** Who needs Halyard on Linux (systemd) or Windows (services).
- **The Polyglot Tool Builder:** Who wants to add Halyard support to a tool using any language (via local OTLP/HTTP).

## 3. Goals & Objectives
- **Zero-Latency Capture:** Move I/O operations (file appends, cache updates) out of the tool's execution path.
- **Polyglot Emission:** Enable telemetry ingestion via a stable local HTTP/OTLP endpoint.
- **Cross-Platform Parity:** Abstract service management away from macOS-only `launchd`.
- **Durable Identity:** Maintain the "Plain Text Source of Truth" while improving accessibility.

## 4. Key Features
- **The Hub Daemon:** A lightweight, persistent background process.
- **OTLP Ingestion:** Support for OpenTelemetry GenAI Semantic Conventions via local `127.0.0.1:4318`.
- **Platform-Agnostic Services:** Built-in managers for `systemd`, `WinService`, and `launchd`.
- **Background Cache Sync:** The Hub manages the SQLite read-model asynchronously.

## 5. Constraints & Non-Negotiables
- **Local-Only:** The Hub MUST only bind to localhost.
- **Plain-Text First:** All ingested sessions MUST land in the standard `ai-sessions.log`.
- **Privacy First:** The Hub MUST NOT capture prompts or source code; it only accepts metadata spans.
