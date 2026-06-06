"""v5.19/B4 — AF_UNIX peer-credential helpers."""

from __future__ import annotations

import os
import socket
import sys

import pytest

from halyard import peercred

_POSIX = hasattr(os, "getuid")
_SUPPORTED = sys.platform.startswith("linux") or sys.platform == "darwin"


@pytest.mark.skipif(not _SUPPORTED, reason="peer-cred only on Linux/macOS")
def test_peer_uid_of_af_unix_pair_is_self() -> None:
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        assert peercred.peer_uid(a) == os.getuid()
        assert peercred.peer_uid(b) == os.getuid()
    finally:
        a.close()
        b.close()


@pytest.mark.skipif(not _SUPPORTED, reason="peer-cred only on Linux/macOS")
def test_peer_is_self_true_for_same_process_pair() -> None:
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        assert peercred.peer_is_self(a) is True
    finally:
        a.close()
        b.close()


def test_peer_is_self_fails_closed_without_getuid(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate Windows (no os.getuid): must fail closed, not raise.
    monkeypatch.delattr(os, "getuid", raising=False)
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM) if _POSIX else (None, None)
    try:
        sock = a if a is not None else socket.socket()
        assert peercred.peer_is_self(sock) is False
    finally:
        if a is not None:
            a.close()
            b.close()


@pytest.mark.skipif(not _POSIX, reason="socketpair needs POSIX")
def test_peer_uid_on_non_unix_socket_is_none() -> None:
    # A plain (non-AF_UNIX) socket has no peer creds -> None, no crash.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        assert peercred.peer_uid(s) is None
    finally:
        s.close()
