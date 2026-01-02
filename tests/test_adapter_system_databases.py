"""Unit tests for adapter system_databases property."""



class TestSystemDatabasesProperty:
    """Test that each adapter correctly defines system_databases."""

    def test_base_adapter_returns_empty(self):
        """Base DatabaseAdapter should return empty frozenset."""
        from sqlit.domains.connections.providers.adapters.base import DatabaseAdapter

        # Create a minimal concrete implementation to test the base class
        class ConcreteAdapter(DatabaseAdapter):
            @property
            def name(self) -> str:
                return "Test"

            @property
            def supports_multiple_databases(self) -> bool:
                return True

            @property
            def supports_stored_procedures(self) -> bool:
                return False

            def connect(self, config):
                pass

            def get_databases(self, conn):
                return []

            def get_tables(self, conn, database=None):
                return []

            def get_views(self, conn, database=None):
                return []

            def get_columns(self, conn, table, database=None, schema=None):
                return []

            def get_procedures(self, conn, database=None):
                return []

            def get_indexes(self, conn, database=None):
                return []

            def get_triggers(self, conn, database=None):
                return []

            def get_sequences(self, conn, database=None):
                return []

            def quote_identifier(self, name):
                return f'"{name}"'

            def build_select_query(self, table, limit, database=None, schema=None):
                return f"SELECT * FROM {table} LIMIT {limit}"

            def execute_query(self, conn, query, max_rows=None):
                return [], [], False

            def execute_non_query(self, conn, query):
                return 0

        adapter = ConcreteAdapter()
        assert adapter.system_databases == frozenset()

    def test_mssql_system_databases(self):
        """SQL Server adapter should exclude master, tempdb, model, msdb."""
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

        adapter = SQLServerAdapter()
        expected = frozenset({"master", "tempdb", "model", "msdb"})
        assert adapter.system_databases == expected

    def test_postgresql_system_databases(self):
        """PostgreSQL adapter should exclude template0, template1."""
        from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter

        adapter = PostgreSQLAdapter()
        expected = frozenset({"template0", "template1"})
        assert adapter.system_databases == expected

    def test_cockroachdb_inherits_postgres_system_databases(self):
        """CockroachDB inherits PostgreSQL's system_databases."""
        from sqlit.domains.connections.providers.cockroachdb.adapter import CockroachDBAdapter

        adapter = CockroachDBAdapter()
        expected = frozenset({"template0", "template1"})
        assert adapter.system_databases == expected

    def test_mysql_system_databases(self):
        """MySQL adapter should exclude mysql, information_schema, performance_schema, sys."""
        from sqlit.domains.connections.providers.mysql.adapter import MySQLAdapter

        adapter = MySQLAdapter()
        expected = frozenset({"mysql", "information_schema", "performance_schema", "sys"})
        assert adapter.system_databases == expected

    def test_mariadb_inherits_mysql_system_databases(self):
        """MariaDB inherits MySQL's system_databases."""
        from sqlit.domains.connections.providers.mariadb.adapter import MariaDBAdapter

        adapter = MariaDBAdapter()
        expected = frozenset({"mysql", "information_schema", "performance_schema", "sys"})
        assert adapter.system_databases == expected

    def test_clickhouse_system_databases(self):
        """ClickHouse adapter should exclude system, information_schema."""
        from sqlit.domains.connections.providers.clickhouse.adapter import ClickHouseAdapter

        adapter = ClickHouseAdapter()
        assert "system" in adapter.system_databases
        assert "information_schema" in adapter.system_databases or "INFORMATION_SCHEMA" in adapter.system_databases

    def test_snowflake_system_databases(self):
        """Snowflake adapter should exclude SNOWFLAKE metadata database."""
        from sqlit.domains.connections.providers.snowflake.adapter import SnowflakeAdapter

        adapter = SnowflakeAdapter()
        # Case-insensitive: either SNOWFLAKE or snowflake should be present
        lowercase_dbs = {s.lower() for s in adapter.system_databases}
        assert "snowflake" in lowercase_dbs

    def test_sqlite_no_system_databases(self):
        """SQLite (single-file) should return empty frozenset."""
        from sqlit.domains.connections.providers.sqlite.adapter import SQLiteAdapter

        adapter = SQLiteAdapter()
        assert adapter.system_databases == frozenset()
        # Also verify it doesn't support multiple databases
        assert adapter.supports_multiple_databases is False

    def test_duckdb_no_system_databases(self):
        """DuckDB (single-file) should return empty frozenset."""
        from sqlit.domains.connections.providers.duckdb.adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        assert adapter.system_databases == frozenset()
        assert adapter.supports_multiple_databases is False

    def test_turso_no_system_databases(self):
        """Turso (SQLite-based) should return empty frozenset."""
        from sqlit.domains.connections.providers.turso.adapter import TursoAdapter

        adapter = TursoAdapter()
        assert adapter.system_databases == frozenset()
        assert adapter.supports_multiple_databases is False

    def test_oracle_no_system_databases(self):
        """Oracle (single-database with schemas) should return empty frozenset."""
        from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

        adapter = OracleAdapter()
        assert adapter.system_databases == frozenset()
        assert adapter.supports_multiple_databases is False


class TestSystemDatabasesFiltering:
    """Test that system_databases filtering works correctly."""

    def test_lowercase_comparison(self):
        """System databases should be compared case-insensitively."""
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

        adapter = SQLServerAdapter()
        system_dbs = {s.lower() for s in adapter.system_databases}

        # These should all be filtered out
        all_dbs = ["master", "MASTER", "Master", "tempdb", "TEMPDB", "userdb"]
        filtered = [d for d in all_dbs if d.lower() not in system_dbs]

        assert "userdb" in filtered
        assert len(filtered) == 1

    def test_filtering_preserves_user_databases(self):
        """Filtering should keep all non-system databases."""
        from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter

        adapter = PostgreSQLAdapter()
        system_dbs = {s.lower() for s in adapter.system_databases}

        all_dbs = ["postgres", "myapp", "template0", "template1", "analytics"]
        filtered = [d for d in all_dbs if d.lower() not in system_dbs]

        assert "postgres" in filtered
        assert "myapp" in filtered
        assert "analytics" in filtered
        assert "template0" not in filtered
        assert "template1" not in filtered
        assert len(filtered) == 3

    def test_empty_system_databases_filters_nothing(self):
        """Empty system_databases should not filter any databases."""
        from sqlit.domains.connections.providers.sqlite.adapter import SQLiteAdapter

        adapter = SQLiteAdapter()
        system_dbs = {s.lower() for s in adapter.system_databases}

        all_dbs = ["db1", "db2", "system", "master"]
        filtered = [d for d in all_dbs if d.lower() not in system_dbs]

        assert filtered == all_dbs


class TestSystemDatabasesInterface:
    """Test that system_databases property has correct interface."""

    def test_returns_frozenset(self):
        """system_databases should return a frozenset (immutable)."""
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter
        from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter

        for AdapterClass in [SQLServerAdapter, PostgreSQLAdapter]:
            adapter = AdapterClass()
            assert isinstance(adapter.system_databases, frozenset)

    def test_property_is_idempotent(self):
        """Multiple calls to system_databases should return same object."""
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

        adapter = SQLServerAdapter()
        first_call = adapter.system_databases
        second_call = adapter.system_databases

        assert first_call == second_call
        # frozensets are immutable so this is safe
        assert first_call is not None
