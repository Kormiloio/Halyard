# AI Work Reporting Spec

## Requirement: combined project report

Halyard MUST report human time and AI resource usage together for a client or
project.

### Scenario: project with human time and AI sessions

- WHEN the user runs `halyard report --project acme/auth-migration`
- THEN the report shows human hours from `time.timeclock`
- AND AI session count from `ai-sessions.log`
- AND token totals when available
- AND direct API cost
- AND allocated plan cost when configured
- AND total AI cost

### Scenario: project with no AI sessions

- WHEN the project has human time but no AI session records
- THEN the report still shows human hours
- AND states that no AI usage was captured

### Scenario: AI sessions without project attribution

- WHEN `ai-sessions.log` contains sessions without `project=`
- THEN the report shows an unattributed section
- AND does not silently assign those costs to a client invoice

## Requirement: cost trust labels

Halyard MUST label the source quality of reported costs.

### Scenario: captured API cost

- WHEN a session has `cost_usd` captured at write time
- THEN the report labels the cost as captured or calculated from captured token
  data

### Scenario: allocated seat cost

- WHEN a monthly seat cost is distributed across sessions
- THEN the report labels the cost as allocated

### Scenario: inferred project attribution

- WHEN Halyard infers a project from overlapping human timer windows
- THEN the report labels the attribution as inferred until confirmed

## Requirement: invoice evidence

Halyard MUST be able to produce client-safe AI usage evidence for invoices.

### Scenario: invoice appendix requested

- WHEN the user runs `halyard invoice acme --month last --include-ai-evidence`
- THEN Halyard generates a markdown appendix for the invoice
- AND the appendix summarizes tools, models, sessions, tokens, and AI costs
- AND it distinguishes captured, allocated, and inferred values

### Scenario: private content excluded

- WHEN the invoice appendix is generated
- THEN prompts, code contents, transcripts, and private tool outputs are not
  included by default
