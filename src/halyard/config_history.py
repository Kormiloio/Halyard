"""Rate history and invoice audit for Halyard config versioning."""

from __future__ import annotations

import contextlib
import re
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class RateChange:
    client_slug: str
    effective_date: date
    rate: float
    source: str  # "rate_history" or "git:<sha8>"


@dataclass
class AuditMismatch:
    invoice_file: str
    client_slug: str
    period: str  # YYYY-MM
    expected_rate: float
    actual_rate: float
    rate_source: str = "structured"  # "structured" (front-matter) or "inferred" (regex)


def _safe_float(s: str) -> float | None:
    """Parse a float from untrusted text; None if malformed.

    Originally used by the line-by-line git-diff parser (v5.19/B-rate-structural
    replaced that with structural TOML reads of each historical snapshot, so
    untrusted regex-captured values no longer reach this helper). Retained
    for the public security-test contract (v2.39): a crafted value must not
    abort the audit with a ValueError.
    """
    try:
        return float(s)
    except ValueError:
        return None


def rate_history_from_toml(project_dir: Path) -> list[RateChange]:
    """Read rate changes from [[client.rate_history]] entries in clients.toml."""
    from halyard.invoicing import _read_clients

    changes: list[RateChange] = []
    for client in _read_clients(project_dir).values():
        for eff_date, rate in sorted(client.rate_history):
            changes.append(
                RateChange(
                    client_slug=client.slug,
                    effective_date=eff_date,
                    rate=rate,
                    source="rate_history",
                )
            )
    return sorted(changes, key=lambda c: (c.effective_date, c.client_slug))


def rate_history_from_git(project_dir: Path) -> list[RateChange]:
    """Derive rate changes from git log of clients.toml.

    v5.19/B-rate-structural: this used to walk the unified diff line-by-line
    and pull the governing slug from the same hunk. Git's default unified
    diff exposes only ±3 context lines, so a client whose ``slug`` and
    ``hourly_rate`` keys are >3 lines apart (a real config carrying name,
    email, address, etc.) silently dropped rate changes. We now ask git
    for the *full file contents* at every commit that touched
    ``clients.toml``, parse each version as TOML, and emit a RateChange
    whenever a slug's rate differs from the previous commit's rate.
    Structural parsing makes the hunk geometry irrelevant.

    v5.19/B-rate-rename: previously this used ``--reverse`` and assumed the
    file was always named ``clients.toml``. ``git log --follow`` does
    traverse renames, but ``git show <sha>:clients.toml`` fails for
    pre-rename commits because the file was named something else then —
    so the entire pre-rename history was silently dropped (e.g. a
    ``customers.toml`` → ``clients.toml`` rename truncated the audit
    trail to just the post-rename commits). We now walk newest-first
    *with* ``--name-only`` so each commit reports its own path, then
    reverse the collected snapshots in Python.
    """
    snapshots = _historical_clients_toml_snapshots(project_dir)
    if not snapshots:
        return []

    changes: list[RateChange] = []
    prev_rates: dict[str, float] = {}
    # Oldest-first so a single linear scan emits one RateChange per slug
    # per change in chronological order.
    for sha, eff_date, contents in reversed(snapshots):
        for slug, rate in _rates_from_clients_toml(contents):
            if prev_rates.get(slug) == rate:
                continue
            changes.append(
                RateChange(
                    client_slug=slug,
                    effective_date=eff_date,
                    rate=rate,
                    source=f"git:{sha[:8]}",
                )
            )
            prev_rates[slug] = rate

    return sorted(changes, key=lambda c: (c.effective_date, c.client_slug))


