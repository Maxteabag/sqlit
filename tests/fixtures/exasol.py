"""Exasol fixtures."""

from __future__ import annotations

import os
import ssl
import time
from contextlib import closing
from typing import Any

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

# Exasol Fixtures
EXASOL_HOST = os.environ.get("EXASOL_HOST", "localhost")
EXASOL_PORT = int(os.environ.get("EXASOL_PORT", "8563"))
EXASOL_USER = os.environ.get("EXASOL_USER", "sys")
EXASOL_PASSWORD = os.environ.get("EXASOL_PASSWORD", "exasol")
EXASOL_SCHEMA = os.environ.get("EXASOL_SCHEMA", "TEST_SQLIT")

# exasol/docker-db binds 8563 long before it accepts a login, so readiness is a
# real connect retried until this deadline rather than a bare open port.
EXASOL_READY_TIMEOUT = float(os.environ.get("EXASOL_READY_TIMEOUT", "300"))
_READY_INTERVAL = 5.0

# Set by exasol_server_ready when the deadline passes, so the skip message can
# name the driver error instead of only reporting "not available".
_ready_error: str | None = None


def exasol_available() -> bool:
    """Check if Exasol is available."""
    return is_port_open(EXASOL_HOST, EXASOL_PORT)


def _connect() -> Any:
    """Open a pyexasol connection to the test server.

    pyexasol is imported here rather than at module level: tests/conftest.py
    star-imports this module and is loaded by the driver-free unit CI job.
    docker-db presents a self-signed certificate, hence cert_reqs=CERT_NONE.
    """
    import pyexasol

    return pyexasol.connect(
        dsn=f"{EXASOL_HOST}:{EXASOL_PORT}",
        user=EXASOL_USER,
        password=EXASOL_PASSWORD,
        encryption=True,
        websocket_sslopt={"cert_reqs": ssl.CERT_NONE},
        autocommit=True,
    )


@pytest.fixture(scope="session")
def exasol_server_ready() -> bool:
    """Check if Exasol is ready and return True/False."""
    global _ready_error

    required = os.environ.get("EXASOL_REQUIRE_LIVE") == "1"
    if not exasol_available():
        if required:
            pytest.fail("Required Exasol server is not listening")
        return False

    try:
        import pyexasol  # noqa: F401
    except ImportError:
        if required:
            pytest.fail("Required pyexasol driver is not installed")
        pytest.skip("pyexasol is not installed")

    deadline = time.time() + EXASOL_READY_TIMEOUT
    while True:
        try:
            _connect().close()
            return True
        except Exception as e:
            _ready_error = str(e)
            if time.time() >= deadline:
                if required:
                    pytest.fail(f"Required Exasol server did not become ready: {_ready_error}")
                return False
            time.sleep(_READY_INTERVAL)


@pytest.fixture(scope="function")
def exasol_db(exasol_server_ready: bool) -> str:
    """Set up Exasol test schema."""
    if not exasol_server_ready:
        detail = f": {_ready_error}" if _ready_error else ""
        pytest.skip(f"Exasol is not available{detail}")

    try:
        import pyexasol  # noqa: F401
    except ImportError:
        pytest.skip("pyexasol is not installed")

    with closing(_connect()) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {EXASOL_SCHEMA} CASCADE")
        conn.execute(f"CREATE SCHEMA {EXASOL_SCHEMA}")
        conn.execute(f"OPEN SCHEMA {EXASOL_SCHEMA}")

        # Identifiers stay unquoted so Exasol's uppercase folding makes them
        # resolve from the shared suite's own unquoted queries.
        conn.execute("""
            CREATE TABLE test_users (
                id DECIMAL(18,0) PRIMARY KEY,
                name VARCHAR(100),
                email VARCHAR(200)
            )
        """)

        conn.execute("""
            CREATE TABLE test_products (
                id DECIMAL(18,0),
                name VARCHAR(100),
                price DECIMAL(10,2),
                stock DECIMAL(18,0)
            )
        """)

        # Exasol treats the empty string as NULL, so IS NOT NULL is the
        # non-empty test here; `email != ''` would match no row at all.
        conn.execute("""
            CREATE VIEW test_user_emails AS
            SELECT id, name, email FROM test_users WHERE email IS NOT NULL
        """)

        # No index, trigger or sequence: ExasolAdapter reports all three
        # capabilities as unsupported, so the matching base tests self-skip.

        conn.execute("""
            INSERT INTO test_users (id, name, email) VALUES
            (1, 'Alice', 'alice@example.com'),
            (2, 'Bob', 'bob@example.com'),
            (3, 'Charlie', 'charlie@example.com')
        """)

        conn.execute("""
            INSERT INTO test_products (id, name, price, stock) VALUES
            (1, 'Widget', 9.99, 100),
            (2, 'Gadget', 19.99, 50),
            (3, 'Gizmo', 29.99, 25)
        """)

    yield EXASOL_SCHEMA

    try:
        conn = _connect()
        conn.execute(f"DROP SCHEMA IF EXISTS {EXASOL_SCHEMA} CASCADE")
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def exasol_connection(exasol_db: str) -> str:
    """Create a sqlit CLI connection for Exasol and clean up after test."""
    connection_name = f"test_exasol_{os.getpid()}"

    cleanup_connection(connection_name)

    # --tls-mode require: docker-db presents a self-signed certificate, so the
    # connection has to encrypt without verifying the chain.
    run_cli(
        "connections",
        "add",
        "exasol",
        "--name",
        connection_name,
        "--server",
        EXASOL_HOST,
        "--port",
        str(EXASOL_PORT),
        "--username",
        EXASOL_USER,
        "--password",
        EXASOL_PASSWORD,
        "--schema",
        exasol_db,
        "--tls-mode",
        "require",
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "EXASOL_HOST",
    "EXASOL_PASSWORD",
    "EXASOL_PORT",
    "EXASOL_READY_TIMEOUT",
    "EXASOL_SCHEMA",
    "EXASOL_USER",
    "exasol_available",
    "exasol_connection",
    "exasol_db",
    "exasol_server_ready",
]
