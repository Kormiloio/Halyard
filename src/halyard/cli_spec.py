"""Public ai-sessions.log specification command."""

from __future__ import annotations

import typer

from halyard.ai_log import _FIELDS, SPEC_URL, FieldKind


def _kind_label(kind: FieldKind) -> str:
    match kind:
        case FieldKind.SAFE_FIELD:
            return "string"
        case FieldKind.INT:
            return "integer"
        case FieldKind.FLOAT_4:
            return "number"
        case FieldKind.BOOL_LOWER | FieldKind.TOKENS_AVAILABLE:
            return "boolean"
        case FieldKind.BILLING:
            return "billing string"
        case FieldKind.TAGS:
            return "list"
        case FieldKind.FREE_TEXT:
            return "percent-encoded string"
        case FieldKind.BREAKDOWN:
            return "model breakdown string"


def generate_ai_sessions_spec() -> str:
    """Return the public Markdown spec for `ai-sessions.log`."""
    lines = [
        "# Halyard ai-sessions.log Format v1",
        "",
        f"Canonical URL: {SPEC_URL}",
        "",
        "## Session Records",
        "",
        "```text",
        "s <start> <end> <tool> <model> <input_tokens> <output_tokens> <cost_usd> [key=value ...]",
        "```",
        "",
        "Required fields:",
        "",
        "| Position | Name | Type | Notes |",
        "|---:|---|---|---|",
        "| 1 | `start` | ISO timestamp | Session start time. |",
        "| 2 | `end` | ISO timestamp | Session end time. |",
        "| 3 | `tool` | string | AI tool identifier. |",
        "| 4 | `model` | string | Model identifier. |",
        "| 5 | `input_tokens` | integer | Non-negative input token count. |",
        "| 6 | `output_tokens` | integer | Non-negative output token count. |",
        "| 7 | `cost_usd` | number | Non-negative USD cost. |",
        "",
        "Optional fields:",
        "",
        "| Key | Attribute | Type |",
        "|---|---|---|",
    ]
    for spec in _FIELDS:
        lines.append(f"| `{spec.key}` | `{spec.attr}` | {_kind_label(spec.kind)} |")

    lines.extend(
        [
            "",
            "## Amendment Records",
            "",
            "```text",
            "a <session_hash> key=value [key=value ...]",
            "```",
            "",
            "Amendment records append corrections without rewriting original session records.",
            "The hash is the first 12 hex characters of SHA-256 over the original `s` line.",
            "",
            "## Hub Ingestion",
            "",
            "`POST /v1/ingest` accepts either a raw canonical line:",
            "",
            "```json",
            (
                '{"line": "s 2026-05-23T10:00:00 2026-05-23T10:05:00 '
                'custom-tool model-x 100 50 0.0100"}'
            ),
            "```",
            "",
            "or a structured fields object:",
            "",
            "```json",
            (
                '{"fields": {"start": "2026-05-23T10:00:00", '
                '"end": "2026-05-23T10:05:00", "tool": "custom-tool", '
                '"model": "model-x", "input_tokens": 100, "output_tokens": 50, '
                '"cost_usd": 0.01}}'
            ),
            "```",
            "",
            (
                "Structured ingestion rejects missing required fields, unknown keys, "
                "and invalid types."
            ),
            (
                "Halyard records metadata only: prompts, code, file contents, "
                "and transcripts do not belong in this log."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def register(app: typer.Typer) -> None:
    @app.command("spec")
    def spec() -> None:
        """Print the public ai-sessions.log Markdown specification."""
        typer.echo(generate_ai_sessions_spec())
