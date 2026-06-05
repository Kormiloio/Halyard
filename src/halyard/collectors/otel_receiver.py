"""Local OTLP/HTTP receiver for VS Code Copilot telemetry (v3.12).

VS Code Copilot is a standard OTLP *exporter*: it pushes spans to an
endpoint, it does not write a file. So Halyard must *receive*. This is a
tiny stdlib ``ThreadingHTTPServer`` bound to ``127.0.0.1:4318`` that
accepts ``POST /v1/traces`` (and tolerates ``/v1/metrics``), decodes the
OTLP/JSON body, and folds it into the shared per-``session.id``
accumulator in :mod:`halyard.collectors.vscode_otel` (the testable
mapper). Sessions are flushed to the ledger on an idle TTL (the Windsurf
v3.6 pattern) and on shutdown.

Hosted as a daemon thread inside the long-lived ``halyard dashboard``
service process — no new daemon for the user to manage — and started
**only when OTel capture is opted into** (``vscode_otel.MARKER_PATH``),
so a default install gets no new listener.

Privacy: binds loopback only; the mapper reads a metadata allowlist, so
no content reaches a row. The request body is size-bounded (untrusted
input). On flush, each captured ``session.id`` is recorded in the
importer's dedup state so the v3.7 importer never double-counts it.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from halyard.collectors.vscode_otel import _SessionAcc, accumulate_traces, finalize

OTEL_HOST = "127.0.0.1"
OTEL_PORT = 4318

# Idle window after which a session with no new spans is considered done
# and flushed. Mirrors the Windsurf finalization idea; shorter so live
# rows appear without a long wait.
_IDLE_TTL = timedelta(minutes=10)

# Untrusted-input bound: reject an OTLP body larger than this.
_MAX_BODY = 25 * 1024 * 1024  # 25 MB

# v5.18/B06: cardinality cap on the per-session accumulator. ``session.id``
# is wire-supplied, so an unbounded ``_acc`` lets an id-spray OOM the host.
# When the cap is exceeded we FINALIZE the least-recently-updated session
# (never silently drop an in-flight one) to make room.
_MAX_SESSIONS = 4096

# OTLP/HTTP success body (empty ExportTraceServiceResponse).
_OK_BODY = b"{}"


class OTelReceiver:
    """A localhost OTLP/HTTP receiver feeding the vscode_otel mapper."""

    def __init__(self, project_dir: Path | None = None, *, port: int = OTEL_PORT) -> None:
        self.project_dir = project_dir
        self.port = port
        self._acc: dict[str, _SessionAcc] = {}
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._serve_thread: threading.Thread | None = None
        self._flush_thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ── lifecycle ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Bind the loopback socket and start serving + flushing in threads.

        Binds ``127.0.0.1`` only (rejects non-local connections at the
        socket layer). Raises ``OSError`` if the port is unavailable.
        """
        self._server = ThreadingHTTPServer((OTEL_HOST, self.port), self._handler())
        self._serve_thread = threading.Thread(
            target=self._server.serve_forever, name="halyard-otel-receiver", daemon=True
        )
        self._serve_thread.start()
        self._flush_thread = threading.Thread(
            target=self._flush_loop, name="halyard-otel-flush", daemon=True
        )
        self._flush_thread.start()

    def stop(self) -> None:
        """Stop serving, flush every pending session, and close the socket."""
        self._stop.set()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        self.flush_stale(force=True)

    # ── ingestion ──────────────────────────────────────────────────────

    def ingest_traces(self, payload: Any) -> None:
        with self._lock:
            accumulate_traces(self._acc, payload)
            evicted = self._evict_over_cap_locked()
        # v5.18/B06: finalize evicted sessions outside the lock so an
        # id-spray cannot OOM the host, and so an in-flight session is
        # never silently dropped on eviction.
        for acc in evicted:
            self._finalize_one(acc)

    def _evict_over_cap_locked(self) -> list[_SessionAcc]:
        """Pop least-recently-updated sessions until under the cardinality cap.

        Caller must hold ``self._lock``. Returns the popped accumulators so
        the caller can finalize them outside the lock.
        """
        if len(self._acc) <= _MAX_SESSIONS:
            return []
        # Oldest last_update first: evict the stalest in-flight sessions.
        ordered = sorted(self._acc.items(), key=lambda kv: kv[1].last_update)
        overflow = len(self._acc) - _MAX_SESSIONS
        evicted = []
        for sid, acc in ordered[:overflow]:
            del self._acc[sid]
            evicted.append(acc)
        return evicted

    # ── flush ──────────────────────────────────────────────────────────

    def _flush_loop(self) -> None:
        # Wake periodically; flush sessions idle past the TTL. Exits when
        # stop() sets the event (also flushed force-true there).
        while not self._stop.wait(60):
            # v5.18/B06: this is the only flush thread. Any raise in
            # flush_stale/_finalize_one (deleted cwd, git shellout, disk IO)
            # would permanently kill it and telemetry would never be written
            # again. Swallow and continue so the daemon never dies.
            try:
                self.flush_stale()
            except Exception as exc:  # daemon must survive any finalize raise
                from halyard.ai_log import log_diagnostic

                log_diagnostic(f"otel flush_loop error: {exc!r}", tool="otel")

    def flush_stale(self, *, force: bool = False) -> int:
        """Finalize and append sessions idle past the TTL (or all if force).

        Returns the count appended. Each appended session id is recorded
        in the importer dedup state so the v3.7 importer skips it.
        """
        now = datetime.now()
        with self._lock:
            ready = [
                sid
                for sid, acc in self._acc.items()
                if force or (now - acc.last_update) > _IDLE_TTL
            ]

        # v5.18/B06: finalize-then-pop. The old code popped every ready
        # session up front, so a mid-loop raise in _finalize_one (deleted
        # cwd, git shellout, disk IO) silently lost sessions N..end with no
        # re-queue. Pop one at a time and re-insert on failure so a partial
        # flush retries on the next tick instead of dropping telemetry.
        count = 0
        for sid in ready:
            with self._lock:
                acc = self._acc.pop(sid, None)
            if acc is None:
                continue  # concurrently evicted/flushed
            try:
                if self._finalize_one(acc):
                    count += 1
            except Exception:
                with self._lock:
                    # Re-insert only if a newer accumulator did not take its
                    # place while the lock was released.
                    self._acc.setdefault(sid, acc)
                raise
        return count

    def _finalize_one(self, acc: _SessionAcc) -> bool:
        from halyard.ai_log import (
            AI_LOG_FILENAME,
            append_session,
            find_project_dir,
            maybe_show_dashboard_hint,
            read_active_project,
            write_unattributed_session,
        )
        from halyard.collectors import session_has_evidence, session_is_implausible
        from halyard.collectors.copilot import record_otel_capture
        from halyard.git_context import infer_project_with_source
        from halyard.hub import find_hub

        session = finalize(acc)
        if session is None:
            return False
        if not session_has_evidence(session) or session_is_implausible(session):
            return False

        cwd = Path.cwd()
        target_dir = self.project_dir or find_project_dir(start=cwd) or find_hub()

        proj, method = infer_project_with_source(cwd)
        active = read_active_project()
        if active:
            proj, method = active, "timer"
        session.project = proj
        session.attr_method = method

        if target_dir and (target_dir / AI_LOG_FILENAME).exists():
            append_session(target_dir, session)
            maybe_show_dashboard_hint()
        else:
            write_unattributed_session(session)

        # Coexistence: the importer skips any session id already captured.
        if session.session_id:
            record_otel_capture(session.session_id)
        return True

    # ── HTTP handler ───────────────────────────────────────────────────

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        receiver = self

        class _Handler(BaseHTTPRequestHandler):
            # v5.18/B06: bound per-request socket reads so a slow/half-open
            # client cannot hold a ThreadingHTTPServer worker thread forever
            # (slowloris). Mirrors hub_server's handler (hub_server.py:625).
            timeout = 10

            def do_POST(self) -> None:
                path = self.path.split("?", 1)[0].rstrip("/")
                if path not in ("/v1/traces", "/v1/metrics"):
                    self.send_error(HTTPStatus.NOT_FOUND, "unknown OTLP path")
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0") or "0")
                except ValueError:
                    self.send_error(HTTPStatus.BAD_REQUEST, "bad Content-Length")
                    return
                if length <= 0:
                    self._respond_ok()  # empty export is a valid no-op
                    return
                if length > _MAX_BODY:
                    self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body too large")
                    return
                body = self.rfile.read(length)
                try:
                    payload = json.loads(body)
                except (ValueError, UnicodeDecodeError):
                    self.send_error(HTTPStatus.BAD_REQUEST, "invalid OTLP/JSON")
                    return
                # Metrics are tolerated (200) but not parsed: per the GenAI
                # semconv, per-call token usage rides on spans, which is the
                # path we map. Re-confirm in Phase 0 against a live capture.
                if path == "/v1/traces":
                    receiver.ingest_traces(payload)
                self._respond_ok()

            def _respond_ok(self) -> None:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(_OK_BODY)))
                self.end_headers()
                self.wfile.write(_OK_BODY)

            def log_message(self, *args: Any) -> None:
                pass  # silence default stderr access logging

        return _Handler


def start_receiver(project_dir: Path | None, *, port: int = OTEL_PORT) -> OTelReceiver | None:
    """Start the receiver if OTel capture is opted into; else return None.

    Best-effort: a bind failure (port in use) is swallowed so it can
    never take down the dashboard service it rides inside.
    """
    from halyard.collectors.vscode_otel import otel_capture_enabled

    if not otel_capture_enabled():
        return None
    receiver = OTelReceiver(project_dir, port=port)
    try:
        receiver.start()
    except OSError:
        return None
    return receiver
