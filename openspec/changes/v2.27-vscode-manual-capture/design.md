# Design: v2.27 — VS Code Manual Capture

## Capture Model

VS Code support reuses the existing manual session path instead of adding a
collector module. This keeps the data model honest: Halyard records the user's
declared work block, not a tool-native telemetry event.

The generated task uses:

```text
halyard record-session --tool vscode --model ${input:halyardModel} --minutes ${input:halyardMinutes} --note ${input:halyardNote}
```

`record-session` already resolves project attribution from `--project` or the
active timer. If the user starts a Halyard watch before working in VS Code, the
task records against that active project.

## File Written

`halyard install-vscode-tasks` writes `.vscode/tasks.json` in the current
workspace. It:

- preserves existing valid JSON content;
- creates `"version": "2.0.0"` when absent;
- appends the Halyard task only if no task with the same label exists;
- appends task inputs only when their `id` is absent.

Malformed existing JSON is treated as empty task configuration.

## Tool Identity

`tool=vscode` is the canonical slug. It maps to:

- Passport stamp: "VS Code" with the puzzle-piece icon;
- dashboard marker: `V`;
- TUI marker: `V`.

`github-copilot` is expected to appear as the model/assistant label by default,
not as the tool slug, because the user is operating inside VS Code.

## Privacy

The task prompts only for model label, minutes, and short note. It does not read
VS Code chat history, prompts, file contents, or workspace source files.

## Future Upgrade Path

If VS Code or GitHub Copilot exposes a stable public hook/API later, Halyard can
add a native collector that writes `source=hook` or `source=sdk`. That collector
should continue using `tool=vscode` or introduce a documented `tool=copilot`
migration only if the emitted events are no longer editor-scoped.
