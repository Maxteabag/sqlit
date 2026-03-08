"""Turso (libSQL) fixtures."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

# Load .env file from tests directory if it exists
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

# Turso Cloud settings (takes precedence over Docker if set)
TURSO_CLOUD_URL = os.environ.get("TURSO_CLOUD_URL", "")
TURSO_CLOUD_AUTH_TOKEN = os.environ.get("TURSO_CLOUD_AUTH_TOKEN", "")

# Turso connection settings for Docker (libsql-server)
TURSO_HOST = os.environ.get("TURSO_HOST", "localhost")
TURSO_PORT = int(os.environ.get("TURSO_PORT", "8081"))


def _using_turso_cloud() -> bool:
    """Check if we should use Turso Cloud instead of local Docker."""
    return bool(TURSO_CLOUD_URL and TURSO_CLOUD_AUTH_TOKEN)


def turso_available() -> bool:
    """Check if Turso (libsql-server or cloud) is available."""
    if _using_turso_cloud():
        return True  # Assume cloud is available if configured
    return is_port_open(TURSO_HOST, TURSO_PORT)


@pytest.fixture(scope="session")
def turso_server_ready() -> bool:
    """Check if Turso is ready and return True/False."""
    if _using_turso_cloud():
        return True

    if not turso_available():
        return False

    time.sleep(1)
    return True


def _get_turso_cloud_sync_url() -> str:
    """Convert libsql:// URL to https:// for sync_url parameter."""
    url = TURSO_CLOUD_URL
    if url.startswith("libsql://"):
        url = url.replace("libsql://", "https://", 1)
    elif not url.startswith(("https://", "http://")):
        url = f"https://{url}"
    return url


def _create_turso_connection():
    """Create a libsql connection for either Cloud or Docker.

    Uses direct HTTP mode for both Cloud and Docker for consistent behavior.
    """
    import libsql

    if _using_turso_cloud():
        url = _get_turso_cloud_sync_url()
        return libsql.connect(url, auth_token=TURSO_CLOUD_AUTH_TOKEN)
    else:
        # For local Docker, connect directly
        turso_url = f"http://{TURSO_HOST}:{TURSO_PORT}"
        return libsql.connect(turso_url)


def _setup_turso_test_tables(client) -> None:
    """Set up test tables in Turso database."""
    # Drop existing test objects
    client.execute("DROP TRIGGER IF EXISTS trg_test_users_audit")
    client.execute("DROP INDEX IF EXISTS idx_test_users_email")
    client.execute("DROP VIEW IF EXISTS test_user_emails")
    client.execute("DROP TABLE IF EXISTS test_users")
    client.execute("DROP TABLE IF EXISTS test_products")

    # Create tables
    client.execute("""
        CREATE TABLE test_users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE
        )
    """)

    client.execute("""
        CREATE TABLE test_products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER DEFAULT 0
        )
    """)

    # Create view
    client.execute("""
        CREATE VIEW test_user_emails AS
        SELECT id, name, email FROM test_users WHERE email IS NOT NULL
    """)

    # Create test index
    client.execute("CREATE INDEX idx_test_users_email ON test_users(email)")

    # Create test trigger
    client.execute("""
        CREATE TRIGGER trg_test_users_audit
        AFTER INSERT ON test_users
        BEGIN
            SELECT 1;
        END
    """)

    # Insert test data
    client.execute("""
        INSERT INTO test_users (id, name, email) VALUES
        (1, 'Alice', 'alice@example.com'),
        (2, 'Bob', 'bob@example.com'),
        (3, 'Charlie', 'charlie@example.com')
    """)

    client.execute("""
        INSERT INTO test_products (id, name, price, stock) VALUES
        (1, 'Widget', 9.99, 100),
        (2, 'Gadget', 19.99, 50),
        (3, 'Gizmo', 29.99, 25)
    """)

    # Commit changes to persist them
    client.commit()


def _cleanup_turso_test_tables(client) -> None:
    """Clean up test tables in Turso database."""
    client.execute("DROP TRIGGER IF EXISTS trg_test_users_audit")
    client.execute("DROP INDEX IF EXISTS idx_test_users_email")
    client.execute("DROP VIEW IF EXISTS test_user_emails")
    client.execute("DROP TABLE IF EXISTS test_users")
    client.execute("DROP TABLE IF EXISTS test_products")
    client.commit()


@pytest.fixture(scope="function")
def turso_db(turso_server_ready: bool) -> str:
    """Set up Turso test database.

    Supports both local Docker (libsql-server) and Turso Cloud.
    Set TURSO_CLOUD_URL and TURSO_CLOUD_AUTH_TOKEN env vars to use cloud.
    """
    if not turso_server_ready:
        pytest.skip("Turso (libsql-server) is not available")

    import importlib.util

    if importlib.util.find_spec("libsql") is None:
        pytest.skip("libsql is not installed")

    try:
        client = _create_turso_connection()
        _setup_turso_test_tables(client)
        client.close()
    except Exception as e:
        pytest.skip(f"Failed to setup Turso database: {e}")

    # Yield connection info for turso_connection fixture
    if _using_turso_cloud():
        yield (TURSO_CLOUD_URL, TURSO_CLOUD_AUTH_TOKEN)
    else:
        yield f"http://{TURSO_HOST}:{TURSO_PORT}"

    # Cleanup
    try:
        client = _create_turso_connection()
        _cleanup_turso_test_tables(client)
        client.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def turso_connection(turso_db) -> str:
    """Create a sqlit CLI connection for Turso and clean up after test.

    Works with both local Docker and Turso Cloud.
    """
    connection_name = f"test_turso_{os.getpid()}"

    cleanup_connection(connection_name)

    # Handle both cloud (tuple) and docker (string) modes
    if isinstance(turso_db, tuple):
        turso_url, auth_token = turso_db
    else:
        turso_url = turso_db
        auth_token = ""

    run_cli(
        "connections",
        "add",
        "turso",
        "--name",
        connection_name,
        "--server",
        turso_url,
        "--password",
        auth_token or "",
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "TURSO_CLOUD_AUTH_TOKEN",
    "TURSO_CLOUD_URL",
    "TURSO_HOST",
    "TURSO_PORT",
    "turso_available",
    "turso_connection",
    "turso_db",
    "turso_server_ready",
]
