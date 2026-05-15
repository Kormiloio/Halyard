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
    """Parse a float from untrusted git-diff text; None if malformed.

    The `[0-9.]+` capture can match e.g. `1.2.3`; a crafted commit diff
    must not abort the whole rate-history audit with a ValueError.
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
    """Derive rate changes from git log of clients.toml."""
    try:
        result = subprocess.run(
            ["git", "log", "--follow", "-p", "--", "clients.toml"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    if result.returncode != 0 or not result.stdout.strip():
        return []

    changes: list[RateChange] = []
    commit_sha = ""
    commit_date: date | None = None
    current_slug = ""

    for line in result.stdout.splitlines():
        if line.startswith("commit "):
            commit_sha = line.split()[1][:8]
            commit_date = None
            current_slug = ""
        elif line.startswith("Date:"):
            commit_date = _parse_git_date(line[5:].strip())
        elif line.startswith("@@") or line.startswith("diff --git"):
            # Hunk / file boundary: the previous slug no longer governs the
            # rate lines that follow, so don't carry it across.
            current_slug = ""
        elif re.match(r'^\+\s*slug\s*=\s*["\']?([A-Za-z0-9_:/-]+)', line):
            # Anchored to the `slug` key itself — must not match
            # `+client_slug =` or `+project_slug =`.
            m = re.match(r'^\+\s*slug\s*=\s*["\']?([A-Za-z0-9_:/-]+)', line)
            if m:
                current_slug = m.group(1)
        elif line.startswith("+hourly_rate") and "=" in line and commit_date:
            m = re.search(r"hourly_rate\s*=\s*([0-9.]+)", line)
            rate = _safe_float(m.group(1)) if m else None
            if rate is not None and current_slug:
                changes.append(
                    RateChange(
                        client_slug=current_slug,
                        effective_date=commit_date,
                        rate=rate,
                        source=f"git:{commit_sha}",
                    )
                )
        elif re.match(r"^\+rate\s*=", line) and commit_date and current_slug:
            m = re.search(r"rate\s*=\s*([0-9.]+)", line)
            rate = _safe_float(m.group(1)) if m else None
            if rate is not None:
                changes.append(
                    RateChange(
                        client_slug=current_slug,
                        effective_date=commit_date,
                        rate=rate,
                        source=f"git:{commit_sha}",
                    )
                )

    return sorted(changes, key=lambda c: (c.effective_date, c.client_slug))


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
        text = path.read_text()
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
