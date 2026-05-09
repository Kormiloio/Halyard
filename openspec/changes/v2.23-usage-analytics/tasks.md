# Tasks

Implementation checklist for v2.23 - Usage Analytics.

## 1. Product and spec

- [x] 1.1 Write Usage Analytics PRD.
- [x] 1.2 Add OpenSpec proposal, design, and requirements.
- [ ] 1.3 Review terminology against README and current dashboard docs.

## 2. Shared aggregation service

- [x] 2.1 Add `src/halyard/usage.py` view models.
- [x] 2.2 Implement all/30d/7d range filtering.
- [x] 2.3 Implement daily usage buckets.
- [x] 2.4 Implement model and tool buckets.
- [x] 2.5 Implement active day, current streak, longest streak, and peak hour.
- [x] 2.6 Implement favorite model selection.
- [x] 2.7 Preserve missing-token and unavailable-data metadata.

## 3. CLI

- [ ] 3.1 Add `halyard usage`.
- [ ] 3.2 Add `--range all|30d|7d`.
- [ ] 3.3 Add `--json`.
- [ ] 3.4 Reuse shared usage service rather than duplicating report logic.

## 4. Dashboard

- [x] 4.1 Add Usage view entry point from the local dashboard.
- [ ] 4.2 Add Overview and Models tabs.
- [ ] 4.3 Add range segmented control.
- [x] 4.4 Add summary metric cards.
- [x] 4.5 Add activity heatmap.
- [ ] 4.6 Add daily model usage chart.
- [x] 4.7 Add model and tool breakdown rows.
- [ ] 4.8 Add empty and missing-data states.

## 5. Visual quality

- [ ] 5.1 Define model color palette.
- [ ] 5.2 Verify desktop and narrow laptop layouts.
- [ ] 5.3 Ensure chart labels and stat text do not overflow.
- [ ] 5.4 Add accessible labels for heatmap cells and chart bars.
- [ ] 5.5 Capture screenshot before release.

## 6. Tests

- [ ] 6.1 Test empty session data.
- [x] 6.2 Test range boundaries with fixed `now`.
- [x] 6.3 Test active days and streaks.
- [ ] 6.4 Test peak hour tie-breaking.
- [ ] 6.5 Test favorite model fallback behavior.
- [ ] 6.6 Test model/tool share calculations.
- [x] 6.7 Test `tokens_available=false` handling.
- [ ] 6.8 Test CLI JSON output.
- [x] 6.9 Test dashboard Usage view renders core sections.

## 7. Documentation

- [ ] 7.1 Add README mention once implemented.
- [ ] 7.2 Add demo screenshot or GIF once the dashboard view exists.
- [ ] 7.3 Add troubleshooting note for missing token/cost data.
