"""Invoice generation from Halyard plain-text project files."""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import tomli_w
from jinja2 import Environment, FileSystemLoader

from halyard.ai_log import AiSession, parse_sessions
from halyard.ai_plans import AiPlan

# M-3/M-4: Slugs must be lowercase alphanumeric + hyphens only.
# This prevents path traversal (e.g. slug = "../../etc") and argument
# splitting in subprocess calls to open/xdg-open.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


@dataclass(frozen=True)
class ClientRecord:
    slug: str
    name: str
    hourly_rate: float
    email: str = ""
    address: str = ""
    rate_history: tuple[tuple[date, float], ...] = ()


@dataclass(frozen=True)
class ProjectRecord:
    slug: str
    client_slug: str
    name: str
    hourly_rate: float | None = None


@dataclass(frozen=True)
class InvoiceLineItem:
    description: str
    hours: float
    rate: float
    amount: float


@dataclass(frozen=True)
class InvoiceView:
    invoice_number: str
    client_slug: str
    issue_date: date
    due_date: date
    currency: str
    line_items: list[InvoiceLineItem]
    total: float


@dataclass(frozen=True)
class InvoiceResult:
    path: Path | None
    rendered: str
    total: float
    dry_run: bool
    warning: str | None = None


class InvoiceError(Exception):
    """Raised when an invoice cannot be generated."""


def normalize_invoice_month(month: str | None) -> str:
    """Resolve 'last', 'this', or YYYY-MM into a YYYY-MM string."""
    now = datetime.now()
    if month is None or month == "this":
        return now.strftime("%Y-%m")
    if month == "last":
        year = now.year
        month_num = now.month - 1
        if month_num == 0:
            year -= 1
            month_num = 12
        return f"{year}-{month_num:02d}"
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise ValueError("--month must be last, this, or YYYY-MM") from exc
    return month


