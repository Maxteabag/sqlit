"""Integration tests for SurrealDB database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestSurrealDBIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for SurrealDB database operations via CLI.

    These tests require a running SurrealDB instance (via Docker).
    Tests are skipped if SurrealDB is not available.

    SurrealQL divergence notes (may cause base tests to fail/behave differently):
      - Record IDs are returned as ``test_users:1`` rather than plain ``1``;
        views (DEFINE TABLE ... AS SELECT) are not reported by
        ``get_views`` (the adapter returns []), so ``test_query_view`` still
        runs as a raw SurrealQL SELECT but tree-level view discovery is
        intentionally empty.
      - SurrealQL aggregate syntax differs: ``SELECT COUNT(*) as user_count``
        returns ``count: 1`` per row rather than a single aggregated row, so
        ``test_query_aggregate`` may produce different output.
      - ``test_get_trigger_definition`` / ``test_get_sequence_definition``
        auto-skip because SurrealDB advertises
        ``supports_triggers=False`` and ``supports_sequences=False``.
      - ``INSERT INTO ... VALUES`` is accepted by SurrealQL but stores rows
        under auto-assigned record IDs, so ``test_query_insert`` should pass
        but the returned ``id`` looks like ``test_users:4``.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="surrealdb",
            display_name="SurrealDB",
            connection_fixture="surrealdb_connection",
            db_fixture="surrealdb_db",
            create_connection_args=lambda: [],  # Uses fixtures
        )

    def test_query_with_where(self, request, cli_runner):
        """SurrealQL variant of the base WHERE test.

        In SurrealDB ``id`` is a ``RecordID`` (``test_users:1``) not an int,
        so the base test's ``WHERE id = 1`` matches nothing. Query by ``name``
        instead, which still exercises the WHERE + column-projection path.
        """
        connection = request.getfixturevalue(self.config.connection_fixture)
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT name, email FROM test_users WHERE name = 'Alice'",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "alice@example.com" in result.stdout
        assert "1 row(s) returned" in result.stdout

    def test_query_aggregate(self, request, cli_runner):
        """SurrealQL variant of the base aggregate test.

        SurrealQL spells COUNT(*) as ``count()`` and requires ``GROUP ALL``
        to collapse into a single aggregate row.
        """
        connection = request.getfixturevalue(self.config.connection_fixture)
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT count() AS user_count FROM test_users GROUP ALL",
        )
        assert result.returncode == 0
        assert "3" in result.stdout

    def test_query_insert(self, request, cli_runner):
        """SurrealQL variant of the base INSERT/SELECT-back test.

        SurrealQL's CREATE assigns ``test_users:4``-style RecordIDs, so the
        read-back uses ``name`` rather than a numeric id comparison.
        """
        connection = request.getfixturevalue(self.config.connection_fixture)
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "CREATE test_users:4 SET name = 'David', email = 'david@example.com'",
        )
        assert result.returncode == 0

        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT name, email FROM test_users WHERE name = 'David'",
        )
        assert result.returncode == 0
        assert "David" in result.stdout
        assert "david@example.com" in result.stdout

    def test_create_surrealdb_connection(self, surrealdb_db, cli_runner):
        """Test creating a SurrealDB connection via CLI."""
        from tests.fixtures.surrealdb import (
            SURREALDB_HOST,
            SURREALDB_NAMESPACE,
            SURREALDB_PASSWORD,
            SURREALDB_PORT,
            SURREALDB_USER,
        )

        connection_name = "test_create_surrealdb"

        try:
            result = cli_runner(
                "connections",
                "add",
                "surrealdb",
                "--name",
                connection_name,
                "--server",
                SURREALDB_HOST,
                "--port",
                str(SURREALDB_PORT),
                "--namespace",
                SURREALDB_NAMESPACE,
                "--database",
                surrealdb_db,
                "--username",
                SURREALDB_USER,
                "--password",
                SURREALDB_PASSWORD,
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "SurrealDB" in result.stdout

        finally:
            cli_runner("connection", "delete", connection_name, check=False)

    def test_create_surrealdb_connection_with_ssl(self, cli_runner):
        """Test creating a SurrealDB connection with --use-ssl (wss:// scheme).

        Verifies the use_ssl option (which switches the URL scheme from
        ws:// to wss://) is accepted by the CLI. Doesn't actually connect
        because we'd need a TLS-terminated endpoint, but confirms the
        schema field round-trips through the CLI and is stored.
        """
        from sqlit.domains.connections.store.connections import load_connections
        from tests.fixtures.surrealdb import (
            SURREALDB_HOST,
            SURREALDB_NAMESPACE,
            SURREALDB_PASSWORD,
            SURREALDB_PORT,
            SURREALDB_USER,
        )

        connection_name = "test_surrealdb_ssl"

        try:
            result = cli_runner(
                "connections",
                "add",
                "surrealdb",
                "--name",
                connection_name,
                "--server",
                SURREALDB_HOST,
                "--port",
                str(SURREALDB_PORT),
                "--namespace",
                SURREALDB_NAMESPACE,
                "--database",
                "test_sqlit",
                "--username",
                SURREALDB_USER,
                "--password",
                SURREALDB_PASSWORD,
                "--use-ssl",
                "true",
            )
            assert result.returncode == 0, f"stdout={result.stdout} stderr={result.stderr}"
            assert "created successfully" in result.stdout

            # Verify the option persisted
            connections = load_connections()
            config = next((c for c in connections if c.name == connection_name), None)
            assert config is not None
            assert str(config.get_option("use_ssl", "false")).lower() == "true"

        finally:
            cli_runner("connection", "delete", connection_name, check=False)

    def test_surrealql_record_id_format(self, surrealdb_connection, cli_runner):
        """Test that SurrealQL record IDs are returned in SurrealDB-specific
        ``table:id`` form.

        This is SurrealQL-specific behaviour that distinguishes it from
        standard SQL — record IDs are first-class typed values, not plain
        integers.
        """
        result = cli_runner(
            "query",
            "-c",
            surrealdb_connection,
            "-q",
            "SELECT id FROM test_users WHERE name = 'Alice'",
        )
        assert result.returncode == 0
        # The id should appear in table:id format (e.g. test_users:1).
        # Accept either stringified repr that contains the table name.
        assert "test_users" in result.stdout

    def test_surrealdb_namespace_database_switching(self, surrealdb_db):
        """Test that the adapter correctly switches namespace/database on
        connect based on connection options.

        SurrealDB uses a namespace/database hierarchy rather than SQL
        schemas; this confirms both levels are applied when opening a
        session.
        """
        from sqlit.domains.connections.app.session import ConnectionSession
        from sqlit.domains.connections.domain.config import ConnectionConfig
        from sqlit.domains.connections.providers.config_service import (
            normalize_connection_config,
        )
        from sqlit.domains.connections.providers.registry import get_adapter
        from tests.fixtures.surrealdb import (
            SURREALDB_HOST,
            SURREALDB_NAMESPACE,
            SURREALDB_PASSWORD,
            SURREALDB_PORT,
            SURREALDB_USER,
        )

        config = normalize_connection_config(
            ConnectionConfig.from_dict(
                {
                    "name": "inline_surrealdb_ns_test",
                    "db_type": "surrealdb",
                    "namespace": SURREALDB_NAMESPACE,
                    "use_ssl": "false",
                    "endpoint": {
                        "kind": "tcp",
                        "host": SURREALDB_HOST,
                        "port": str(SURREALDB_PORT),
                        "database": surrealdb_db,
                        "username": SURREALDB_USER,
                        "password": SURREALDB_PASSWORD,
                    },
                }
            )
        )

        with ConnectionSession.create(config, get_adapter) as session:
            tables = session.adapter.get_tables(session.connection)
            table_names = [t[1] for t in tables]
            assert "test_users" in table_names, (
                f"Expected test_users in namespace/{surrealdb_db}; got {table_names}"
            )
