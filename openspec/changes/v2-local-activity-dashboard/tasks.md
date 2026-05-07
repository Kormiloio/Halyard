# Tasks

Implementation checklist for v2 — Local Activity Dashboard.

## 1. Product and architecture

- [x] 1.1 Write local dashboard PRD.
- [x] 1.2 Add Glass Cockpit UI direction and user stories.
- [x] 1.3 Choose initial server approach: FastAPI/Starlette or standard-library
      HTTP server.
- [x] 1.4 Define dashboard route map and shared view models.
- [x] 1.5 Decide package layout for templates and static assets.

## 2. Shared report services

- [x] 2.1 Extract AI session parsing into reusable service functions.
- [ ] 2.2 Extract timeclock parsing and project-hour aggregation.
- [x] 2.3 Extract AI cost aggregation from CLI report logic.
- [x] 2.4 Add health-check service for project files and collectors.

## 3. CLI command

- [x] 3.1 Add `halyard dashboard` command.
- [x] 3.2 Support `--port`, defaulting to an available local port.
- [x] 3.3 Support `--open` without launching a browser by default.
- [x] 3.4 Print the dashboard URL and shutdown instructions.

## 4. Dashboard views

- [x] 4.1 Build Glass Cockpit overview.
- [ ] 4.2 Build Today view.
- [x] 4.3 Build Projects view.
- [x] 4.4 Build Sessions view with filters.
- [ ] 4.5 Build Costs view with trust labels.
- [x] 4.6 Build Health view for collector status.

## 5. Modern UI quality

- [x] 5.1 Define visual system: typography, spacing, semantic colors, tables,
      metrics, and status indicators.
- [ ] 5.2 Add responsive layouts for laptop and desktop viewports.
- [x] 5.3 Ensure live updates do not shift or resize core dashboard regions.
- [ ] 5.4 Add empty, loading, healthy, warning, and error states for each view.
- [ ] 5.5 Verify dashboard screenshots before release.

## 6. Safety and trust

- [x] 6.1 Bind to `127.0.0.1` by default.
- [x] 6.2 Keep MVP read-only.
- [x] 6.3 Exclude prompts, transcripts, code contents, and secrets.
- [x] 6.4 Add tests for project discovery and missing-file health states.

## 7. Documentation and demo

- [x] 7.1 Document `halyard dashboard` in README.
- [ ] 7.2 Add a screenshot or GIF to the README once implemented.
- [ ] 7.3 Add demo script showing Claude Code capture appearing in the dashboard.
