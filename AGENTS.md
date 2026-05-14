<claude-mem-context>
# Memory Context

# [Halyard] recent context, 2026-05-14 1:33pm EDT

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (18,285t read) | 731,024t work | 97% savings

### May 13, 2026
S608 Codex sessions not appearing in Halyard web UI — root cause identified as wiped dedup state (May 13 at 12:26 AM)
### May 14, 2026
S609 Codex sessions not appearing in Halyard web UI — root cause investigated, fix validated, and state restored (May 14 at 11:42 AM)
S610 Codex not showing in Halyard web UI — root cause diagnosed, dedup fix validated, and v2.30 tool visibility spec fully written (May 14 at 11:47 AM)
S611 Codex not showing in Halyard web UI — debugging session log anomalies and hook configuration (May 14 at 11:52 AM)
S612 Codex not showing in Halyard web UI — root cause traced to missing Codex hook support and duplicate hook bug investigation (May 14 at 12:03 PM)
S613 Clarifying whether removing hooks from committed .claude/settings.json in Halyard repo affects personal or other users' hook installations (May 14 at 12:06 PM)
S614 Halyard install-hook duplicate-fire investigation and v2.31 spec creation for install-hook hardening (May 14 at 12:10 PM)
S615 Task status check across v2.30 and v2.31 specs; deciding which to implement first (May 14 at 12:17 PM)
S617 Halyard v2.30 (Tool Visibility) and v2.31 (Install-Hook Hardening) implementation and progress tracking (May 14 at 12:20 PM)
2120 1:05p 🔵 Halyard Version History: Test Count Progression Confirmed in project.md
2121 " 🔵 v2.32 VS Code Extension and Metadata Parity: Partially Implemented
2122 1:06p ✅ v2.32 Tasks.md Updated: 14 Tasks Marked Complete
2123 " 🟣 All v2.32 Targeted Tests Pass: 69 Tests Green Across 6 Test Files
S618 Halyard v2.30/v2.31 completion review and roadmap orientation toward v2.32 (May 14 at 1:06 PM)
2124 1:07p ⚖️ v2.32 Phase 2: Cursor/Codex Metadata Parity and Dashboard/TUI Exposure Planned
2125 " 🔵 Cursor and Codex Collectors Confirmed: No v2.32 Metadata Fields Yet
2126 " 🔵 Dashboard and TUI Do Not Yet Surface v2.32 Interaction Metadata
2127 1:08p 🔵 Codex JSONL Format Has No User/Assistant Message Events: Interaction Counts Unavailable
2128 " 🔵 Dashboard Health Badge and TUI Project Pane: Extension Points for v2.32 Metadata
2129 " 🔄 git_context.py: numstat_delta Refactored to Expose files_touched_count via numstat_summary
2130 1:09p 🟣 Cursor Collector Updated with v2.32 Interaction Metadata and Tool Count Extraction
2131 " 🟣 Codex Collector Updated: Speculative JSONL Event Parsing for Interaction and Tool Counts
2132 " 🟣 Dashboard Health Badge Extended with v2.32 Interaction, File, Test, and Build Status Signals
2133 1:10p 🟣 TUI Session Feed Extended with Inline v2.32 Metadata Badges
2134 " 🟣 TUI ProjectPane Health Lines Extended with Interaction, Files, and Test Aggregates
2135 " 🟣 Cursor Collector: Privacy Boundary and Metadata Extraction Test Added
2136 1:11p 🟣 Codex Importer: Privacy Boundary and JSONL Interaction Extraction Test Added
2137 " 🟣 Dashboard Test Added: v2.32 Metadata Count Badges Rendered in Health Column
2138 " 🟣 TUI Tests Added: ProjectPane Metadata Aggregates and SessionFeed Metadata Badges
2139 " 🟣 Phase 2 v2.32 Test Suite: All Tests Pass Across 6 Targeted Files
2140 " 🔴 Test Failures: test_collectors_outcome.py Monkeypatches Removed numstat_delta Import
2141 1:12p 🔴 Cursor Collector: Reverted numstat_summary to numstat_delta; files_touched_count Now Read from Payload
2143 " 🔴 Full 12-File Test Suite Passes After numstat_delta Fix: All 214+ Tests Green
2144 " ✅ v2.32 Tasks.md: 6 More Tasks Checked Off — Collector Parity and UI Work Complete
2145 1:13p 🔴 Codex _parse_iso Fixed: UTC Timestamps Now Normalized to Local-Naive (Not Naive-UTC)
2146 " 🟣 Dashboard Tool Usage Panel Upgraded: Full Table with Tokens Column Replaces Capped List
2147 " 🟣 TUI Tests Added: --hub Flag Routing and Project-Preference Logic
2148 1:16p 🟣 Large-Scale Halyard Codebase Expansion
2149 " 🔴 Windows Platform Safety — fcntl Conditional Import
2150 " 🔴 TOML Injection Fixed in voyages.py and git_context.py
2151 " 🔴 Session Hash Mismatch Fixed via _raw_hash Field
2152 " 🔴 SQLite Cache Staleness Fixed with INSERT OR REPLACE
2153 " 🔴 Datetime Timezone Normalization — All Collectors Emit Local-Naive
2154 " 🟣 v2.32 Privacy-Safe Interaction Metadata Fields Added to AiSession
2155 " 🟣 v2.29 Pre-Ship Hardening Milestone Shipped — 931 Tests Passing
2156 1:18p 🟣 v2.31 Install-Hook Cross-File Dedup Prevents Double-Recording
2157 " 🟣 record-session CLI Gains 20+ Metadata Flags
2158 " 🔴 halyard tui --hub Flag Fixes Log Path Selection Logic
2159 " 🟣 git_context.py Gains numstat_summary with Files-Touched Count
2160 " 🟣 All Major Collectors Now Emit Interaction Count Telemetry
2161 " ✅ ruff Pinned to ==0.15.12 in uv.lock
2162 1:19p 🔵 Code Review Found 2 Bugs and 4 Observations
2163 " 🔴 db.py Schema Fixed — code_added Column Added to CREATE TABLE
2164 1:20p 🔴 db.py Migration Fix Broke Tests — Duplicate Column and Version Mismatch
2165 " 🔴 db.py Tests Still Failing After Version Bump — 4 Remaining Issues
2166 " ✅ db.py Fixes Confirmed Intact After git stash pop
2167 1:21p 🔵 test_sync_applies_amendment_on_resync Failing — pr_ref Null After Re-sync
2168 1:22p 🔵 parse_sessions Amendment Folding Traced — Possible #-char Issue in pr_ref Value
2169 1:23p 🔵 Test Failures Caused by Unpatched find_hub() — Real Hub Sessions Contaminating Test DB
2170 1:33p 🔵 Codex Not Appearing in Halyard Web UI

Access 731k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>