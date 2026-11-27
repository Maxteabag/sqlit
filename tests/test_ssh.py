"""Integration tests for SSH tunnel functionality."""

from __future__ import annotations

import json
import time

import pytest


class TestSSHTunnelIntegration:
    """Integration tests for SSH tunnel database connections via CLI.

    These tests require:
    - A running SSH server (via Docker)
    - A PostgreSQL instance accessible from the SSH server
    Tests are skipped if SSH server is not available.
    """

    @pytest.fixture(autouse=True)
    def slow_down_ssh_tests(self):
        """Add a small delay between SSH tests to avoid overwhelming the server.

        Note: SSH tests may fail when run together rapidly due to SSH server
        connection limits. Run individually with: pytest tests/test_ssh.py -k <test_name>
        """
        time.sleep(2)  # Wait before each test
        yield
        time.sleep(1)  # Wait after each test for connections to fully close

    def test_create_ssh_connection(self, ssh_postgres_db, cli_runner):
        """Test creating a PostgreSQL connection with SSH tunnel via CLI."""
        from .conftest import (
            POSTGRES_PASSWORD,
            POSTGRES_USER,
            SSH_HOST,
            SSH_PASSWORD,
            SSH_PORT,
            SSH_REMOTE_DB_HOST,
            SSH_REMOTE_DB_PORT,
            SSH_USER,
        )

        connection_name = "test_create_ssh"

        try:
            # Create connection with SSH tunnel
            result = cli_runner(
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
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "PostgreSQL" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_query_via_ssh_tunnel(self, ssh_connection, cli_runner):
        """Test executing SELECT query through SSH tunnel."""
        result = cli_runner(
            "query",
            "-c",
            ssh_connection,
            "-q",
            "SELECT * FROM test_users ORDER BY id",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "Bob" in result.stdout
        assert "Charlie" in result.stdout
        assert "3 row(s) returned" in result.stdout

    def test_query_with_where_via_ssh(self, ssh_connection, cli_runner):
        """Test executing SELECT with WHERE clause through SSH tunnel."""
        result = cli_runner(
            "query",
            "-c",
            ssh_connection,
            "-q",
            "SELECT name, email FROM test_users WHERE id = 1",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "alice@example.com" in result.stdout
        assert "1 row(s) returned" in result.stdout

    def test_query_json_format_via_ssh(self, ssh_connection, cli_runner):
        """Test query output in JSON format through SSH tunnel."""
        result = cli_runner(
            "query",
            "-c",
            ssh_connection,
            "-q",
            "SELECT id, name FROM test_users ORDER BY id LIMIT 2",
            "--format",
            "json",
        )
        assert result.returncode == 0

        # Parse JSON output (row count message goes to stderr, not stdout)
        data = json.loads(result.stdout)

        assert len(data) == 2
        assert data[0]["name"] == "Alice"
        assert data[1]["name"] == "Bob"

    def test_query_csv_format_via_ssh(self, ssh_connection, cli_runner):
        """Test query output in CSV format through SSH tunnel."""
        result = cli_runner(
            "query",
            "-c",
            ssh_connection,
            "-q",
            "SELECT id, name FROM test_users ORDER BY id LIMIT 2",
            "--format",
            "csv",
        )
        assert result.returncode == 0
        assert "id,name" in result.stdout
        assert "1,Alice" in result.stdout
        assert "2,Bob" in result.stdout

    def test_query_aggregate_via_ssh(self, ssh_connection, cli_runner):
        """Test aggregate query through SSH tunnel."""
        result = cli_runner(
            "query",
            "-c",
            ssh_connection,
            "-q",
            "SELECT COUNT(*) as user_count FROM test_users",
        )
        assert result.returncode == 0
        assert "3" in result.stdout

    def test_insert_via_ssh(self, ssh_connection, cli_runner):
        """Test INSERT statement through SSH tunnel."""
        result = cli_runner(
            "query",
            "-c",
            ssh_connection,
            "-q",
            "INSERT INTO test_users (id, name, email) VALUES (4, 'David', 'david@example.com')",
        )
        assert result.returncode == 0

        # Verify the insert
        result = cli_runner(
            "query",
            "-c",
            ssh_connection,
            "-q",
            "SELECT * FROM test_users WHERE id = 4",
        )
        assert "David" in result.stdout

    def test_delete_ssh_connection(self, ssh_postgres_db, cli_runner):
        """Test deleting an SSH tunnel connection."""
        from .conftest import (
            POSTGRES_PASSWORD,
            POSTGRES_USER,
            SSH_HOST,
            SSH_PASSWORD,
            SSH_PORT,
            SSH_REMOTE_DB_HOST,
            SSH_REMOTE_DB_PORT,
            SSH_USER,
        )

        connection_name = "test_delete_ssh"

        # Create connection first
        cli_runner(
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

        # Delete it
        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        # Verify it's gone
        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout


@pytest.mark.parametrize("reuse_session_tunnel", [True, False], ids=["borrowed", "owned"])
def test_transaction_script_via_ssh(ssh_server_ready, reuse_session_tunnel):
    from sqlit.domains.connections.app.session import ConnectionSession
    from sqlit.domains.connections.domain.config import ConnectionConfig
    from sqlit.domains.query.app.transaction import TransactionExecutor
    from tests.fixtures.postgres import POSTGRES_DATABASE, POSTGRES_PASSWORD, POSTGRES_USER
    from tests.fixtures.ssh import (
        SSH_HOST, SSH_PASSWORD, SSH_PORT, SSH_REMOTE_DB_HOST, SSH_REMOTE_DB_PORT, SSH_USER,
    )

    if not ssh_server_ready:
        pytest.skip("SSH integration fixture is unavailable")

    config = ConnectionConfig.from_dict({
        "name": "transaction-via-ssh", "db_type": "postgresql",
        "server": SSH_REMOTE_DB_HOST, "port": str(SSH_REMOTE_DB_PORT),
        "database": POSTGRES_DATABASE, "username": POSTGRES_USER, "password": POSTGRES_PASSWORD,
        "ssh_enabled": True, "ssh_host": SSH_HOST, "ssh_port": str(SSH_PORT),
        "ssh_username": SSH_USER, "ssh_auth_type": "password", "ssh_password": SSH_PASSWORD,
    })
    with ConnectionSession.create(config) as session:
        executor = TransactionExecutor(
            config=config, provider=session.provider,
            tunnel=session.tunnel if reuse_session_tunnel else None,
        )
        try:
            result = executor.atomic_execute(
                "CREATE TEMP TABLE tunnel_check (value integer); "
                "INSERT INTO tunnel_check VALUES (73); SELECT value FROM tunnel_check"
            )
            assert result.completed, result.results
            assert result.results[-1].result.rows == [(73,)]
        finally:
            executor.close()

        # Closing the transaction executor must leave the original session usable.
        with session.connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1
