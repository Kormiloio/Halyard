"""Local AI-work evidence appendix (v2.68) — the OSS slice of v2.19.

Standalone emission of the existing invoice evidence appendix
(`invoicing.render_ai_evidence_appendix`) plus a deterministic,
**keyless** integrity digest.

The digest is tamper-EVIDENT: the author can publish it and anyone can
re-hash the artifact to confirm it was not altered. It is NOT a
signature and NOT proof of authorship. Cryptographic attestation
(signed, verifiable, cross-party) is a Halyard Enterprise feature and
deliberately lives in the enterprise repo, not here.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

_DIGEST_PREFIX = "Evidence digest: sha256:"
_BOUNDARY = (
    "Unsigned local evidence — the digest detects post-hoc modification of "
    "this exact artifact (byte-for-byte); it does not prove authorship. "
    "Cryptographic attestation is a Halyard Enterprise feature."
)
# The footer is OUTSIDE the hashed region. It always begins with this
# separator immediately followed by the digest line, so the body can be
# split back out unambiguously (the appendix body never contains the
# digest-prefixed form).
_FOOTER_MARKER = "\n---\n" + _DIGEST_PREFIX


def _canonical_body(body: str) -> str:
    """Normalise to a single trailing newline so emit and verify agree
    regardless of incidental trailing whitespace."""
    return body.rstrip("\n") + "\n"


def compute_digest(body: str) -> str:
    """SHA-256 over the canonical appendix body (hex)."""
    return hashlib.sha256(_canonical_body(body).encode("utf-8")).hexdigest()


def assemble_artifact(body: str) -> str:
    """Compose the canonical body + the (unhashed) integrity footer."""
    canonical = _canonical_body(body)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    footer = f"\n---\n{_DIGEST_PREFIX}{digest}\n\n{_BOUNDARY}\n"
    return canonical + footer


def build_evidence_artifact(
    project_dir: Path,
    *,
    project: str | None = None,
    client: str | None = None,
    all_time: bool = False,
    month: str | None = None,
    now: datetime | None = None,
) -> str:
    """Build the standalone evidence artifact for the selected period.

    Reuses the existing appendix renderer verbatim (no second
    renderer) and the same session selection as `halyard report`.
    """
    from halyard.ai_plans import read_ai_plans
    from halyard.invoicing import render_ai_evidence_appendix
    from halyard.reports import build_filtered_ai_report, parse_timeclock

    clock = now or datetime.now()
    period = datetime.strptime(month, "%Y-%m") if month else clock

    report = build_filtered_ai_report(
        project_dir, project=project, client=client, all_time=all_time, now=period
    )
    plans = read_ai_plans(project_dir)
    tc_entries = parse_timeclock(project_dir / "time.timeclock")
    body = render_ai_evidence_appendix(report.sessions, plans, tc_entries, report.period_label)
    return assemble_artifact(body)


def build_evidence_data(
    project_dir: Path,
    *,
    project: str | None = None,
    client: str | None = None,
    all_time: bool = False,
    month: str | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Structured form of the evidence appendix (v2.69 `--json`).

    Same selection + numbers as the markdown appendix, as data. There
    is deliberately **no digest** here: the v2.68 integrity digest is
    defined over the markdown artifact only; this JSON is unsigned
    data, not a digested artifact.
    """
    from collections import defaultdict

    from halyard.ai_plans import read_ai_plans
    from halyard.ledger import build_ledger
    from halyard.reports import build_filtered_ai_report, parse_timeclock

    clock = now or datetime.now()
    period = datetime.strptime(month, "%Y-%m") if month else clock
    report = build_filtered_ai_report(
        project_dir, project=project, client=client, all_time=all_time, now=period
    )
    sessions = report.sessions

    by_ref: dict[str, list] = defaultdict(list)  # type: ignore[type-arg]
    for s in sessions:
        if s.pr_ref:
            by_ref[s.pr_ref].append(s)
    pr_refs = []
    for ref in sorted(by_ref):
        bucket = sorted(by_ref[ref], key=lambda s: s.outcome_resolved_at or "", reverse=True)
        pr_refs.append({"ref": ref, "state": bucket[0].pr_state or None, "sessions": len(bucket)})

    data: dict[str, object] = {
        "period_label": report.period_label,
        "filter": {"project": project, "client": client},
        "tools": sorted({s.tool for s in sessions}),
        "models": sorted({s.model for s in sessions}),
        "metrics": {
            "sessions": len(sessions),
            "active_minutes": sum(
                max(1, int((s.end - s.start).total_seconds() // 60)) for s in sessions
            ),
            "input_tokens": report.total_input_tokens,
            "output_tokens": report.total_output_tokens,
            "cache_read_tokens": report.total_cache_read_tokens,
            "cache_write_tokens": report.total_cache_write_tokens,
        },
        "pr_refs": pr_refs,
        "digest": None,  # explicit: JSON is not a digested artifact
    }

    if sessions:
        ps = min(s.start for s in sessions)
        summary = build_ledger(
            sessions,
            read_ai_plans(project_dir),
            parse_timeclock(project_dir / "time.timeclock"),
            year=ps.year,
            month=ps.month,
        )
        data["cost"] = {
            "direct_usd": round(summary.total_direct_usd, 4),
            "allocated_usd": round(summary.total_allocated_usd, 4),
            "total_usd": round(summary.total_usd, 4),
        }
        data["has_inferred_attribution"] = any(e.has_inferred_attribution for e in summary.entries)
    else:
        data["cost"] = {"direct_usd": 0.0, "allocated_usd": 0.0, "total_usd": 0.0}
        data["has_inferred_attribution"] = False
    return data


def verify_evidence_artifact(text: str) -> bool:
    """True iff the embedded digest matches a re-hash of the body.

    Pure local recomputation — no key, the same check anyone could do
    by hand. Returns False if the footer is missing/malformed.
    """
    idx = text.rfind(_FOOTER_MARKER)
    if idx == -1:
        return False
    body = text[:idx]
    after_sep = text[idx + len("\n---\n") :]
    first_line = after_sep.splitlines()[0] if after_sep else ""
    if not first_line.startswith(_DIGEST_PREFIX):
        return False
    claimed = first_line[len(_DIGEST_PREFIX) :].strip()
    return bool(claimed) and claimed == compute_digest(body)