def generate_invoice(
    client_slug: str,
    *,
    project_slug: str | None,
    period: str,
    project_dir: Path,
    force: bool = False,
    dry_run: bool = False,
    rate_override: float | None = None,
    include_ai_evidence: bool = False,
) -> InvoiceResult:
    """Render an invoice markdown file for a client and billing period."""
    config = _read_toml(project_dir / "halyard.toml")
    clients = _read_clients(project_dir)
    projects = _read_projects(project_dir)

    client = clients.get(client_slug)
    if client is None:
        raise InvoiceError(f"Client '{client_slug}' not found in clients.toml.")

    year, month = _parse_period(period)
    period_start = datetime(year, month, 1)
    period_end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

    selected_projects = [
        p
        for p in projects.values()
        if p.client_slug == client_slug and (project_slug is None or p.slug == project_slug)
    ]
    if project_slug is not None and not selected_projects:
        raise InvoiceError(f"Project '{project_slug}' not found for client '{client_slug}'.")

    closed, open_entries = _read_time_entries(project_dir / "time.timeclock")
    project_accounts = {f"{client_slug}:{p.slug}" for p in selected_projects}
    if project_slug is None and not selected_projects:
        project_accounts = {
            account for _start, _end, account in closed if account.startswith(f"{client_slug}:")
        }

    minutes_by_account: dict[str, int] = {}
    for start, end, account in closed:
        if account not in project_accounts:
            continue
        if period_start <= end < period_end:
            minutes_by_account[account] = minutes_by_account.get(account, 0) + max(
                0, int((end - start).total_seconds() // 60)
            )

    if not minutes_by_account:
        raise InvoiceError(f"No closed time entries found for {client_slug} in {period}.")

    warning = _open_warning(client_slug, open_entries, project_accounts, period_start, period_end)

    line_items: list[InvoiceLineItem] = []
    for account, minutes in sorted(minutes_by_account.items()):
        _, account_project = account.split(":", 1)
        project = projects.get(account_project)
        description = project.name if project else account_project
        rate = (
            rate_override
            or (project.hourly_rate if project else None)
            or _effective_rate(client, period_start)
        )
        hours = round(minutes / 60, 2)
        line_items.append(
            InvoiceLineItem(
                description=description,
                hours=hours,
                rate=rate,
                amount=round(hours * rate, 2),
            )
        )

    if _include_ai_cost(config):
        ai_cost = _ai_cost_for(project_dir, project_accounts, period_start, period_end)
        if ai_cost > 0:
            line_items.append(
                InvoiceLineItem(
                    description="AI usage cost",
                    hours=0.0,
                    rate=0.0,
                    amount=round(ai_cost, 2),
                )
            )

    invoice_dir = project_dir / "invoices"
    invoice_dir.mkdir(exist_ok=True)
    existing = sorted(invoice_dir.glob(f"{period}-*-{client_slug}.md"))
    counter = _invoice_counter(config)
    if existing:
        if not force:
            raise InvoiceError(f"Invoice already exists: {existing[0]}. Use --force to overwrite.")
        invoice_path = existing[0]
        invoice_number = invoice_path.stem.removesuffix(f"-{client_slug}")
    else:
        invoice_number = f"{period}-{counter + 1:03d}"
        invoice_path = invoice_dir / f"{invoice_number}-{client_slug}.md"

    # M-4: confirm the resolved invoice path stays within invoice_dir.
    # Slug validation in _read_clients already blocks traversal chars, but this
    # adds a second layer of defence for the force=True branch (existing path).
    if not invoice_path.resolve().is_relative_to(invoice_dir.resolve()):
        raise InvoiceError(f"Invoice path escapes invoice directory: {invoice_path}")

    business = config.get("business", {}) if isinstance(config.get("business"), dict) else {}
    currency = str(business.get("currency") or "USD")
    issue_date = _period_last_day(year, month)
    due_days = int(business.get("default_due_days") or 30)
    view = InvoiceView(
        invoice_number=invoice_number,
        client_slug=client_slug,
        issue_date=issue_date,
        due_date=issue_date + timedelta(days=due_days),
        currency=currency,
        line_items=line_items,
        total=round(sum(item.amount for item in line_items), 2),
    )
    rendered = _render_invoice(project_dir, business, client, view)

    if include_ai_evidence:
        from halyard.ai_plans import read_ai_plans
        from halyard.reports import parse_timeclock

        evidence_sessions = [
            s
            for s in parse_sessions(project_dir)
            if s.project in project_accounts and period_start <= s.end < period_end
        ]
        plans = read_ai_plans(project_dir)
        tc_entries = parse_timeclock(project_dir / "time.timeclock")
        period_label = datetime(year, month, 1).strftime("%B %Y")
        rendered += render_ai_evidence_appendix(evidence_sessions, plans, tc_entries, period_label)

    if dry_run:
        return InvoiceResult(
            path=None, rendered=rendered, total=view.total, dry_run=True, warning=warning
        )

    invoice_path.write_text(rendered)
    if not existing:
        _write_invoice_counter(project_dir / "halyard.toml", config, counter + 1)

    return InvoiceResult(
        path=invoice_path, rendered=rendered, total=view.total, dry_run=False, warning=warning
    )


def render_ai_evidence_appendix(
    sessions: list[AiSession],
    plans: list[AiPlan],
    tc_entries: list[tuple[datetime, datetime, str]],
    period_label: str,
) -> str:
    """Render a markdown AI usage evidence appendix for an invoice.

    Never includes prompts, code contents, or session transcripts.
    """
    if not sessions:
        return "\n\n---\n\n## AI Usage Evidence\n\nNo AI sessions recorded for this period.\n"

    from halyard.ledger import build_ledger

    period_start = min(s.start for s in sessions)
    summary = build_ledger(
        sessions, plans, tc_entries, year=period_start.year, month=period_start.month
    )

    tools = sorted({s.tool for s in sessions})
    models = sorted({s.model for s in sessions})
    total_input = sum(s.input_tokens for s in sessions)
    total_output = sum(s.output_tokens for s in sessions)
    total_cache_read = sum(s.cache_read or 0 for s in sessions)
    total_cache_write = sum(s.cache_write or 0 for s in sessions)
    total_minutes = sum(max(1, int((s.end - s.start).total_seconds() // 60)) for s in sessions)

    lines = [
        "",
        "---",
        "",
        "## AI Usage Evidence",
        "",
        f"**Period:** {period_label}  ",
        f"**Tools:** {', '.join(tools)}  ",
        f"**Models:** {', '.join(models)}  ",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Sessions | {len(sessions)} |",
        f"| Active minutes | {total_minutes} |",
        f"| Input tokens | {total_input:,} |",
        f"| Output tokens | {total_output:,} |",
    ]
    if total_cache_read or total_cache_write:
        lines.append(f"| Cache read tokens | {total_cache_read:,} |")
        lines.append(f"| Cache write tokens | {total_cache_write:,} |")

    lines += [
        "",
        "| Cost | Amount | Basis |",
        "|---|---|---|",
    ]
    if summary.total_direct_usd > 0:
        lines.append(
            f"| Direct API | ${summary.total_direct_usd:.4f} | captured from API responses |"
        )
    if summary.total_allocated_usd > 0:
        lines.append(
            f"| Allocated plans | ${summary.total_allocated_usd:.4f}"
            " | subscription plan allocation |"
        )
    lines.append(f"| **Total AI cost** | **${summary.total_usd:.4f}** | |")

    notes: list[str] = []
    if summary.total_allocated_usd > 0:
        notes.append(
            "Allocated costs are estimates derived from configured subscription plans "
            "and are not direct per-session charges."
        )
    if any(e.has_inferred_attribution for e in summary.entries):
        notes.append(
            "Some sessions have project attribution inferred from timeclock overlap "
            "and have not been explicitly confirmed."
        )

    if notes:
        lines += ["", "*" + " ".join(notes) + "*"]

    lines.append("")
    return "\n".join(lines)


def render_pdf(invoice_path: Path) -> str | None:
    """Render a PDF via typst when available. Returns a warning when skipped."""
    if shutil.which("typst") is None:
        return "typst not found — PDF skipped. Install typst to enable PDF output."
    subprocess.run(["typst", "compile", str(invoice_path)], check=True)
    _open_file(invoice_path.with_suffix(".pdf"))
    return None


def _open_file(path: Path) -> None:
    import sys as _sys

    if _sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif _sys.platform == "win32":
        import os as _os

        _os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text())


def _effective_rate(client: ClientRecord, as_of: date) -> float:
    """Return the hourly rate in effect on the given date.

    Picks the most recent rate_history entry with effective <= as_of.
    Falls back to hourly_rate when no history exists or all entries are future-dated.
    """
    applicable = [(d, r) for d, r in client.rate_history if d <= as_of]
    if not applicable:
        return client.hourly_rate
    return max(applicable, key=lambda x: x[0])[1]


def _read_clients(project_dir: Path) -> dict[str, ClientRecord]:
    data = _read_toml(project_dir / "clients.toml")
    result: dict[str, ClientRecord] = {}
    for raw in data.get("client", []):
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("slug") or "")
        if not slug or not _SLUG_RE.match(slug):
            # M-3: reject slugs with path separators, spaces, or other unsafe chars
            continue
        history: list[tuple[date, float]] = []
        for entry in raw.get("rate_history", []):
            if not isinstance(entry, dict):
                continue
            try:
                eff = date.fromisoformat(str(entry["effective"]))
                history.append((eff, float(entry["rate"])))
            except (KeyError, ValueError, TypeError):
                continue
        history.sort(key=lambda x: x[0])
        result[slug] = ClientRecord(
            slug=slug,
            name=str(raw.get("name") or slug),
            hourly_rate=float(raw.get("hourly_rate") or 0),
            email=str(raw.get("email") or ""),
            address=str(raw.get("address") or ""),
            rate_history=tuple(history),
        )
    return result


def _read_projects(project_dir: Path) -> dict[str, ProjectRecord]:
    data = _read_toml(project_dir / "projects.toml")
    result: dict[str, ProjectRecord] = {}
    for raw in data.get("project", []):
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("slug") or "")
        client_slug = str(raw.get("client_slug") or "")
        # M-3: reject slugs that contain path separators or other unsafe chars
        if not slug or not client_slug:
            continue
        if not _SLUG_RE.match(slug) or not _SLUG_RE.match(client_slug):
            continue
        rate = raw.get("hourly_rate")
        result[slug] = ProjectRecord(
            slug=slug,
            client_slug=client_slug,
            name=str(raw.get("name") or slug),
            hourly_rate=float(rate) if rate is not None else None,
        )
    return result


def _read_time_entries(
    path: Path,
) -> tuple[list[tuple[datetime, datetime, str]], list[tuple[datetime, str]]]:
    if not path.exists():
        return [], []
    closed: list[tuple[datetime, datetime, str]] = []
    open_entries: list[tuple[datetime, str]] = []
    current: tuple[datetime, str] | None = None
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        timestamp = _parse_timeclock_timestamp(parts[1], parts[2])
        if timestamp is None:
            continue
        if parts[0] == "i" and len(parts) >= 4:
            if current is not None:
                open_entries.append(current)
            current = (timestamp, parts[3])
        elif parts[0] == "o" and current is not None:
            start, account = current
            closed.append((start, timestamp, account))
            current = None
    if current is not None:
        open_entries.append(current)
    return closed, open_entries


def _parse_timeclock_timestamp(day: str, time: str) -> datetime | None:
    try:
        return datetime.strptime(f"{day} {time}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _open_warning(
    client_slug: str,
    open_entries: list[tuple[datetime, str]],
    project_accounts: set[str],
    period_start: datetime,
    period_end: datetime,
) -> str | None:
    matches = [
        (start, account)
        for start, account in open_entries
        if account in project_accounts and period_start <= start < period_end
    ]
    if not matches:
        return None
    starts = ", ".join(start.strftime("%Y-%m-%d %H:%M:%S") for start, _account in matches)
    return (
        f"Warning: {len(matches)} open time entries found for {client_slug} — "
        f"clock out before invoicing. Open starts: {starts}"
    )


def _include_ai_cost(config: dict[str, object]) -> bool:
    if config.get("include_ai_cost_in_invoice") is True:
        return True
    invoicing = config.get("invoicing")
    return isinstance(invoicing, dict) and invoicing.get("include_ai_cost_in_invoice") is True


def _ai_cost_for(
    project_dir: Path,
    project_accounts: set[str],
    period_start: datetime,
    period_end: datetime,
) -> float:
    sessions = parse_sessions(project_dir)
    return round(
        sum(
            session.cost_usd
            for session in sessions
            if session.project in project_accounts and period_start <= session.end < period_end
        ),
        2,
    )


def _invoice_counter(config: dict[str, object]) -> int:
    invoicing = config.get("invoicing")
    if isinstance(invoicing, dict):
        value = invoicing.get("counter", invoicing.get("invoice_counter", 0))
    else:
        value = config.get("invoice_counter", 0)
    return int(value or 0)


def _write_invoice_counter(path: Path, config: dict[str, object], counter: int) -> None:
    invoicing = config.setdefault("invoicing", {})
    if not isinstance(invoicing, dict):
        invoicing = {}
        config["invoicing"] = invoicing
    invoicing["counter"] = counter
    path.write_text(tomli_w.dumps(config))


def _render_invoice(
    project_dir: Path,
    business: dict[str, object],
    client: ClientRecord,
    invoice: InvoiceView,
) -> str:
    override = project_dir / "templates" / "invoice.md.j2"
    if override.exists():
        template_dir = override.parent
        template_name = override.name
    else:
        template_dir = Path(__file__).resolve().parents[2] / "templates"
        template_name = "invoice.md.j2"

    # L-1: autoescape=False is intentional — output is Markdown, not HTML.
    # If adding HTML templates in future, create a separate Environment with autoescape=True.
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=False)
    template = env.get_template(template_name)
    return template.render(
        business=business,
        client=client,
        invoice=invoice,
    )


def _parse_period(period: str) -> tuple[int, int]:
    try:
        parsed = datetime.strptime(period, "%Y-%m")
    except ValueError as exc:
        raise InvoiceError("--period must be YYYY-MM (e.g. 2026-05).") from exc
    return parsed.year, parsed.month


def _period_last_day(year: int, month: int) -> date:
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return next_month - timedelta(days=1)
