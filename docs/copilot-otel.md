# VS Code Copilot capture via OpenTelemetry (v3.12)

Halyard captures GitHub Copilot agent sessions from the **OpenTelemetry**
stream VS Code emits (GenAI semantic conventions), instead of scraping VS
Code's undocumented internal storage. The internal files keep moving and
changing shape (that breakage is exactly why this path exists); the OTLP
stream is a documented, stable, opt-in source.

**Privacy:** Halyard ingests *metadata only* — model, token counts, tool-call
counts, durations, and the session id. Prompt text, responses, tool names, and
file paths are never read, even if VS Code's content capture is enabled. The
receiver binds `127.0.0.1` only.

## Recommended setup: built-in receiver

```sh
halyard install-vscode-otel   # writes the three github.copilot.chat.otel.* keys
                              # (after a diff-and-approve) + an opt-in marker
```

This points VS Code's Copilot OTLP exporter at `http://localhost:4318` and
records that you opted in. Then:

1. **Restart VS Code** so it picks up the settings.
2. Make sure the Halyard service is running: `halyard service install` (or
   `halyard dashboard`). The OTLP receiver runs *inside* that process and only
   starts when the opt-in marker is present — a default install gets no extra
   listener.

A Copilot agent session now produces an `AiSession` row live (no manual
import), aggregated per conversation and flushed after a short idle window (or
on service shutdown).

To turn it off:

```sh
halyard uninstall-vscode-otel   # removes the keys and the opt-in marker
```

`halyard doctor` warns when Copilot history is on disk but OTel capture isn't
wired up, and points to `install-vscode-otel`.

## Alternative: external OTel Collector (file export)

If you'd rather not run `halyard service`, point VS Code at a standard OpenTelemetry
Collector and have *it* listen on `:4318`. The mapper
(`halyard.collectors.vscode_otel.parse_traces_to_sessions`) accepts the same
OTLP/JSON payload, so a collector with a `file` exporter can feed Halyard the
same way the Gemini outfile path works (v2.67). This trades the zero-config
built-in receiver for a collector you maintain.

## Coexistence with the file importer

The v3.7 file importer (`halyard import-copilot`) stays as a fallback for
sessions captured before you enabled OTel. The two paths are dedup-coordinated
by VS Code's chat-session id: a session already captured via OTel (it carries
`job_id=copilot-otel:<id>` in the ledger) is skipped by the importer, so it is
never double-counted. OTel is the richer, live source and wins.

## Status / caveat

Phase-0 live verification (capturing one real Copilot OTLP payload to confirm
exact attribute placement) was **deferred** — the build environment had no
Copilot Chat extension. The mapper is built defensively against the documented
GenAI semconv and OTLP/JSON encoding (it probes both resource- and span-level
`session.id`, and harvests usage wherever it appears on spans). If a future VS
Code release places attributes differently, capture degrades gracefully
("unavailable is not zero") rather than crashing; re-verification against a live
payload is a fixture diff, not a rewrite.
