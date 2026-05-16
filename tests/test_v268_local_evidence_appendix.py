"""v2.68 — Local AI-work evidence appendix (OSS slice of v2.19).

v2.19 (signed/verifiable/cross-party) stays in the enterprise repo.
This locks the OSS-safe slice: a standalone `halyard evidence`
artifact that reuses the existing appendix renderer verbatim and adds
a deterministic, keyless, tamper-evident digest — explicitly NOT a
signature and NOT authorship proof.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.cli import app
from halyard.evidence import build_evidence_artifact, verify_evidence_artifact

runner = CliRunner()


def _init(tmp: Path) -> None:
    (tmp / "halyard.toml").write_text("[business]\nname = 'Acme'\n")
    (tmp / "time.timeclock").write_text("; time\n")
    (tmp / AI_LOG_FILENAME).write_text(HEADER)


def _add(tmp: Path, *, note: str | None = None) -> None:
    append_session(
        tmp,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0123,
            project="acme:auth",
            note=note,
        ),
    )


# 1. renderer reuse — no second renderer ------------------------------------


def test_artifact_reuses_existing_appendix_renderer(tmp_path: Path) -> None:
    _init(tmp_path)
    _add(tmp_path)
    from halyard.ai_plans import read_ai_plans
    from halyard.invoicing import render_ai_evidence_appendix
    from halyard.reports import build_filtered_ai_report, parse_timeclock

    art = build_evidence_artifact(tmp_path, all_time=True)

    report = build_filtered_ai_report(tmp_path, all_time=True)
    body = render_ai_evidence_appendix(
        report.sessions,
        read_ai_plans(tmp_path),
        parse_timeclock(tmp_path / "time.timeclock"),
        report.period_label,
    )
    # The exact renderer output is embedded verbatim (modulo trailing nl).
    assert body.strip() in art
    assert "## AI Usage Evidence" in art


# 2. deterministic digest ---------------------------------------------------


def test_digest_deterministic_and_sensitive(tmp_path: Path) -> None:
    _init(tmp_path)
    _add(tmp_path)
    a1 = build_evidence_artifact(tmp_path, all_time=True)
    a2 = build_evidence_artifact(tmp_path, all_time=True)
    assert a1 == a2  # byte-identical across runs

    # A one-token change flips the digest.
    _add(tmp_path)  # second session changes the body
    a3 = build_evidence_artifact(tmp_path, all_time=True)
    d1 = next(ln for ln in a1.splitlines() if ln.startswith("Evidence digest:"))
    d3 = next(ln for ln in a3.splitlines() if ln.startswith("Evidence digest:"))
    assert d1 != d3


# 3. verify: clean vs tampered ---------------------------------------------


def test_verify_detects_modification(tmp_path: Path) -> None:
    _init(tmp_path)
    _add(tmp_path)
    art = build_evidence_artifact(tmp_path, all_time=True)
    assert verify_evidence_artifact(art) is True

    tampered = art.replace("| Sessions | 1 |", "| Sessions | 99 |")
    assert tampered != art
    assert verify_evidence_artifact(tampered) is False

    assert verify_evidence_artifact("no footer here") is False


# 4. wall-clock is outside the hashed region --------------------------------


def test_digest_independent_of_wall_clock(tmp_path: Path) -> None:
    _init(tmp_path)
    _add(tmp_path)
    # Different "now" but all_time → period_label constant → identical
    # artifact, proving no wall-clock value enters the hashed body.
    a1 = build_evidence_artifact(tmp_path, all_time=True, now=datetime(2026, 5, 9, 1, 0))
    a2 = build_evidence_artifact(tmp_path, all_time=True, now=datetime(2027, 1, 1, 23, 0))
    assert a1 == a2


# 5. privacy — no prompt/note/code content ----------------------------------


def test_artifact_contains_no_note_or_content(tmp_path: Path) -> None:
    _init(tmp_path)
    _add(tmp_path, note="SECRET-PROMPT-LEAK-CANARY")
    art = build_evidence_artifact(tmp_path, all_time=True)
    assert "SECRET-PROMPT-LEAK-CANARY" not in art


# 6. honest boundary, no overclaim ------------------------------------------


def test_honest_boundary_no_authorship_claim(tmp_path: Path) -> None:
    _init(tmp_path)
    _add(tmp_path)
    art = build_evidence_artifact(tmp_path, all_time=True)
    assert "does not prove authorship" in art
    assert "Halyard Enterprise feature" in art
    low = art.lower()
    # The OSS artifact must never claim to be signed / authorship-proving.
    assert "digitally signed" not in low
    assert "signed by" not in low
    assert "proves you" not in low


# 7. CLI: stdout default, --out/--force, --verify ---------------------------


def test_cli_stdout_out_force_and_verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init(tmp_path)
    _add(tmp_path)
    monkeypatch.chdir(tmp_path)

    res = runner.invoke(app, ["evidence", "--all"])
    assert res.exit_code == 0
    assert "## AI Usage Evidence" in res.output
    assert "Evidence digest: sha256:" in res.output

    out = tmp_path / "evidence.md"
    assert runner.invoke(app, ["evidence", "--all", "--out", str(out)]).exit_code == 0
    first = out.read_text()
    assert verify_evidence_artifact(first)

    # Refuses to overwrite without --force.
    blocked = runner.invoke(app, ["evidence", "--all", "--out", str(out)])
    assert blocked.exit_code == 1
    assert out.read_text() == first

    assert runner.invoke(app, ["evidence", "--all", "--out", str(out), "--force"]).exit_code == 0

    # --verify on the written artifact succeeds; fails after a tamper.
    assert runner.invoke(app, ["evidence", "--verify", str(out)]).exit_code == 0
    out.write_text(first.replace("Sessions | 1", "Sessions | 7"))
    assert runner.invoke(app, ["evidence", "--verify", str(out)]).exit_code == 1
