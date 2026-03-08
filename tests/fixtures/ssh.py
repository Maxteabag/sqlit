"""SSH tunnel fixtures."""

from __future__ import annotations

import os
import time

import pytest

from tests.fixtures.postgres import POSTGRES_DATABASE, POSTGRES_PASSWORD, POSTGRES_USER
from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

# SSH connection settings for Docker
SSH_HOST = os.environ.get("SSH_HOST", "localhost")
SSH_PORT = int(os.environ.get("SSH_PORT", "2222"))
SSH_USER = os.environ.get("SSH_USER", "testuser")
SSH_PASSWORD = os.environ.get("SSH_PASSWORD", "testpass")
# The PostgreSQL host as seen from the SSH server (docker network)
SSH_REMOTE_DB_HOST = os.environ.get("SSH_REMOTE_DB_HOST", "postgres-ssh")
SSH_REMOTE_DB_PORT = int(os.environ.get("SSH_REMOTE_DB_PORT", "5432"))


def ssh_available() -> bool:
    """Check if SSH server is available."""
    return is_port_open(SSH_HOST, SSH_PORT)


@pytest.fixture(scope="session")
def ssh_server_ready() -> bool:
    """Check if SSH server is ready and return True/False."""
    if not ssh_available():
        return False
    time.sleep(1)
    return True


@pytest.fixture(scope="function")
def ssh_postgres_db(ssh_server_ready: bool) -> str:
    """Set up PostgreSQL test database accessible via SSH tunnel."""
    if not ssh_server_ready:
        pytest.skip("SSH server is not available")

    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 is not installed")

    # postgres-ssh container is accessible on port 5433
    pg_host = os.environ.get("SSH_DIRECT_PG_HOST", "localhost")
    pg_port = int(os.environ.get("SSH_DIRECT_PG_PORT", "5433"))

    try:
        conn = psycopg2.connect(
            host=pg_host,
            port=pg_port,
            database=POSTGRES_DATABASE,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            connect_timeout=10,
        )
        conn.autocommit = True
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS test_users CASCADE")
        cursor.execute("DROP TABLE IF EXISTS test_products CASCADE")
        cursor.execute("DROP VIEW IF EXISTS test_user_emails")

        cursor.execute("""
            CREATE TABLE test_users (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE
            )
        """)

        cursor.execute("""
            CREATE TABLE test_products (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                stock INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE VIEW test_user_emails AS
            SELECT id, name, email FROM test_users WHERE email IS NOT NULL
        """)

        cursor.execute("""
            INSERT INTO test_users (id, name, email) VALUES
            (1, 'Alice', 'alice@example.com'),
            (2, 'Bob', 'bob@example.com'),
            (3, 'Charlie', 'charlie@example.com')
        """)

        cursor.execute("""
            INSERT INTO test_products (id, name, price, stock) VALUES
            (1, 'Widget', 9.99, 100),
            (2, 'Gadget', 19.99, 50),
            (3, 'Gizmo', 29.99, 25)
        """)

        conn.close()

    except Exception as e:
        pytest.skip(f"Failed to setup PostgreSQL database for SSH test: {e}")

    yield POSTGRES_DATABASE

    try:
        conn = psycopg2.connect(
            host=pg_host,
            port=pg_port,
            database=POSTGRES_DATABASE,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            connect_timeout=10,
        )
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS test_users CASCADE")
        cursor.execute("DROP TABLE IF EXISTS test_products CASCADE")
        cursor.execute("DROP VIEW IF EXISTS test_user_emails")
        conn.close()
    except Exception:
        pass


@pytest.fixture(scope="function")
def ssh_connection(ssh_postgres_db: str) -> str:
    """Create a sqlit CLI connection for PostgreSQL via SSH tunnel."""
    connection_name = f"test_ssh_{os.getpid()}"

    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "postgresql",
        "--name",
        connection_name,
        "--server",
        SSH_REMOTE_DB_HOST,
        "--port",
        str(SSH_REMOTE_DB_PORT),
        "--database",
        ssh_postgres_db,
        "--username",
        POSTGRES_USER,
        "--password",
        POSTGRES_PASSWORD,
        "--ssh-enabled",
        "--ssh-host",
        SSH_HOST,
        "--ssh-port",
        str(SSH_PORT),
        "--ssh-username",
        SSH_USER,
        "--ssh-auth-type",
        "password",
        "--ssh-password",
        SSH_PASSWORD,
    )

    yield connection_name

    cleanup_connection(connection_name)


__all__ = [
    "SSH_HOST",
    "SSH_PASSWORD",
    "SSH_PORT",
    "SSH_REMOTE_DB_HOST",
    "SSH_REMOTE_DB_PORT",
    "SSH_USER",
    "ssh_available",
    "ssh_connection",
    "ssh_postgres_db",
    "ssh_server_ready",
]
