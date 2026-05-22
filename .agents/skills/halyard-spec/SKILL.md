---
name: halyard-spec
description: Enforces the "Documentation-First" workflow for Halyard. Mandates reading and updating PRDs, ARDs, and OpenSpec changes before implementation.
---

# Halyard Spec-First Workflow

This skill codifies the mandatory documentation and planning workflow for the Halyard project.

## Core Mandates

You MUST follow the **Research -> Spec -> Implementation -> Validate** sequence for all non-trivial changes.

### 1. Research phase
- Always start by reading `openspec/project.md` to ensure alignment with the project mission and non-negotiables.
- Identify if the task relates to an existing "Active focus" version in the roadmap.

### 2. Spec-First Phase (Mandatory)
Before writing ANY code for a new feature or architectural change:
1. **Create/Update Proposal:** Write or update the `proposal.md` in `openspec/changes/<v-slug>/`. Explain the "why" and the high-level "what".
2. **Draft PRD/ARD:** For significant architectural shifts or new modules, create or update the relevant PRD (Product Requirements Document) or ARD (Architecture Recommendation Document) in `docs/`.
3. **Write Specs:** Define requirements in `openspec/changes/<v-slug>/specs/*.md` using the Gherkin-style `WHEN/THEN` scenarios.
4. **Detail Design:** Document the technical approach, trade-offs, and chosen stack in `design.md`.
5. **Prepare Tasks:** Create `tasks.md` as the implementation checklist.

### 3. Implementation Phase
- Only after the Spec phase is "Approved" (aligned with the user) should you begin coding.
- Follow the `tasks.md` checklist strictly.
- Adhere to the `modern-python` standards (uv, ruff, pytest, dependency groups).

### 4. Validation Phase
- Update `tasks.md` to mark items as complete.
- Ensure documentation parity: if implementation diverged from design, update the docs.
- All non-trivial changes MUST include tests that verify the specs defined in phase 2.

## File Locations

- **Project Context:** `openspec/project.md`
- **Active Specs:** `openspec/changes/v<version>-<slug>/`
- **Architecture Docs:** `docs/ARD-*.md`
- **Product Docs:** `docs/PRD-*.md`
- **System Integrity:** `docs/trust-model.md`

## Tool usage
- Use `grep_search` to find relevant previous specs for consistency.
- Use `read_file` on existing PRDs before proposing new ones to maintain architectural continuity.
