"""Halyard Hub — central telemetry receiver and write-broker."""

from __future__ import annotations

import contextlib
import hmac
import json
import math
import os
import socket
import socketserver
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from halyard.ai_log import (
    _FIELDS,
    AiSession,
    FieldKind,
    _parse_line_result,
    _to_naive_local,
    append_session,
)
from halyard.auto_timer import INACTIVITY_MINUTES
from halyard.collectors.vscode_otel import _SessionAcc, accumulate_traces, finalize

HUB_HOST = "127.0.0.1"
HUB_PORT = 4318
_TS_FMT = "%Y-%m-%d %H:%M:%S"

# Configuration
_IDLE_TTL = timedelta(minutes=10)
# Cap the number of in-flight OTel sessions accumulated before TTL flush so a
# local client spamming distinct session ids cannot grow memory without bound.
# Oldest-by-last-update entries are evicted; a real editor has very few live.
_MAX_OTEL_SESSIONS = 1000
_MAX_SSE_CONNECTIONS = 32  # v5.19/B4: bound SSE worker threads
# v5.19/B4: AF_UNIX peer-cred is available only on POSIX (not Windows TCP).
_AF_UNIX_AVAILABLE = hasattr(socket, "AF_UNIX")


def hub_socket_path(port: int) -> Path:
    """Path to the Hub's AF_UNIX ingest socket for a given port.

    Port-keyed so a test hub (e.g. :54318) and a real hub (:4318) use distinct
    sockets and never clobber each other; the client derives the same path from
    its configured port.
    """
    return Path.home() / ".halyard" / f"hub-{port}.sock"


if _AF_UNIX_AVAILABLE:

    class _ThreadingUnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        """A threaded HTTP server over an AF_UNIX socket.

        ``UnixStreamServer`` (unlike ``HTTPServer``) does not populate
        ``server_name``/``server_port`` and would choke on the AF_UNIX
        ``getsockname`` (a path, not ``(host, port)``); set sane stand-ins so
        the ``BaseHTTPRequestHandler`` machinery is happy.
        """

        daemon_threads = True

        def server_bind(self) -> None:
            socketserver.UnixStreamServer.server_bind(self)
            self.server_name = "localhost"
            self.server_port = 0


# Single source of truth for the auto-timer idle policy lives in auto_timer.
_AUTO_INACTIVITY = timedelta(minutes=INACTIVITY_MINUTES)
_MAX_BODY = 25 * 1024 * 1024  # 25 MB
# Cap per-listener SSE backlog so a stalled client cannot grow memory without
# bound; dropping the oldest events is harmless (the dashboard full-refetches).
_SSE_QUEUE_MAX = 2000
_OK_BODY = b"{}"
_REQUIRED_INGEST_FIELDS = {
    "start",
    "end",
    "tool",
    "model",
    "input_tokens",
    "output_tokens",
    "cost_usd",
}
_OPTIONAL_INGEST_FIELDS = {spec.key for spec in _FIELDS}
_INGEST_FIELD_SPECS = {spec.key: spec for spec in _FIELDS}


class IngestPayload(BaseModel):
    """Validated `/v1/ingest` payload for polyglot emitters."""

    model_config = ConfigDict(extra="forbid")

    line: str | None = None
    fields: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _exactly_one_shape(self) -> Self:
        has_line = self.line is not None
        has_fields = self.fields is not None
        if has_line == has_fields:
            raise ValueError("provide exactly one of line or fields")
        return self

    def to_session(self) -> AiSession:
        if self.line is not None:
            session, error = _parse_line_result(self.line)
            if error is not None or session is None:
                raise ValueError(error or "invalid session line")
            return session
        return _session_from_fields(self.fields or {})


def _session_from_fields(fields: dict[str, Any]) -> AiSession:
    missing = sorted(_REQUIRED_INGEST_FIELDS - fields.keys())
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(missing)}")

    allowed = _REQUIRED_INGEST_FIELDS | _OPTIONAL_INGEST_FIELDS
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise ValueError(f"unknown field(s): {', '.join(unknown)}")

    session = AiSession(
        start=_parse_ingest_datetime(fields["start"], "start"),
        end=_parse_ingest_datetime(fields["end"], "end"),
        tool=_parse_ingest_string(fields["tool"], "tool"),
        model=_parse_ingest_string(fields["model"], "model"),
        input_tokens=_parse_ingest_int(fields["input_tokens"], "input_tokens"),
        output_tokens=_parse_ingest_int(fields["output_tokens"], "output_tokens"),
        cost_usd=_parse_ingest_float(fields["cost_usd"], "cost_usd"),
    )

    for key, value in fields.items():
        if key in _REQUIRED_INGEST_FIELDS:
            continue
        spec = _INGEST_FIELD_SPECS[key]
        setattr(session, spec.attr, _parse_optional_ingest_value(value, key, spec.kind))

    return session


