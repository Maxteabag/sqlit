"""Integration tests for Turso (libSQL) database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestTursoIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for Turso database operations via CLI.

    These tests require a running libsql-server instance (via Docker).
    Tests are skipped if libsql-server is not available.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="turso",
            display_name="Turso",
            connection_fixture="turso_connection",
            db_fixture="turso_db",
            create_connection_args=lambda: [],  # Uses fixtures
        )

    def test_create_turso_connection(self, turso_db, cli_runner):
        """Test creating a Turso connection via CLI."""
        connection_name = "test_create_turso"

        # Handle both cloud (tuple) and docker (string) modes
        if isinstance(turso_db, tuple):
            turso_url, auth_token = turso_db
        else:
            turso_url = turso_db
            auth_token = ""

        try:
            result = cli_runner(
                "connections",
                "add",
                "turso",
                "--name",
                connection_name,
                "--server",
                turso_url,
                "--password",
                auth_token,
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "Turso" in result.stdout

        finally:
            cli_runner("connection", "delete", connection_name, check=False)

    def test_query_turso_join(self, turso_connection, cli_runner):
        """Test JOIN query on Turso."""
        result = cli_runner(
            "query",
            "-c",
            turso_connection,
            "-q",
            """
                SELECT u.name, p.name as product, p.price
                FROM test_users u
                CROSS JOIN test_products p
                WHERE u.id = 1 AND p.id = 1
            """,
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "Widget" in result.stdout

    def test_query_turso_update(self, turso_connection, cli_runner):
        """Test UPDATE statement on Turso."""
        result = cli_runner(
            "query",
            "-c",
            turso_connection,
            "-q",
            "UPDATE test_products SET stock = 200 WHERE id = 1",
        )
        assert result.returncode == 0

        result = cli_runner(
            "query",
            "-c",
            turso_connection,
            "-q",
            "SELECT stock FROM test_products WHERE id = 1",
        )
        assert "200" in result.stdout

    def test_delete_turso_connection(self, turso_db, cli_runner):
        """Test deleting a Turso connection."""
        connection_name = "test_delete_turso"

        # Handle both cloud (tuple) and docker (string) modes
        if isinstance(turso_db, tuple):
            turso_url, auth_token = turso_db
        else:
            turso_url = turso_db
            auth_token = ""

        cli_runner(
            "connections",
            "add",
            "turso",
            "--name",
            connection_name,
            "--server",
            turso_url,
            "--password",
            auth_token,
        )

        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout

    def test_query_turso_invalid_query(self, turso_connection, cli_runner):
        """Test handling of invalid SQL query."""
        result = cli_runner(
            "query",
            "-c",
            turso_connection,
            "-q",
            "SELECT * FROM nonexistent_table",
            check=False,
        )
        assert result.returncode != 0
        assert "error" in result.stdout.lower() or "error" in result.stderr.lower()

    def test_expand_tables_folder(self, turso_connection):
        """Test expanding Tables folder (get_tables).

        This simulates what happens when a user clicks to expand the Tables
        folder in the database explorer tree.
        """
        from sqlit.config import load_connections
        from sqlit.db.adapters import get_adapter
        from sqlit.services.session import ConnectionSession

        connections = load_connections()
        config = next((c for c in connections if c.name == turso_connection), None)
        assert config is not None, f"Connection {turso_connection} not found"

        with ConnectionSession.create(config, get_adapter) as session:
            tables = session.adapter.get_tables(session.connection)

            # Should find our test tables
            table_names = [t[1] for t in tables]  # TableInfo is (schema, name)
            assert "test_users" in table_names, f"test_users not found in {table_names}"
            assert "test_products" in table_names, f"test_products not found in {table_names}"

    def test_expand_table_node(self, turso_connection):
        """Test expanding a table node to see columns (get_columns).

        This simulates what happens when a user clicks to expand a table
        in the database explorer tree to see its columns.
        """
        from sqlit.config import load_connections
        from sqlit.db.adapters import get_adapter
        from sqlit.services.session import ConnectionSession

        connections = load_connections()
        config = next((c for c in connections if c.name == turso_connection), None)
        assert config is not None, f"Connection {turso_connection} not found"

        with ConnectionSession.create(config, get_adapter) as session:
            # Expand test_users table
            columns = session.adapter.get_columns(session.connection, "test_users")

            assert len(columns) >= 3, f"Expected at least 3 columns, got {len(columns)}"

            column_names = [c.name for c in columns]
            assert "id" in column_names, f"id column not found in {column_names}"
            assert "name" in column_names, f"name column not found in {column_names}"
            assert "email" in column_names, f"email column not found in {column_names}"

            # Expand test_products table
            columns = session.adapter.get_columns(session.connection, "test_products")

            assert len(columns) >= 4, f"Expected at least 4 columns, got {len(columns)}"

            column_names = [c.name for c in columns]
            assert "id" in column_names
            assert "name" in column_names
            assert "price" in column_names
            assert "stock" in column_names

    def test_expand_views_folder(self, turso_connection):
        """Test expanding Views folder (get_views).

        This simulates what happens when a user clicks to expand the Views
        folder in the database explorer tree.
        """
        from sqlit.config import load_connections
        from sqlit.db.adapters import get_adapter
        from sqlit.services.session import ConnectionSession

        connections = load_connections()
        config = next((c for c in connections if c.name == turso_connection), None)
        assert config is not None, f"Connection {turso_connection} not found"

        with ConnectionSession.create(config, get_adapter) as session:
            views = session.adapter.get_views(session.connection)

            # Should find our test view
            view_names = [v[1] for v in views]  # ViewInfo is (schema, name)
            assert "test_user_emails" in view_names, f"test_user_emails not found in {view_names}"

    def test_write_persistence_across_connections(self, turso_connection):
        """Test that writes persist across separate connections.

        This is a critical test that verifies the adapter correctly commits
        writes to the remote Turso server, not just to a local cache.
        """
        import uuid

        from sqlit.config import load_connections
        from sqlit.db.adapters import get_adapter
        from sqlit.services.session import ConnectionSession

        connections = load_connections()
        config = next((c for c in connections if c.name == turso_connection), None)
        assert config is not None, f"Connection {turso_connection} not found"

        # Generate unique test value to avoid conflicts
        test_value = f"persistence_test_{uuid.uuid4().hex[:8]}"
        test_table = "write_persistence_test"

        # Connection 1: Create table and insert data
        with ConnectionSession.create(config, get_adapter) as session:
            # Create test table
            session.adapter.execute_non_query(
                session.connection,
                f"CREATE TABLE IF NOT EXISTS {test_table} (id INTEGER PRIMARY KEY, val TEXT)"
            )
            # Insert test data
            session.adapter.execute_non_query(
                session.connection,
                f"INSERT INTO {test_table} (val) VALUES ('{test_value}')"
            )

        # Connection 2: Verify data persisted (completely new connection)
        with ConnectionSession.create(config, get_adapter) as session:
            columns, rows, _ = session.adapter.execute_query(
                session.connection,
                f"SELECT val FROM {test_table} WHERE val = '{test_value}'"
            )

            assert len(rows) == 1, f"Expected 1 row with value '{test_value}', got {len(rows)} rows"
            assert rows[0][0] == test_value, f"Expected '{test_value}', got '{rows[0][0]}'"

            # Cleanup - drop the entire test table
            session.adapter.execute_non_query(
                session.connection,
                f"DROP TABLE IF EXISTS {test_table}"
            )
