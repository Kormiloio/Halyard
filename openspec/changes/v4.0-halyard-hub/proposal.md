# OpenSpec Proposal: v4.0 Halyard Hub

## 1. Why
To scale Halyard to Linux/Windows and eliminate the "silent latency" introduced by file-locking in terminal hooks. We want to move from a library-based "Import to Write" model to a service-based "Polyglot Emission" model.

## 2. What
Implement the Halyard Hub — a local background daemon that handles all telemetry ingestion, log appends, and cache synchronization.

## 3. Non-Goals
- Cloud-hosted capture (remains local-only).
- Changing the `ai-sessions.log` format (stays plain-text).
- Shared multi-user databases (remains per-user).