def _parse_ingest_datetime(value: Any, key: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be an ISO timestamp string")
    try:
        return _to_naive_local(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as exc:
        raise ValueError(f"{key} must be an ISO timestamp string") from exc


def _parse_ingest_string(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _parse_ingest_int(value: Any, key: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    if value < 0:
        raise ValueError(f"{key} must be non-negative")
    return value


def _parse_ingest_float(value: Any, key: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{key} must be a number")
    parsed = float(value)
    # v5.16/B1 (Hub ingest path): the parse-side guard in ai_log only protects
    # the file parser; the Hub's /v1/ingest had its own float path that still
    # admitted inf/nan (inf later raises decimal.InvalidOperation, nan poisons
    # totals to NaN). With the unauthenticated endpoint (B4), a hostile local
    # webpage could poison or crash financial reports. Reject non-finite here.
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{key} must be a finite non-negative number")
    return parsed


def _parse_optional_ingest_value(value: Any, key: str, kind: FieldKind) -> Any:
    match kind:
        case FieldKind.SAFE_FIELD | FieldKind.BILLING | FieldKind.FREE_TEXT | FieldKind.BREAKDOWN:
            return _parse_ingest_string(value, key)
        case FieldKind.INT:
            return _parse_ingest_int(value, key)
        case FieldKind.FLOAT_4:
            return _parse_ingest_float(value, key)
        case FieldKind.BOOL_LOWER | FieldKind.TOKENS_AVAILABLE:
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be a boolean")
            return value
        case FieldKind.TAGS:
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item for item in value
            ):
                raise ValueError(f"{key} must be a list of non-empty strings")
            return value
    raise ValueError(f"{key} has unsupported field kind")


def _validation_message(exc: ValidationError) -> str:
    first = exc.errors()[0]
    loc = ".".join(str(part) for part in first.get("loc", ()) if part)
    msg = str(first.get("msg", "invalid payload"))
    return f"{loc}: {msg}" if loc else msg


@dataclass
class ActiveState:
    project: str | None = None
    started_at: datetime | None = None
    timeclock: Path | None = None
    auto_project: str | None = None
    auto_started_at: datetime | None = None
    auto_timeclock: Path | None = None
    last_presence: datetime | None = None


class EventEmitter:
    """Small in-process pub/sub fanout for Hub SSE listeners."""

    def __init__(self) -> None:
        self._listeners: list[deque[str]] = []
        self._lock = threading.Lock()

    def subscribe(self) -> deque[str]:
        queue: deque[str] = deque(maxlen=_SSE_QUEUE_MAX)
        with self._lock:
            self._listeners.append(queue)
        return queue

    def unsubscribe(self, queue: deque[str]) -> None:
        with self._lock, contextlib.suppress(ValueError):
            self._listeners.remove(queue)

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        payload = json.dumps({"type": event_type, "data": data})
        event_str = f"data: {payload}\n\n"
        with self._lock:
            for queue in self._listeners:
                queue.append(event_str)

    def drain(self, queue: deque[str]) -> list[str]:
        """Atomically remove and return all pending events for one listener.

        Pops under the same lock that ``emit`` appends under, so producers and
        the consuming SSE thread never touch the deque concurrently.
        """
        with self._lock:
            events = list(queue)
            queue.clear()
        return events


def _parse_optional_iso(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be an ISO string")
    return _to_naive_local(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _parse_timer_started(value: str | None) -> datetime | None:
    if not value:
        return None
    with contextlib.suppress(ValueError):
        return datetime.strptime(value, _TS_FMT)
    return _parse_optional_iso(value)


class _RejectedTargetDirError(Exception):
    """The client supplied a project_dir/timeclock that is not a registered
    Halyard project. v5.19/B5-followup: this used to silently fall back to the
    hub's own project, so a token-holding client could redirect a timer write
    by passing any path. We now raise so the handler responds 400 instead.
    """


def _target_project_dir(data: dict[str, Any]) -> Path | None:
    """Resolve a client-supplied target dir, constrained to registered projects.

    v5.19/B5: previously any existing directory was accepted, so a
    token-holding client could create ``time.timeclock`` (and inject fields)
    in an arbitrary location. Only honour a dir that is an already-registered
    Halyard project (exists + has ``halyard.toml``).

    Return value semantics:
      - ``None`` — the client supplied no target at all; caller may fall back
        to the hub's own project dir.
      - registered :class:`Path` — the validated target.
      - raises :class:`_RejectedTargetDirError` — the client supplied a target that
        failed validation. Callers MUST surface this as 400/403 rather than
        silently rewriting the hub's ledger.
    """
    raw = data.get("project_dir")
    candidate: Path | None = None
    if isinstance(raw, str) and raw:
        candidate = Path(raw)
    else:
        raw_timeclock = data.get("timeclock")
        if isinstance(raw_timeclock, str) and raw_timeclock:
            candidate = Path(raw_timeclock).parent
    if candidate is None:
        return None
    from halyard.registry import read_registry

    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise _RejectedTargetDirError("project_dir not a registered project") from exc
    if any(resolved == p.resolve() for p in read_registry()):
        return resolved
    raise _RejectedTargetDirError("project_dir not a registered project")


class HubServer:
    """A localhost Hub for receiving AI sessions and OTLP telemetry."""

    def __init__(self, project_dir: Path | None = None, *, port: int = HUB_PORT) -> None:
        self.project_dir = project_dir
        self.port = port
        self._otel_acc: dict[str, _SessionAcc] = {}
        self._write_queue: deque[AiSession] = deque()
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._unix_server: socketserver.BaseServer | None = None
        self._stop = threading.Event()

        # v4.3: Real-time eventing
        self._events = EventEmitter()
        # v5.19/B4: bound concurrent SSE connections — each holds a worker
        # thread in a keep-alive loop, so an unbounded count is a thread-
        # exhaustion DoS.
        self._sse_active = 0

        # v4.0: Coalesce cache syncs so a burst of writes to one dir does not
        # spawn one full-log re-sync thread per write.
        self._sync_lock = threading.Lock()
        self._syncing: set[str] = set()
        self._resync: set[str] = set()

        # v4.2: Active state tracking
        self.state = ActiveState()
        self._load_state()

    def _sse_acquire(self) -> bool:
        with self._lock:
            if self._sse_active >= _MAX_SSE_CONNECTIONS:
                return False
            self._sse_active += 1
            return True

    def _sse_release(self) -> None:
        with self._lock:
            self._sse_active = max(0, self._sse_active - 1)

    def _load_state(self) -> None:
        """Load state from ~/.halyard/active if present."""
        from halyard.reports import read_active_timer

        active = read_active_timer(prefer_hub=False)
        if active:
            self.state.project = active.slug
            self.state.timeclock = active.timeclock
            if active.started:
                with contextlib.suppress(ValueError):
                    self.state.started_at = datetime.strptime(active.started, _TS_FMT)
        # Recover auto-presence the prior process left open. Without this every
        # restart orphans an open `i` (in-memory auto_project resets to None),
        # producing the `i i i … o` under-billing corruption.
        self._reconcile_auto_presence()

    def _reconcile_auto_presence(self, *, now: datetime | None = None) -> None:
        """Resume or close-stale the auto-presence window persisted on disk.

        Runs in ``__init__`` (via ``_load_state``) before any thread serves
        traffic, so no lock is needed. A recent window resumes in memory (the
        original ``i`` is already in the timeclock); a stale one is closed with
        the ``o`` it never got.
        """
        from halyard.ai_log import locked_file
        from halyard.auto_timer import clear_presence, read_presence

        state = read_presence()
        if not state:
            return

        project = state.get("project", "")
        tc_str = state.get("timeclock", "")
        last_str = state.get("last_activity") or state.get("started", "")
        started_str = state.get("started", "") or last_str
        if not (project and tc_str and last_str):
            clear_presence()
            return
        try:
            last = datetime.strptime(last_str, _TS_FMT)
            started = datetime.strptime(started_str, _TS_FMT)
        except ValueError:
            clear_presence()
            return

        clock = now or datetime.now()
        timeclock = Path(tc_str)
        if clock - last >= _AUTO_INACTIVITY:
            # Stale: close the orphaned open at its last known activity.
            if timeclock.exists():
                with locked_file(timeclock, "a") as f:
                    f.write(f"o {last.strftime(_TS_FMT)}\n")
            clear_presence()
            return
        # Recent: resume the window without writing a new clock-in.
        self.state.auto_project = project
        self.state.auto_started_at = started
        self.state.auto_timeclock = timeclock
        self.state.last_presence = last

    def _persist_auto_presence_locked(self) -> None:
        """Mirror in-memory auto-presence to ~/.halyard/auto-timer.

        Caller must hold ``self._lock``. Clears the file when no window is open.
        """
        from halyard.auto_timer import clear_presence, write_presence

        if self.state.auto_project is None:
            clear_presence()
            return
        if self.state.auto_timeclock is None or self.state.auto_started_at is None:
            return
        write_presence(
            self.state.auto_project,
            self.state.auto_timeclock,
            self.state.auto_started_at,
            self.state.last_presence or self.state.auto_started_at,
        )

    def start(self) -> None:
        """Start the hub server and background workers."""
        self._server = ThreadingHTTPServer((HUB_HOST, self.port), self._handler())
        # Reflect the actually-bound port (e.g. when constructed with port=0).
        self.port = self._server.server_port

        # Serving thread
        threading.Thread(
            target=self._server.serve_forever, name="halyard-hub-server", daemon=True
        ).start()

        # v5.19/B4: AF_UNIX ingest listener for same-host emitters. Auth is by
        # OS peer-credential (no token), and a co-located *other* user's UID
        # won't match ours — a guarantee TCP can't give. Best-effort: a failure
        # here never blocks the TCP server.
        self._start_unix_listener()

        # Flush/Worker thread
        threading.Thread(target=self._worker_loop, name="halyard-hub-worker", daemon=True).start()

    def _start_unix_listener(self) -> None:
        if not _AF_UNIX_AVAILABLE:
            return
        sock_path = hub_socket_path(self.port)
        try:
            sock_path.parent.mkdir(parents=True, exist_ok=True)
            with contextlib.suppress(OSError):
                sock_path.parent.chmod(0o700)
            # Remove a stale socket from a crashed run (a live one would still
            # be connectable, but the bind below would EADDRINUSE — we own this
            # path, so unlinking is safe).
            with contextlib.suppress(FileNotFoundError):
                sock_path.unlink()
            server = _ThreadingUnixHTTPServer(str(sock_path), self._handler())
            os.chmod(sock_path, 0o600)
        except OSError:
            self._unix_server = None
            return
        self._unix_server = server
        threading.Thread(target=server.serve_forever, name="halyard-hub-unix", daemon=True).start()

    def stop(self) -> None:
        """Graceful shutdown: flush everything and stop serving."""
        self._stop.set()
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._unix_server is not None:
            self._unix_server.shutdown()
            self._unix_server.server_close()
            with contextlib.suppress(OSError):
                hub_socket_path(self.port).unlink()
        self._flush_all()

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        """v4.3: Dispatch a real-time event to all SSE listeners."""
        self._events.emit(event_type, data)

    def ingest_session(self, session: AiSession) -> None:
        """Queue a validated AiSession for asynchronous logging."""
        # v5.0: Check for collisions on ingestion
        self._check_for_collisions(session)

        with self._lock:
            self._write_queue.append(session)

    def _check_for_collisions(self, session: AiSession) -> None:
        """v5.0: Identify and emit collision events."""
        if not session.remote or not session.branch:
            return

        from halyard.collisions import find_collisions
        from halyard.db import get_recent_branch_activity

        # Query cache for recent activity on this branch
        history = get_recent_branch_activity(session.remote, session.branch)
        collisions = find_collisions(session, history)

        if collisions:
            from halyard.attribution import canonical_project, load_project_aliases

            self.emit(
                "collision_detected",
                {
                    # canonicalize so the live banner matches the persistent
                    # panels (which read via parse_sessions) — v5.9
                    "project": canonical_project(
                        session.project, load_project_aliases(self.project_dir)
                    ),
                    "branch": session.branch,
                    "remote": session.remote,
                    "collision_count": len(collisions),
                    "latest_collision_tool": collisions[0].tool,
                },
            )

    def ingest_traces(self, payload: Any) -> None:
        """Queue OTLP traces for mapping and eventual logging."""
        with self._lock:
            accumulate_traces(self._otel_acc, payload)
            evicted = self._evict_excess_otel()

        # v5.18/B4-evict: finalize-and-write evicted accumulators outside the
        # lock (mirroring flush_stale), instead of dropping in-flight sessions.
        for acc in evicted:
            session = finalize(acc)
            if session:
                self._write_to_log(session)

    def _evict_excess_otel(self) -> list[_SessionAcc]:
        """Bound ``_otel_acc`` size by removing the least-recently-updated
        sessions. Must be called holding ``self._lock``.

        Returns the removed accumulators so the caller can finalize-and-write
        them: a bare ``del`` here silently dropped genuine in-flight sessions
        before they reached the ledger (v5.18/B4-evict data loss).
        """
        excess = len(self._otel_acc) - _MAX_OTEL_SESSIONS
        if excess <= 0:
            return []
        oldest = sorted(self._otel_acc.items(), key=lambda kv: kv[1].last_update)
        return [self._otel_acc.pop(sid) for sid, _acc in oldest[:excess]]

    def flush_stale(self, *, force: bool = False) -> int:
        """Finalize and append sessions idle past the TTL (or all if force)."""
        now = datetime.now()
        ready = []
        with self._lock:
            for sid, acc in list(self._otel_acc.items()):
                if force or (now - acc.last_update) > _IDLE_TTL:
                    ready.append(self._otel_acc.pop(sid))

        count = 0
        for acc in ready:
            session = finalize(acc)
            if session:
                self._write_to_log(session)
                count += 1
        return count

    def _worker_loop(self) -> None:
        """Process the write queue and periodically flush idle OTel sessions."""
        while not self._stop.is_set():
            self._worker_tick()
            time.sleep(1)

    def _worker_tick(self) -> None:
        """One unit of background work, isolated so an unexpected error in any
        step cannot kill the daemon thread and silently halt all writes."""
        try:
            # 1. Process explicit AiSession writes
            self._process_write_queue()
            # 2. Flush idle OTel sessions
            self.flush_stale()
            # 3. Close stale auto-timer windows
            self._close_stale_presence()
        except Exception as exc:  # never let one bad session stop the worker
            from halyard.ai_log import log_diagnostic

            log_diagnostic(f"hub_server: worker tick failed: {exc}")

    def _process_write_queue(self) -> None:
        sessions_to_write = []
        with self._lock:
            while self._write_queue:
                sessions_to_write.append(self._write_queue.popleft())

        # Per-item guard: a single failing write (e.g. transient IO error) must
        # not drop the rest of the already-dequeued batch (v5.9).
        for session in sessions_to_write:
            try:
                self._write_to_log(session)
            except Exception as exc:
                from halyard.ai_log import log_diagnostic

                log_diagnostic(f"hub_server: session write failed: {exc}")

    def _flush_all(self) -> None:
        self._process_write_queue()
        self.flush_stale(force=True)

    def _write_to_log(self, session: AiSession) -> None:
        from halyard.ai_log import find_project_dir, write_unattributed_session
        from halyard.hub import find_hub

        target = self.project_dir or find_project_dir() or find_hub()
        if target:
            append_session(target, session, direct=True)
            # v4.0: Trigger background cache sync
            self._trigger_cache_sync(target)
        else:
            write_unattributed_session(session)

        # v4.3: Notify reactive dashboard
        self.emit(
            "session_ingested",
            {"project": session.project, "tool": session.tool, "cost": session.cost_usd},
        )

    def _trigger_cache_sync(self, project_dir: Path) -> None:
        """Asynchronously update the SQLite read-model for the written dir.

        Coalesces concurrent triggers for the same dir: if a sync is already
        in flight, the dir is flagged for one re-run instead of spawning a
        second thread, so a write burst collapses to at most one extra sync.
        """
        key = str(project_dir)
        with self._sync_lock:
            if key in self._syncing:
                self._resync.add(key)
                return
            self._syncing.add(key)
        threading.Thread(target=self._sync_worker, args=(project_dir, key), daemon=True).start()

    def _sync_worker(self, project_dir: Path, key: str) -> None:
        from halyard.db import sync_source

        while True:
            with contextlib.suppress(Exception):
                sync_source(project_dir)
            with self._sync_lock:
                if key in self._resync:
                    self._resync.discard(key)
                    continue
                self._syncing.discard(key)
                return

    def _state_payload(self) -> dict[str, Any]:
        with self._lock:
            return {
                "project": self.state.project,
                "started_at": (
                    self.state.started_at.isoformat() if self.state.started_at else None
                ),
                "timeclock": str(self.state.timeclock) if self.state.timeclock else None,
                "last_presence": (
                    self.state.last_presence.isoformat() if self.state.last_presence else None
                ),
                "auto_project": self.state.auto_project,
                "auto_started_at": (
                    self.state.auto_started_at.isoformat() if self.state.auto_started_at else None
                ),
                "auto_timeclock": (
                    str(self.state.auto_timeclock) if self.state.auto_timeclock else None
                ),
            }

    def _record_presence_activity(
        self,
        project: str,
        timeclock: Path,
        *,
        now: datetime | None = None,
    ) -> None:
        from halyard.ai_log import _safe_field, locked_file

        with self._lock:
            manual_active = self.state.project is not None
        if manual_active or not timeclock.exists():
            return

        project = _safe_field(project)
        clock = now or datetime.now()
        ts = clock.strftime(_TS_FMT)

        with self._lock:
            if self.state.auto_project is None:
                with locked_file(timeclock, "a") as f:
                    f.write(f"i {ts} {project}  ;auto\n")
                self.state.auto_project = project
                self.state.auto_started_at = clock
                self.state.auto_timeclock = timeclock
            self.state.last_presence = clock
            self._persist_auto_presence_locked()

    def _update_presence(self, *, now: datetime | None = None) -> None:
        with self._lock:
            if self.state.auto_project is not None:
                self.state.last_presence = now or datetime.now()
                self._persist_auto_presence_locked()

    def _close_presence_now(self, *, now: datetime | None = None) -> bool:
        from halyard.ai_log import locked_file

        with self._lock:
            if self.state.auto_project is None:
                return False
            timeclock = self.state.auto_timeclock
            stamp = now or datetime.now()
            self.state.auto_project = None
            self.state.auto_started_at = None
            self.state.auto_timeclock = None
            self.state.last_presence = None
            self._persist_auto_presence_locked()

        if timeclock and timeclock.exists():
            with locked_file(timeclock, "a") as f:
                f.write(f"o {stamp.strftime(_TS_FMT)}\n")
        return True

    def _close_stale_presence(self, *, now: datetime | None = None) -> bool:
        clock = now or datetime.now()
        with self._lock:
            last = self.state.last_presence
        if last is None or (clock - last) < _AUTO_INACTIVITY:
            return False
        return self._close_presence_now(now=last)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        hub = self

        class _Handler(BaseHTTPRequestHandler):
            # Bound per-request socket reads so a slow/half-open client cannot
            # hold a ThreadingHTTPServer worker thread indefinitely (slowloris).
            timeout = 10

            def do_GET(self) -> None:
                if not self._host_ok():
                    self._respond_error(HTTPStatus.BAD_REQUEST, "invalid Host header")
                    return
                path_parts = self.path.split("?", 1)
                path = path_parts[0].rstrip("/")
                params = {}
                if len(path_parts) > 1:
                    from urllib.parse import parse_qs

                    params = {k: v[0] for k, v in parse_qs(path_parts[1]).items()}

                if path == "/v1/events":
                    self._handle_sse()
                elif path == "/v1/collisions":
                    self._handle_collision_check(params)
                elif path == "/v1/state":
                    self._handle_get_state()
                elif path == "/health":
                    self._respond_json(HTTPStatus.OK, {"status": "ok"})
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)

            def _handle_get_state(self) -> None:
                """v4.2: Return the current active project and timer."""
                # v5.19/B4: the state payload leaks home-dir/project paths — auth it.
                if not self._authorized():
                    self._respond_error(HTTPStatus.UNAUTHORIZED, "missing or invalid token")
                    return
                self._respond_json(HTTPStatus.OK, hub._state_payload())

            def _handle_collision_check(self, params: dict[str, str]) -> None:
                """v5.0: Check for collisions without ingesting a session."""
                if not self._authorized():
                    self._respond_error(HTTPStatus.UNAUTHORIZED, "missing or invalid token")
                    return
                remote = params.get("remote")
                branch = params.get("branch")
                if not remote or not branch:
                    self.send_error(HTTPStatus.BAD_REQUEST, "missing remote or branch")
                    return

                from halyard.ai_log import AiSession
                from halyard.collisions import find_collisions
                from halyard.db import get_recent_branch_activity

                # Create a synthetic session to check against history
                now = datetime.now()
                probe = AiSession(
                    start=now,
                    end=now,
                    tool="probe",
                    model="probe",
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    remote=remote,
                    branch=branch,
                )

                history = get_recent_branch_activity(remote, branch)
                collisions = find_collisions(probe, history)

                resp_data = {
                    "collisions": [
                        {
                            "tool": c.tool,
                            "ended_at": c.end.isoformat(),
                            "seconds_ago": int((now - c.end).total_seconds()),
                        }
                        for c in collisions
                    ]
                }
                self._respond_json(HTTPStatus.OK, resp_data)

            def do_POST(self) -> None:
                if not self._host_ok():
                    self._respond_error(HTTPStatus.BAD_REQUEST, "invalid Host header")
                    return
                if not self._csrf_ok():
                    self._respond_error(
                        HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "expected Content-Type application/json"
                    )
                    return
                path = self.path.split("?", 1)[0].rstrip("/")

                # OTLP Ingestion
                if path == "/v1/traces":
                    self._handle_otlp()
                # Direct Ingestion
                elif path == "/v1/ingest":
                    self._handle_ingest()
                # Timer Management
                elif path == "/v1/state/timer":
                    self._handle_timer_action()
                elif path == "/v1/state/presence":
                    self._handle_presence_action()
                else:
                    self.send_error(HTTPStatus.NOT_FOUND, "unknown hub path")

            def _handle_timer_action(self) -> None:
                """v4.2: Start or stop the timer."""
                if not self._authorized():
                    self._respond_error(HTTPStatus.UNAUTHORIZED, "missing or invalid token")
                    return
                body = self._read_body()
                if body is None:
                    return
                try:
                    data = json.loads(body)
                    action = data.get("action")
                    # v5.19/B5: sanitize the project slug before it is written
                    # into the timeclock / global state (the presence path
                    # already does this) — a raw value could inject newlines or
                    # extra fields into the append-only records.
                    from halyard.ai_log import _safe_field

                    project = data.get("project")
                    if isinstance(project, str):
                        project = _safe_field(project)

                    from halyard.ai_log import find_project_dir
                    from halyard.hub import find_hub
                    from halyard.orchestration import TimerAlreadyRunning, start_timer, stop_timer

                    # v5.19/B5-followup: a rejected client-supplied target is a
                    # 400, not a silent fall-back to the hub's ledger.
                    try:
                        client_target = _target_project_dir(data)
                    except _RejectedTargetDirError as exc:
                        self._respond_error(HTTPStatus.BAD_REQUEST, str(exc))
                        return
                    target_dir = (
                        client_target or hub.project_dir or find_project_dir() or find_hub()
                    )
                    if not target_dir:
                        self._respond_error(HTTPStatus.INTERNAL_SERVER_ERROR, "no project dir")
                        return

                    if action == "start":
                        if not project:
                            self._respond_error(HTTPStatus.BAD_REQUEST, "missing project")
                            return
                        try:
                            timer = start_timer(target_dir, project, direct=True)
                        except TimerAlreadyRunning as exc:
                            self._respond_json(
                                HTTPStatus.CONFLICT,
                                {"error": "already running", "project": exc.slug},
                            )
                            return
                        with hub._lock:
                            hub.state.project = project
                            hub.state.started_at = _parse_timer_started(timer.started)
                            hub.state.timeclock = timer.timeclock
                        hub.emit("timer_started", {"project": project})
                        hub.emit("timer_updated", hub._state_payload())
                    elif action == "stop":
                        result = stop_timer(target_dir, direct=True)
                        with hub._lock:
                            hub.state.project = None
                            hub.state.started_at = None
                            hub.state.timeclock = None
                        hub.emit("timer_stopped", {})
                        hub.emit("timer_updated", hub._state_payload())
                        self._respond_json(
                            HTTPStatus.OK,
                            {
                                "was_running": result.was_running,
                                "project": result.slug,
                                "elapsed_seconds": result.elapsed_seconds,
                                "backfill_count": result.backfill_count,
                            },
                        )
                        return
                    else:
                        self._respond_error(HTTPStatus.BAD_REQUEST, "unknown action")
                        return

                    self._respond_json(HTTPStatus.OK, hub._state_payload())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._respond_error(HTTPStatus.BAD_REQUEST, "invalid JSON")
                except Exception as exc:
                    from halyard.ai_log import _log_error

                    _log_error("hub timer action failed", exc)
                    self._respond_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal error")

            def _handle_presence_action(self) -> None:
                """v4.2: Record or close auto-timer presence."""
                if not self._authorized():
                    self._respond_error(HTTPStatus.UNAUTHORIZED, "missing or invalid token")
                    return
                body = self._read_body()
                if body is None:
                    return
                try:
                    data = json.loads(body)
                    action = data.get("action")
                    now = _parse_optional_iso(data.get("now"))
                    if action == "activity":
                        project = data.get("project")
                        timeclock = data.get("timeclock")
                        if not project or not timeclock:
                            self._respond_error(
                                HTTPStatus.BAD_REQUEST, "missing project or timeclock"
                            )
                            return
                        hub._record_presence_activity(project, Path(timeclock), now=now)
                        self._respond_json(HTTPStatus.OK, hub._state_payload())
                    elif action == "update":
                        hub._update_presence(now=now)
                        self._respond_json(HTTPStatus.OK, hub._state_payload())
                    elif action == "close_stale":
                        closed = hub._close_stale_presence(now=now)
                        self._respond_json(HTTPStatus.OK, {"closed": closed})
                    elif action == "close_now":
                        closed = hub._close_presence_now(now=now)
                        self._respond_json(HTTPStatus.OK, {"closed": closed})
                    else:
                        self._respond_error(HTTPStatus.BAD_REQUEST, "unknown action")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._respond_error(HTTPStatus.BAD_REQUEST, "invalid JSON")
                except Exception as exc:
                    from halyard.ai_log import _log_error

                    _log_error("hub presence action failed", exc)
                    self._respond_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal error")

            def _handle_sse(self) -> None:
                """v4.3: Handle a Server-Sent Events (SSE) connection."""
                # v5.19/B4: auth (token via ?token= query for EventSource) +
                # bound the number of concurrent streams.
                if not self._authorized():
                    self._respond_error(HTTPStatus.UNAUTHORIZED, "missing or invalid token")
                    return
                if not hub._sse_acquire():
                    self._respond_error(HTTPStatus.SERVICE_UNAVAILABLE, "too many SSE connections")
                    return
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                # Register this connection
                queue = hub._events.subscribe()

                try:
                    # Keep-alive loop
                    while not hub._stop.is_set():
                        for event in hub._events.drain(queue):
                            self.wfile.write(event.encode())

                        # Send keep-alive comment
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()

                        time.sleep(2)
                except (ConnectionResetError, BrokenPipeError):
                    pass
                finally:
                    hub._events.unsubscribe(queue)
                    hub._sse_release()

            def _handle_otlp(self) -> None:
                body = self._read_body()
                if body is None:
                    return
                try:
                    payload = json.loads(body)
                    hub.ingest_traces(payload)
                    self._respond_ok()
                except (ValueError, UnicodeDecodeError):
                    self.send_error(HTTPStatus.BAD_REQUEST, "invalid OTLP/JSON")

            def _handle_ingest(self) -> None:
                # v5.19/B4: require auth — this writes attacker-chosen sessions
                # into the exclusive ledger. (AF_UNIX peers pass via peer-cred.)
                if not self._authorized():
                    self._respond_error(HTTPStatus.UNAUTHORIZED, "missing or invalid token")
                    return
                body = self._read_body()
                if body is None:
                    return
                try:
                    data = json.loads(body)
                    payload = IngestPayload.model_validate(data)
                    hub.ingest_session(payload.to_session())
                    self._respond_ok()
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._respond_error(HTTPStatus.BAD_REQUEST, "invalid JSON")
                except ValidationError as exc:
                    self._respond_error(HTTPStatus.BAD_REQUEST, _validation_message(exc))
                except ValueError as exc:
                    self._respond_error(HTTPStatus.BAD_REQUEST, str(exc))

            def _host_ok(self) -> bool:
                """Reject non-loopback Host headers (DNS-rebinding / browser CSRF)."""
                # v5.19/B4: the Host allowlist is a browser/DNS-rebinding
                # defense; an AF_UNIX peer is a local process (no DNS, no
                # browser), authenticated by peer-credential instead.
                conn = getattr(self, "connection", None)
                if conn is not None and getattr(conn, "family", None) == socket.AF_UNIX:
                    return True
                host = self.headers.get("Host", "")
                return host in {f"127.0.0.1:{hub.port}", f"localhost:{hub.port}"}

            def _read_body(self) -> bytes | None:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self.send_error(HTTPStatus.BAD_REQUEST, "bad Content-Length")
                    return None
                # v5.19/B-followup: a negative Content-Length is not zero —
                # `self.rfile.read(-1)` blocks until EOF/peer-close, a trivial
                # local DoS. Reject anything outside [0, _MAX_BODY].
                if length < 0:
                    self.send_error(HTTPStatus.BAD_REQUEST, "negative Content-Length")
                    return None
                if length > _MAX_BODY:
                    self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body too large")
                    return None
                try:
                    body = self.rfile.read(length)
                except (TimeoutError, OSError):
                    self.send_error(HTTPStatus.REQUEST_TIMEOUT, "body read timed out")
                    return None
                if len(body) != length:
                    self.send_error(HTTPStatus.BAD_REQUEST, "incomplete body")
                    return None
                return body

            def _respond_ok(self) -> None:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(_OK_BODY)))
                self.end_headers()
                self.wfile.write(_OK_BODY)

            def _respond_error(self, status: HTTPStatus, message: str) -> None:
                self._respond_json(status, {"error": message})

            def _respond_json(self, status: HTTPStatus, data: dict[str, Any]) -> None:
                body = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _authorized(self) -> bool:
                # v5.19/B4: an AF_UNIX peer authenticates by OS peer-credential
                # (same-user) — no token needed. TCP can't provide peer creds,
                # so it falls through to the bearer token.
                conn = getattr(self, "connection", None)
                if conn is not None and getattr(conn, "family", None) == socket.AF_UNIX:
                    from halyard.peercred import peer_is_self

                    return peer_is_self(conn)

                from halyard.service import _load_or_create_token

                expected = _load_or_create_token()
                submitted = self.headers.get("X-Halyard-Token", "")
                if not submitted:
                    cookie = self.headers.get("Cookie", "")
                    for part in cookie.split(";"):
                        part = part.strip()
                        if part.startswith("halyard_token="):
                            submitted = part[len("halyard_token=") :]
                            break
                if not submitted:
                    # SSE EventSource cannot set request headers, so the
                    # dashboard renders the events URL with a ?token= param.
                    from urllib.parse import parse_qs, urlsplit

                    vals = parse_qs(urlsplit(self.path).query).get("token")
                    if vals:
                        submitted = vals[0]
                return bool(submitted) and hmac.compare_digest(submitted, expected)

            def _csrf_ok(self) -> bool:
                # v5.19/B4 (owner review): defeat browser cross-site CSRF /
                # DNS-rebinding writes. A malicious page can only send a CORS
                # "simple request" (text/plain, form-encoded, multipart) without
                # a preflight; requiring application/json forces a preflight the
                # hub never answers, blocking it. An explicit cross-site
                # Sec-Fetch-Site is also rejected. Machine clients (hub_client,
                # Copilot OTLP) send application/json and no Sec-Fetch-Site.
                if self.headers.get("Sec-Fetch-Site", "") == "cross-site":
                    return False
                ctype = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
                return ctype == "application/json"

            def log_message(self, *args: Any) -> None:
                pass

        return _Handler