def _historical_clients_toml_snapshots(
    project_dir: Path,
) -> list[tuple[str, date, str]]:
    """Return ``(sha, effective_date, contents)`` newest-first for every
    commit that touched the current ``clients.toml`` (or its predecessors
    across renames).

    Uses ``--follow --name-only`` so each commit reports the *path the
    file had at that commit* — necessary to ``git show <sha>:<path>``
    for pre-rename history. Newest-first traversal matches how
    ``--follow`` works under the hood; the caller reverses if it wants
    chronological order.
    """
    try:
        log = subprocess.run(
            [
                "git",
                "log",
                "--follow",
                "--name-only",
                # Sentinel-prefixed header so we can unambiguously split
                # commit blocks even when the historical filename ever
                # happened to start with the prefix.
                "--format=__halyard_commit__ %H %aI",
                "--",
                "clients.toml",
            ],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    if log.returncode != 0 or not log.stdout.strip():
        return []

    snapshots: list[tuple[str, date, str]] = []
    current_sha = ""
    current_date: date | None = None
    current_path = ""
    for raw_line in log.stdout.splitlines():
        line = raw_line.rstrip()
        if line.startswith("__halyard_commit__ "):
            # Commit the previous block (if it had a path).
            if current_sha and current_date and current_path:
                contents = _git_show_path(project_dir, current_sha, current_path)
                if contents is not None:
                    snapshots.append((current_sha, current_date, contents))
            # Start a new block.
            parts = line.split(" ", 2)
            current_sha = parts[1] if len(parts) > 1 else ""
            current_date = _iso_to_date(parts[2]) if len(parts) > 2 else None
            current_path = ""
            continue
        if not line.strip():
            continue
        # `--name-only` lists every file in the commit; with `--follow`
        # against a single path, only the followed entry (or its
        # rename source/dest) appears, so we just take the first one.
        if not current_path:
            current_path = line.strip()
    # Flush the trailing block.
    if current_sha and current_date and current_path:
        contents = _git_show_path(project_dir, current_sha, current_path)
        if contents is not None:
            snapshots.append((current_sha, current_date, contents))
    return snapshots


def _git_show_path(project_dir: Path, sha: str, path: str) -> str | None:
    """Return ``path`` contents at ``sha``, or None if unavailable.

    Replaces the prior ``_git_show_clients_toml`` (which hard-coded the
    filename and therefore failed for every pre-rename commit).
    """
    try:
        result = subprocess.run(
            ["git", "show", f"{sha}:{path}"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _rates_from_clients_toml(contents: str) -> list[tuple[str, float]]:
    """Return ``[(slug, hourly_rate), …]`` from a clients.toml snapshot.

    Tolerant of malformed historical files: a parse error just yields an
    empty list so a bad commit cannot abort the whole rate history.
    Recognises both ``hourly_rate`` (canonical) and the legacy ``rate``
    key, mirroring the diff-parser's behaviour.
    """
    import tomllib

    try:
        data = tomllib.loads(contents)
    except (tomllib.TOMLDecodeError, ValueError):
        return []

    out: list[tuple[str, float]] = []
    for client in data.get("client", []):
        if not isinstance(client, dict):
            continue
        slug = client.get("slug")
        if not isinstance(slug, str) or not slug:
            continue
        raw_rate = client.get("hourly_rate")
        if raw_rate is None:
            raw_rate = client.get("rate")
        if raw_rate is None:
            continue
        if isinstance(raw_rate, bool):  # bool is a subclass of int
            continue
        if not isinstance(raw_rate, int | float):
            continue
        out.append((slug, float(raw_rate)))
    return out


def is_git_repo(project_dir: Path) -> bool:
    """Return True if project_dir is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=project_dir,
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def audit_invoices(
    project_dir: Path,
    *,
    client_filter: str | None = None,
    period_filter: str | None = None,
) -> list[AuditMismatch]:
    """Compare rates recorded in invoices against effective rates from clients.toml."""
    from halyard.invoicing import _effective_rate, _read_clients

    invoice_dir = project_dir / "invoices"
    if not invoice_dir.exists():
        return []

    clients = _read_clients(project_dir)
    mismatches: list[AuditMismatch] = []

    for path in sorted(invoice_dir.glob("*.md")):
        meta = _parse_invoice_meta(path)
        if meta is None:
            continue

        client_slug, period, rates = meta

        if client_filter and client_slug != client_filter:
            continue
        if period_filter and period != period_filter:
            continue

        client = clients.get(client_slug)
        if client is None:
            continue

        try:
            year, month = int(period[:4]), int(period[5:7])
            period_start = date(year, month, 1)
        except (ValueError, IndexError):
            continue

        expected = _effective_rate(client, period_start)
        for actual, rate_source in rates:
            if abs(actual - expected) > 0.005:
                mismatches.append(
                    AuditMismatch(
                        invoice_file=path.name,
                        client_slug=client_slug,
                        period=period,
                        expected_rate=expected,
                        actual_rate=actual,
                        rate_source=rate_source,
                    )
                )

    return mismatches


def _parse_invoice_meta(
    path: Path,
) -> tuple[str, str, list[tuple[float, str]]] | None:
    """Return (client_slug, period, [(rate, source), ...]) from an invoice .md file.

    source is "structured" when rates come from front-matter YAML (v2.18+)
    or "inferred" when parsed from the rendered markdown table (pre-v2.18).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    lines = text.splitlines()
    client_slug = ""
    invoice_number = ""
    template_version = 1
    in_front = False
    front_matter_lines: list[str] = []

    for i, line in enumerate(lines):
        if i == 0 and line.strip() == "---":
            in_front = True
            continue
        if in_front and line.strip() == "---":
            in_front = False
            break
        if in_front:
            front_matter_lines.append(line)
            if line.startswith("client_slug:"):
                client_slug = line.split(":", 1)[1].strip()
            elif line.startswith("invoice_number:"):
                invoice_number = line.split(":", 1)[1].strip()
            elif line.startswith("template_version:"):
                with contextlib.suppress(ValueError):
                    template_version = int(line.split(":", 1)[1].strip())

    if not client_slug or not invoice_number:
        return None

    period = invoice_number[:7]
    if not re.match(r"^\d{4}-\d{2}$", period):
        return None

    if template_version >= 2:
        rates = _parse_rates_from_front_matter(front_matter_lines)
        if rates:
            return client_slug, period, [(r, "structured") for r in rates]

    # Fall back to regex over rendered markdown table (pre-v2.18 invoices).
    return client_slug, period, [(r, "inferred") for r in _parse_invoice_rates(text)]


def _parse_rates_from_front_matter(front_matter_lines: list[str]) -> list[float]:
    """Extract rate values from the rates: block in YAML front-matter."""
    rates: list[float] = []
    in_rates = False

    for line in front_matter_lines:
        stripped = line.strip()
        if stripped == "rates:":
            in_rates = True
            continue
        if in_rates:
            if stripped.startswith("- ") or stripped.startswith("rate:"):
                pass  # continue scanning
            elif stripped and not stripped.startswith("-") and ":" in stripped:
                key = stripped.split(":")[0].strip()
                if key not in ("description", "hours", "rate", "currency", "amount"):
                    in_rates = False
                    continue
            if stripped.startswith("rate:"):
                try:
                    val = float(stripped.split(":", 1)[1].strip())
                    if val > 0:
                        rates.append(val)
                except ValueError:
                    pass

    return rates


def _parse_invoice_rates(text: str) -> list[float]:
    """Extract non-zero rate values from the line items table in an invoice."""
    rates: list[float] = []
    in_table = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if in_table:
                break
            continue
        if "Rate" in stripped and "Description" in stripped:
            in_table = True
            continue
        if not in_table:
            continue
        if re.match(r"^\|[-: |]+\|$", stripped):
            continue  # separator row
        cols = [c.strip() for c in stripped.split("|")]
        # cols layout: ['', description, hours, rate, amount, '']
        if len(cols) >= 5:
            parts = cols[3].split()
            if parts:
                try:
                    val = float(parts[-1])
                    if val > 0:
                        rates.append(val)
                except ValueError:
                    pass

    return rates


def _iso_to_date(iso: str) -> date | None:
    """Parse an ISO-8601 timestamp (``%aI`` format) into a calendar date."""
    try:
        from datetime import datetime as _dt

        return _dt.fromisoformat(iso.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def _parse_git_date(date_str: str) -> date | None:
    """Parse a git log Date: header into a date object."""
    try:
        import email.utils

        parsed = email.utils.parsedate(date_str)
        if parsed:
            return date(parsed[0], parsed[1], parsed[2])
    except Exception as e:
        from halyard.ai_log import _log_error

        _log_error(f"_parse_git_date failed for {date_str!r}", e)
    return None
