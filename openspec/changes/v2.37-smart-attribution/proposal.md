# v2.37 — Smart Attribution

## Problem

Project attribution relies on git remote URL matching (`repos.toml`) or an
active timer. This breaks in three common scenarios:

1. **Monorepos** — one remote URL, many sub-projects. Fleet (10 apps in one
   repo) gets one auto-slug for everything.
2. **Non-git directories** — no remote, no attribution signal. Sessions fall
   through to `None` and accumulate silently in the unattributed log.
3. **Zero-config users** — a fresh install attributes everything through the git
   wildcard in `repos.toml`. VCTI, TechtonicShift, KormiloAcquisitions, Halyard,
   Fleet — all land in one bucket like `kormilo:general`.

When unattributed sessions do accumulate, the previous fix prompt
(`halyard assign-unattributed`) required manual interactive triage of every
session. There was no way to see *which repos* generated the unattributed
sessions without reading the log.

## Goals

- Any directory with a `halyard.toml` is automatically attributed to the right
  project slug, regardless of git remote or directory layout.
- A single command (`halyard adopt`) bridges the gap from auto-slug to named
  project.
- Unattributed sessions surface as actionable, grouped by repo — not a raw count.
- Privacy-first: non-git directories stay anonymous. No local file paths stored.

## Non-goals

- Auto-creating `halyard.toml` in every visited directory. Devs control what
  gets tracked.
- Directory-name auto-slugs (`dir/<name>`) for non-git work. Silently cataloguing
  `tax-docs` or `side-hustle` directories would erode trust.
- Migrating historical hub sessions automatically. `halyard reattribute` (future)
  handles that explicitly.
