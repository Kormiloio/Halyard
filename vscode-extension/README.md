# Halyard VS Code Extension

Privacy-safe VS Code session capture for Halyard.

The extension records coarse metadata through the Halyard CLI — it does not
capture prompts, code, chat text, file names, or file contents.

Captured fields: session duration, branch name, changed file count,
added/removed line counts, human active and idle seconds, telemetry
source/trust markers.

## Requirements

- [Halyard](https://github.com/Kormiloio/Halyard) installed and on `PATH`
  (`pipx install halyard`)
- A Halyard project initialised in the workspace (`halyard init`)

## Install

### From .vsix (local build)

```bash
cd vscode-extension
npm install
npm run compile
vsce package
code --install-extension halyard-vscode-0.1.0.vsix
```

Reload VS Code after install.

### From Extension Development Host (while iterating)

Open the `vscode-extension/` folder in VS Code and press **F5**. A second
window opens with the extension loaded. No packaging needed.

## Usage

All commands are available via the Command Palette (`Cmd+Shift+P`):

| Command | What it does |
|---|---|
| **Halyard: Start AI Work** | Begins a timed session; status bar shows elapsed time |
| **Halyard: Stop and Record AI Work** | Stops the timer and writes the session to `ai-sessions.log` |
| **Halyard: Record AI Session** | One-shot manual entry with a duration prompt |
| **Halyard: Open Dashboard** | Opens `halyard dashboard` in a background process |
| **Halyard: Show Current Scope** | Shows workspace path, branch, and elapsed time |

If VS Code quits mid-session, a recovery prompt appears on the next launch
offering to record, continue, or discard the unfinished session.

## Configuration

Settings are under `halyard.*` in VS Code preferences:

| Setting | Default | Description |
|---|---|---|
| `halyard.executable` | `"halyard"` | Path to the Halyard CLI |
| `halyard.defaultModel` | `"github-copilot"` | Model label for VS Code sessions |
| `halyard.idleAfterSeconds` | `300` | Seconds without activity counted as idle |

## Development

```bash
npm install
npm run compile   # tsc
npm test          # vitest (pure unit tests, no VS Code infrastructure needed)
npm run watch     # tsc --watch for iterating with F5
```
