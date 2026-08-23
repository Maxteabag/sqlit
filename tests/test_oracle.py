"""Integration tests for Oracle database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTests, DatabaseTestConfig


class TestOracleIntegration(BaseDatabaseTests):
    """Integration tests for Oracle database operations via CLI.

    These tests require a running Oracle instance (via Docker).
    Tests are skipped if Oracle is not available.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="oracle",
            display_name="Oracle",
            connection_fixture="oracle_connection",
            db_fixture="oracle_db",
            create_connection_args=lambda: [],  # Uses fixtures
            uses_limit=False,  # Oracle uses FETCH FIRST instead of LIMIT
            timezone_datetime_type="TIMESTAMP WITH TIME ZONE",
        )

    def test_create_oracle_connection(self, oracle_db, cli_runner):
        """Test creating an Oracle connection via CLI."""
        from .conftest import ORACLE_HOST, ORACLE_PASSWORD, ORACLE_PORT, ORACLE_USER

        connection_name = "test_create_oracle"

        try:
            # Create connection
            result = cli_runner(
                "connections",
                "add",
                "oracle",
                "--name",
                connection_name,
                "--server",
                ORACLE_HOST,
                "--port",
                str(ORACLE_PORT),
                "--database",
                oracle_db,
                "--username",
                ORACLE_USER,
                "--password",
                ORACLE_PASSWORD,
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "Oracle" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_create_oracle_connection_with_role(self, oracle_db, cli_runner):
        """Test creating an Oracle connection with --oracle-role parameter."""
        from .conftest import ORACLE_HOST, ORACLE_PASSWORD, ORACLE_PORT, ORACLE_USER

        connection_name = "test_oracle_role"

        try:
            # Create connection with role parameter
            result = cli_runner(
                "connections",
                "add",
                "oracle",
                "--name",
                connection_name,
                "--server",
                ORACLE_HOST,
                "--port",
                str(ORACLE_PORT),
                "--database",
                oracle_db,
                "--username",
                ORACLE_USER,
                "--password",
                ORACLE_PASSWORD,
                "--oracle-role",
                "normal",
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify connection works with normal role
            result = cli_runner(
                "query",
                "-c",
                connection_name,
                "-q",
                "SELECT 1 FROM dual",
            )
            assert result.returncode == 0

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_oracle_role_choices(self, oracle_db, cli_runner):
        """Test that invalid oracle-role values are rejected."""
        from .conftest import ORACLE_HOST, ORACLE_PASSWORD, ORACLE_PORT, ORACLE_USER

        connection_name = "test_oracle_invalid_role"

        # Create connection with invalid role
        result = cli_runner(
            "connections",
            "add",
            "oracle",
            "--name",
            connection_name,
            "--server",
            ORACLE_HOST,
            "--port",
            str(ORACLE_PORT),
            "--database",
            oracle_db,
            "--username",
            ORACLE_USER,
            "--password",
            ORACLE_PASSWORD,
            "--oracle-role",
            "invalid_role",
            check=False,
        )
        # Should fail because invalid_role is not a valid choice
        assert result.returncode != 0
        assert "invalid choice" in result.stderr.lower() or "invalid" in result.stderr.lower()

    def test_query_oracle_fetch_first(self, oracle_connection, cli_runner):
        """Test Oracle FETCH FIRST clause (Oracle's equivalent of LIMIT)."""
        result = cli_runner(
            "query",
            "-c",
            oracle_connection,
            "-q",
            "SELECT * FROM test_users ORDER BY id FETCH FIRST 2 ROWS ONLY",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "Bob" in result.stdout
        assert "2 row(s) returned" in result.stdout

    def test_query_oracle_clob_returns_text(self, oracle_connection, cli_runner):
        """CLOB values must be fetched inline as text, not LOB locators.

        With oracledb's default fetch_lobs=True, rows contain LOB locator
        objects: the CLI renders their repr instead of the value, and the
        TUI's process worker hangs pickling them after the query connection
        is closed (issue #276).
        """
        result = cli_runner(
            "query",
            "-c",
            oracle_connection,
            "-q",
            "SELECT TO_CLOB('clob value ok') AS payload FROM DUAL",
        )
        assert result.returncode == 0
        assert "clob value ok" in result.stdout

    def test_schema_introspection_includes_granted_cross_schema_tables(self, oracle_db):
        """Tables granted from another schema must appear with usable columns."""
        import os

        import oracledb

        from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter
        from tests.fixtures.oracle import (
            ORACLE_HOST,
            ORACLE_PASSWORD,
            ORACLE_PORT,
            ORACLE_USER,
        )

        owner = "ISSUE295_OWNER"
        table = "SHARED_CUSTOMERS"
        dsn = f"{ORACLE_HOST}:{ORACLE_PORT}/{oracle_db}"
        admin = oracledb.connect(
            user="system",
            password=os.environ.get("ORACLE_ADMIN_PASSWORD", ORACLE_PASSWORD),
            dsn=dsn,
        )
        try:
            cursor = admin.cursor()
            try:
                try:
                    cursor.execute(f"DROP USER {owner} CASCADE")
                except oracledb.DatabaseError:
                    pass
                cursor.execute(f'CREATE USER {owner} IDENTIFIED BY "Issue295Password123!"')
                cursor.execute(f"ALTER USER {owner} QUOTA UNLIMITED ON USERS")
                cursor.execute(f"CREATE TABLE {owner}.{table} (id NUMBER PRIMARY KEY, name VARCHAR2(50))")
                cursor.execute(f"CREATE INDEX {owner}.IX_SHARED_NAME ON {owner}.{table} (name)")
                cursor.execute(f"CREATE TRIGGER {owner}.TRG_SHARED BEFORE INSERT ON {owner}.{table} FOR EACH ROW BEGIN NULL; END;")
                cursor.execute(f"CREATE SEQUENCE {owner}.SHARED_SEQ START WITH 1")
                cursor.execute(f"CREATE PROCEDURE {owner}.REFRESH_SHARED AS BEGIN NULL; END;")
                cursor.execute(f"GRANT SELECT ON {owner}.{table} TO {ORACLE_USER}")
                cursor.execute(f"GRANT SELECT ON {owner}.SHARED_SEQ TO {ORACLE_USER}")
                cursor.execute(f"GRANT EXECUTE ON {owner}.REFRESH_SHARED TO {ORACLE_USER}")
                admin.commit()

                user_conn = oracledb.connect(
                    user=ORACLE_USER,
                    password=ORACLE_PASSWORD,
                    dsn=dsn,
                )
                try:
                    adapter = OracleAdapter()
                    assert (owner, table) in adapter.get_tables(user_conn)
                    columns = adapter.get_columns(user_conn, table, schema=owner)
                    assert [(column.name, column.is_primary_key) for column in columns] == [
                        ("ID", True),
                        ("NAME", False),
                    ]
                    index = next(item for item in adapter.get_indexes(user_conn) if item.name == f"{owner}.IX_SHARED_NAME")
                    assert index.table_name == f"{owner}.{table}"
                    assert adapter.get_index_definition(user_conn, index.name, index.table_name)["columns"] == ["NAME"]
                    trigger = next(item for item in adapter.get_triggers(user_conn) if item.name == f"{owner}.TRG_SHARED")
                    assert adapter.get_trigger_definition(user_conn, trigger.name, trigger.table_name)["event"] == "INSERT"
                    sequence = next(item for item in adapter.get_sequences(user_conn) if item.name == f"{owner}.SHARED_SEQ")
                    assert adapter.get_sequence_definition(user_conn, sequence.name)["increment"] == 1
                    assert f"{owner}.REFRESH_SHARED" in adapter.get_procedures(user_conn)
                finally:
                    user_conn.close()
            finally:
                cursor.close()
        finally:
            try:
                cursor = admin.cursor()
                cursor.execute(f"DROP USER {owner} CASCADE")
                admin.commit()
                cursor.close()
            finally:
                admin.close()

    def test_delete_oracle_connection(self, oracle_db, cli_runner):
        """Test deleting an Oracle connection."""
        from .conftest import ORACLE_HOST, ORACLE_PASSWORD, ORACLE_PORT, ORACLE_USER

        connection_name = "test_delete_oracle"

        # Create connection first
        cli_runner(
            "connections",
            "add",
            "oracle",
            "--name",
            connection_name,
            "--server",
            ORACLE_HOST,
            "--port",
            str(ORACLE_PORT),
            "--database",
            oracle_db,
            "--username",
            ORACLE_USER,
            "--password",
            ORACLE_PASSWORD,
        )

        # Delete it
        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        # Verify it's gone
        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout
