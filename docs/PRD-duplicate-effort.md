# PRD — Duplicate-Effort Detection (v5.0)

## 1. Executive Summary
As engineering teams adopt AI agents and tools at scale, "AI-Collision" — multiple tools or people working on the same branch or ticket simultaneously — becomes a real risk. This redundant effort wastes tokens and developer time. v5.0 introduces **Duplicate-Effort Detection** to identify these collisions using privacy-preserving metadata (branch, remote, and timing overlap) and surface them to the developer in real-time.

## 2. Problem Statement
- **Redundant Spend:** Two developers (or one developer with two tools) may be working on the same branch simultaneously, incurring double AI costs.
- **Merge Conflicts:** Simultaneous AI edits to the same branch increase the likelihood of complex merge conflicts.
- **Fragmented History:** AI sessions are currently "siloed" by tool; there is no cross-tool view of effort overlap.

## 3. Goals & Objectives
- **Early Warning:** Detect when a new AI session starts on a branch that already has an active or recent session.
- **Privacy First:** Use ONLY git metadata and timestamps to detect collisions. NO code or prompt inspection.
- **Real-Time Visibility:** Leverage the Halyard Hub to push collision alerts to the dashboard and CLI.

## 4. Key Features
- **Collision Engine:** Logic that identifies overlapping sessions based on:
  - `branch` name matching.
  - `remote` repository matching.
  - `timestamp` overlap (concurrent sessions).
- **Collision Alerts:**
  - **Dashboard:** A "Collision Alert" badge on active project cards.
  - **CLI:** A warning message when `halyard start` is called on a "busy" branch.
- **Historical Overlap Reporting:** A new analytical view in "The Bridge" showing total wasted effort due to collisions.

## 5. Constraints
- **Local-Only:** Detections are performed against the local SQLite cache and Hub state.
- **Metadata-Gated:** Detection fails gracefully if a collector does not provide `branch` or `remote` metadata.
