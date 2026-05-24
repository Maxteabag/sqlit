"""Tests for probe_port — distinguishes HTTP interceptors from binary servers.

See issue #200: a bare TCP connect classifies any accepting daemon as
"open", so test fixtures based on `is_port_open` proceed against HTTP
security agents and the binary driver hangs reading framing data.
"""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

from tests.fixtures.utils import is_binary_port_open, probe_port


def _fake_socket_returning(initial_bytes: bytes) -> MagicMock:
    """Build a mock sock that returns initial_bytes on the first recv()."""
    sock = MagicMock()
    sock.recv.return_value = initial_bytes
    sock.__enter__.return_value = sock
    sock.__exit__.return_value = False
    return sock


def test_http_interceptor_is_detected_as_http():
    sock = _fake_socket_returning(b"HTTP/1.1")
    with patch("socket.create_connection", return_value=sock):
        assert probe_port("localhost", 10001) == "http"
        assert is_binary_port_open("localhost", 10001) is False


def test_binary_server_replies_with_non_http_bytes():
    # Postgres greeting starts with a length-prefixed message — not "HTTP/".
    sock = _fake_socket_returning(b"\x00\x00\x00\x08")
    with patch("socket.create_connection", return_value=sock):
        assert probe_port("localhost", 5432) == "binary"
        assert is_binary_port_open("localhost", 5432) is True


def test_binary_server_that_doesnt_reply_to_http_is_still_binary():
    """A strict binary protocol may simply ignore our HTTP gibberish; the
    subsequent recv() then times out, which we still classify as binary."""
    sock = MagicMock()
    sock.recv.side_effect = socket.timeout
    sock.__enter__.return_value = sock
    sock.__exit__.return_value = False
    with patch("socket.create_connection", return_value=sock):
        assert probe_port("localhost", 3306) == "binary"
        assert is_binary_port_open("localhost", 3306) is True


def test_connection_refused_classified_separately_from_timeout():
    with patch("socket.create_connection", side_effect=ConnectionRefusedError):
        assert probe_port("localhost", 1) == "refused"
        assert is_binary_port_open("localhost", 1) is False


def test_connect_timeout_classified_as_timeout():
    with patch("socket.create_connection", side_effect=TimeoutError):
        assert probe_port("localhost", 1) == "timeout"
        assert is_binary_port_open("localhost", 1) is False
