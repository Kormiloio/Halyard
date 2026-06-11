"""Peer-credential auth for AF_UNIX sockets (v5.19/B4).

Lets the Hub trust a *same-user* process connecting over its Unix-domain
ingest socket with no shared secret. TCP loopback cannot provide this —
peer credentials are an AF_UNIX feature (``SO_PEERCRED`` on Linux,
``getpeereid`` on macOS). On platforms where it is unavailable (Windows,
or any error) the helpers return ``None``/``False`` so the caller falls
back to token auth — fail closed, never fail open.
"""

from __future__ import annotations

import os
import socket
import struct
import sys


def peer_uid(sock: socket.socket) -> int | None:
    """Return the UID of the process on the other end of an AF_UNIX stream
    socket, or ``None`` if it cannot be determined (unsupported platform,
    non-AF_UNIX socket, or error)."""
    # Peer credentials are an AF_UNIX concept; a TCP/UDP socket has no peer
    # UID. Guard here so the helpers return None uniformly across platforms —
    # including Windows, where socket.AF_UNIX does not exist and a bare
    # attribute access raises AttributeError (the v5.19 regression that broke
    # every Hub request on the Windows CI matrix).
    af_unix = getattr(socket, "AF_UNIX", None)
    if af_unix is None or getattr(sock, "family", None) != af_unix:
        return None
    try:
        if sys.platform.startswith("linux") and hasattr(socket, "SO_PEERCRED"):
            # struct ucred { pid_t pid; uid_t uid; gid_t gid; } — three ints.
            buf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            _pid, uid, _gid = struct.unpack("3i", buf)
            return uid
        if sys.platform == "darwin":
            return _getpeereid_darwin(sock)
    except OSError:
        return None
    return None


def _getpeereid_darwin(sock: socket.socket) -> int | None:
    """macOS has no ``SO_PEERCRED``; use libc ``getpeereid(2)``."""
    import ctypes
    import ctypes.util

    libc_path = ctypes.util.find_library("c")
    if not libc_path:
        return None
    libc = ctypes.CDLL(libc_path, use_errno=True)
    # Explicit signature: without it ctypes marshals the byref pointers as
    # C int and truncates them on 64-bit, corrupting the call.
    libc.getpeereid.argtypes = [
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    libc.getpeereid.restype = ctypes.c_int
    euid = ctypes.c_uint32()
    egid = ctypes.c_uint32()
    rc = libc.getpeereid(sock.fileno(), ctypes.byref(euid), ctypes.byref(egid))
    if rc != 0:
        return None
    return int(euid.value)


def peer_is_self(sock: socket.socket) -> bool:
    """True iff the socket's peer runs as our own UID.

    Conservative: returns ``False`` when the peer UID cannot be determined
    (so a caller that requires same-user auth fails closed and the token
    path takes over)."""
    if not hasattr(os, "getuid"):
        return False  # Windows: no POSIX uid model — caller uses token auth
    uid = peer_uid(sock)
    return uid is not None and uid == os.getuid()
