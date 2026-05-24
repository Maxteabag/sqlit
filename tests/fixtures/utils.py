"""Shared helpers for test fixtures."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_TEST_CONFIG_DIR = Path(tempfile.mkdtemp(prefix="sqlit-test-config-"))
os.environ.setdefault("SQLIT_CONFIG_DIR", str(_TEST_CONFIG_DIR))

# Enable plaintext credential storage for tests (no keyring in CI)
_settings_file = _TEST_CONFIG_DIR / "settings.json"
_settings_file.write_text('{"allow_plaintext_credentials": true}')


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a TCP port is open."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, OSError):
        return False


def probe_port(host: str, port: int, timeout: float = 0.5) -> str:
    """Classify a TCP port as 'refused', 'http', 'binary', or 'timeout'.

    A bare TCP connect (`is_port_open`) returns True for any service that
    accepts the connection — including HTTP security agents that bind common
    ports. When a fixture then opens a binary-protocol driver (Thrift,
    MySQL/Postgres wire, TNS, …) to that port, the driver misreads the
    HTTP response bytes as protocol framing and hangs indefinitely.

    This probe sends a one-line HTTP request and inspects the response:
    if it starts with `HTTP/` the port is owned by an HTTP daemon, not the
    binary server the fixture expects. See issue #200.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            try:
                sock.sendall(b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n")
                data = sock.recv(8)
                return "http" if data.startswith(b"HTTP/") else "binary"
            except socket.timeout:
                # Binary protocol server that ignored our HTTP gibberish.
                return "binary"
    except ConnectionRefusedError:
        return "refused"
    except (TimeoutError, OSError):
        return "timeout"


def is_binary_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Like `is_port_open` but rejects HTTP interceptors.

    Use in fixture availability checks for binary-protocol servers so the
    test suite doesn't hang on a security agent that happens to bind the
    same port. See issue #200.
    """
    return probe_port(host, port, timeout) == "binary"


def wait_for_port(host: str, port: int, timeout: float = 60.0) -> bool:
    """Wait for a TCP port to become available."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(host, port):
            return True
        time.sleep(1)
    return False


def run_cli(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run sqlit CLI command and return result."""
    cmd = [sys.executable, "-m", "sqlit.cli"] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        stderr_clean = "\n".join(
            line
            for line in result.stderr.split("\n")
            if "RuntimeWarning" not in line and "unpredictable behaviour" not in line
        ).strip()
        if stderr_clean:
            raise RuntimeError(f"CLI command failed: {stderr_clean}")
    return result


def cleanup_connection(name: str) -> None:
    """Delete a connection if it exists, ignoring errors."""
    try:
        run_cli("connection", "delete", name, check=False)
    except Exception:
        pass


__all__ = [
    "cleanup_connection",
    "is_port_open",
    "run_cli",
    "wait_for_port",
]
