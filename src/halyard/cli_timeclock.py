"""halyard timeclock — inspect and repair the human time timeclock."""

from __future__ import annotations

import difflib
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console

console = Console()

app = typer.Typer(name="timeclock", help="Inspect and repair the human time timeclock.")


def _resolve_timeclock(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    from halyard.ai_log import find_project_dir
    from halyard.hub import find_hub

    project_dir = find_project_dir() or find_hub()
    if project_dir is None:
        console.print("[bold red]Error:[/] No Halyard project found.")
        raise typer.Exit(code=1)
    return project_dir / "time.timeclock"


def _summary(path: Path) -> tuple[int, int, float, float, int]:
    """Return (dropped_opens, orphan_closes, current_h, repaired_h, windows)."""
    from halyard.reports import timeclock_anomalies
    from halyard.timeclock_repair import counted_minutes, reconstruct_timeclock

    lines = path.read_text(encoding="utf-8").splitlines()
    dropped, orphans = timeclock_anomalies(path)
    repaired = reconstruct_timeclock(lines)
    windows = sum(1 for line in repaired if line.lstrip().startswith("o "))
    return (
        dropped,
        orphans,
        counted_minutes(lines) / 60,
        counted_minutes(repaired) / 60,
        windows,
    )


@app.command(name="check")
def timeclock_check(
    timeclock: str | None = typer.Option(None, "--timeclock", help="Path to time.timeclock."),
) -> None:
    """Report structural anomalies and current vs. reconstructed counted hours."""
    path = _resolve_timeclock(timeclock)
    if not path.exists():
        console.print(f"[yellow]No timeclock at {path}.[/]")
        raise typer.Exit()

    dropped, orphans, current_h, repaired_h, windows = _summary(path)
    console.print(f"\n[bold]Timeclock check[/] — {path}\n")
    console.print(f"  dropped opens (unclosed clock-ins): [bold]{dropped}[/]")
    console.print(f"  orphan closes (no matching clock-in): [bold]{orphans}[/]")
    console.print(f"  counted now:        [bold]{current_h:7.1f}[/] h")
    console.print(f"  after reconstruct:  [bold]{repaired_h:7.1f}[/] h  ({windows} windows)")
    if dropped or orphans:
        console.print("\n[dim]Run [bold]halyard timeclock repair[/] to preview a fix.[/]")
    else:
        console.print("\n[green]✓[/] No structural anomalies.")


def _reconcile_from_sessions(path: Path, lines: list[str]) -> tuple[list[str], float, float]:
    """Propose coverage for session spans the timeclock is missing."""
    from halyard.ai_log import parse_sessions
    from halyard.timeclock_repair import reconcile_from_sessions

    project_dir = path.parent
    spans = [
        (s.start, s.end, s.project or "unattributed")
        for s in parse_sessions(project_dir)
        if s.end and s.end > s.start
    ]
    return reconcile_from_sessions(lines, spans)


def _emit(path: Path, original: list[str], repaired: list[str], apply: bool) -> None:
    """Print a unified diff, or back up and write. Shared by both repair modes.

    Kept common so `--from-sessions` cannot drift from the safety contract
    the original repair established: dry-run by default, timestamped backup
    before any write, atomic replace.
    """
    if not apply:
        diff = difflib.unified_diff(
            original, repaired, fromfile=str(path), tofile=f"{path} (repaired)", lineterm=""
        )
        for line in diff:
            if line.startswith("+") and not line.startswith("+++"):
                console.print(f"[green]{line}[/]")
            elif line.startswith("-") and not line.startswith("---"):
                console.print(f"[red]{line}[/]")
            elif line.startswith("@@"):
                console.print(f"[cyan]{line}[/]")
            else:
                console.print(f"[dim]{line}[/]")
        return

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup)

    tmp = path.with_name(f"{path.name}.tmp")
    text = "\n".join(repaired) + "\n"
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    from halyard.ai_log import atomic_replace

    atomic_replace(tmp, path)
    console.print(f"[green]✓[/] Repaired {path}")
    console.print(f"  backup: {backup}")


@app.command(name="repair")
def timeclock_repair_cmd(
    timeclock: str | None = typer.Option(None, "--timeclock", help="Path to time.timeclock."),
    apply: bool = typer.Option(
        False, "--apply", help="Write the fix (after a timestamped backup)."
    ),
    from_sessions: bool = typer.Option(
        False,
        "--from-sessions",
        help="Recover time from ai-sessions.log instead of rebuilding windows.",
    ),
) -> None:
    """Rebuild clean i/o windows from corrupted auto entries.

    Dry-run by default: prints a unified diff and summary. ``--apply`` backs up
    the file then writes the reconstruction.

    ``--from-sessions`` reconciles against the session ledger instead: any span
    a recorded session proves, but the timeclock does not cover, is appended.
    This recovers days lost before v5.26, when the idle policy closed a window
    mid-turn and nothing could reopen it.
    """
    from halyard.timeclock_repair import reconstruct_timeclock

    path = _resolve_timeclock(timeclock)
    if not path.exists():
        console.print(f"[yellow]No timeclock at {path}.[/]")
        raise typer.Exit()

    original = path.read_text(encoding="utf-8").splitlines()
    if from_sessions:
        repaired, recovered_min, skipped_min = _reconcile_from_sessions(path, original)
        if skipped_min:
            console.print(
                f"[dim]Skipped {skipped_min / 60:.1f} h from sessions longer than 12 h — "
                "a long-lived imported session is not evidence of continuous work.[/]"
            )
        if repaired == original:
            console.print("[green]✓[/] Timeclock already covers every recorded session.")
            raise typer.Exit()
        _emit(path, original, repaired, apply)
        if apply:
            console.print(f"  recovered [bold]{recovered_min / 60:.1f}[/] h from the session log.")
        else:
            console.print(
                f"\n[bold]Summary:[/] {recovered_min / 60:.1f} h of recorded session time "
                "is missing from the timeclock."
            )
            console.print("\n[yellow]Dry run.[/] Re-run with [bold]--apply[/] to write the fix.")
        return

    repaired = reconstruct_timeclock(original)
    dropped, orphans, current_h, repaired_h, windows = _summary(path)

    if repaired == original:
        console.print("[green]✓[/] Timeclock is already clean — nothing to repair.")
        raise typer.Exit()

    if not apply:
        diff = difflib.unified_diff(
            original, repaired, fromfile=str(path), tofile=f"{path} (repaired)", lineterm=""
        )
        for line in diff:
            if line.startswith("+") and not line.startswith("+++"):
                console.print(f"[green]{line}[/]")
            elif line.startswith("-") and not line.startswith("---"):
                console.print(f"[red]{line}[/]")
            elif line.startswith("@@"):
                console.print(f"[cyan]{line}[/]")
            else:
                console.print(f"[dim]{line}[/]")
        console.print(
            f"\n[bold]Summary:[/] {dropped} dropped opens, {orphans} orphan closes — "
            f"{current_h:.1f}h → {repaired_h:.1f}h across {windows} windows."
        )
        console.print("\n[yellow]Dry run.[/] Re-run with [bold]--apply[/] to write the fix.")
        return

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup)

    tmp = path.with_name(f"{path.name}.tmp")
    text = "\n".join(repaired) + "\n"
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    from halyard.ai_log import atomic_replace

    atomic_replace(tmp, path)

    console.print(f"[green]✓[/] Repaired {path}")
    console.print(f"  backup: {backup}")
    console.print(
        f"  {dropped} dropped opens fixed — {current_h:.1f}h → {repaired_h:.1f}h "
        f"across {windows} windows."
    )
