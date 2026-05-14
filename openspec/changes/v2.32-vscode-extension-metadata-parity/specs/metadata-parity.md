# Spec: Cross-Tool Metadata Parity

## Requirement: Shared optional metadata vocabulary

Halyard MUST define a shared optional metadata vocabulary for interaction,
timing, outcome, and provenance fields.

### Scenario: old log line remains valid

WHEN Halyard parses an `ai-sessions.log` line without metadata parity fields
THEN parsing succeeds
AND new metadata fields are unset.

### Scenario: metadata fields are present

WHEN Halyard parses a line with known metadata parity `key=value` fields
THEN those fields are populated on the session object
AND unknown fields are ignored for backward compatibility.

## Requirement: unavailable is not zero

Halyard MUST distinguish a measured zero from unavailable data.

### Scenario: interaction count unavailable

WHEN a collector cannot observe interaction count
THEN it MUST omit `interaction_count` or set `interaction_data_available=false`
AND reports MUST NOT display the value as `0`.

### Scenario: zero interactions observed

WHEN a collector can observe interactions and the measured count is zero
THEN it MAY write `interaction_count=0`
AND it MUST mark interaction data as available or captured.

## Requirement: metadata-only privacy boundary

Collectors MUST NOT serialize prompts, chat text, source code, filenames, file
contents, terminal output, secrets, or transcripts.

### Scenario: native source contains prompt text

WHEN a collector reads a native source that contains prompt text
THEN it MAY count event types or tokens
AND it MUST NOT write the prompt text to `ai-sessions.log`.

### Scenario: native source contains filenames

WHEN a collector can determine files touched
THEN it MAY write `files_touched_count`
AND it MUST NOT write filenames or paths as metadata.

## Requirement: collector coverage tables

Each collector SHOULD document its metadata coverage.

### Scenario: tool cannot expose a field

WHEN a field is unavailable for a tool
THEN the coverage table names the field as unavailable
AND reports remain truthful about the missing data.

### Scenario: field is derived

WHEN a collector derives a value from git, elapsed time, or another source
THEN the coverage table records the value as calculated, inferred, or observed
rather than captured.

## Requirement: cross-tool report compatibility

Reports SHOULD aggregate metadata parity fields across tools without requiring
every tool to populate every field.

### Scenario: mixed telemetry availability

WHEN a report includes sessions from tools with different metadata coverage
THEN available fields are aggregated
AND unavailable fields are counted separately
AND the report does not imply unavailable values are zero.

## Requirement: no productivity scoring

Halyard MUST NOT use metadata parity fields to rank developers or produce a
productivity score.

### Scenario: high interaction count

WHEN a session has many interactions
THEN Halyard may describe it as high-steering or review-worthy
AND MUST NOT label the user as low-productivity.

