"""Tests for supports_cross_database_queries property and validation."""

import pytest


class TestCrossDatabaseQueriesProperty:
    """Test the supports_cross_database_queries adapter property."""

    def test_base_adapter_defaults_to_true(self):
        """Base DatabaseAdapter should default to True (supports cross-db queries)."""
        from sqlit.db.adapters.base import DatabaseAdapter

        # Create a minimal concrete implementation for testing
        class TestAdapter(DatabaseAdapter):
            @property
            def name(self):
                return "Test"

            @property
            def supports_multiple_databases(self):
                return True

            @property
            def supports_stored_procedures(self):
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

        adapter = TestAdapter()
        assert adapter.supports_cross_database_queries is True

    def test_mssql_supports_cross_database_queries(self):
        """MSSQL adapter should support cross-database queries."""
        from sqlit.db.adapters.mssql import SQLServerAdapter

        adapter = SQLServerAdapter()
        assert adapter.supports_cross_database_queries is True

    def test_mysql_supports_cross_database_queries(self):
        """MySQL adapter should support cross-database queries."""
        from sqlit.db.adapters.mysql import MySQLAdapter

        adapter = MySQLAdapter()
        assert adapter.supports_cross_database_queries is True

    def test_postgresql_does_not_support_cross_database_queries(self):
        """PostgreSQL adapter should NOT support cross-database queries."""
        from sqlit.db.adapters.postgresql import PostgreSQLAdapter

        adapter = PostgreSQLAdapter()
        assert adapter.supports_cross_database_queries is False

    def test_cockroachdb_does_not_support_cross_database_queries(self):
        """CockroachDB adapter (extends PostgresBaseAdapter) should NOT support cross-db queries."""
        from sqlit.db.adapters.cockroachdb import CockroachDBAdapter

        adapter = CockroachDBAdapter()
        assert adapter.supports_cross_database_queries is False

    def test_d1_does_not_support_cross_database_queries(self):
        """D1 adapter should NOT support cross-database queries."""
        from sqlit.db.adapters.d1 import D1Adapter

        adapter = D1Adapter()
        assert adapter.supports_cross_database_queries is False

    def test_clickhouse_supports_cross_database_queries(self):
        """ClickHouse adapter should support cross-database queries."""
        from sqlit.db.adapters.clickhouse import ClickHouseAdapter

        adapter = ClickHouseAdapter()
        assert adapter.supports_cross_database_queries is True

    def test_snowflake_supports_cross_database_queries(self):
        """Snowflake adapter should support cross-database queries."""
        from sqlit.db.adapters.snowflake import SnowflakeAdapter

        adapter = SnowflakeAdapter()
        assert adapter.supports_cross_database_queries is True

    def test_mariadb_supports_cross_database_queries(self):
        """MariaDB adapter should support cross-database queries."""
        from sqlit.db.adapters.mariadb import MariaDBAdapter

        adapter = MariaDBAdapter()
        assert adapter.supports_cross_database_queries is True


class TestRequiresDatabaseSelection:
    """Test the requires_database_selection helper function."""

    def test_postgresql_requires_database_selection(self):
        """PostgreSQL should require database selection."""
        from sqlit.db.providers import requires_database_selection

        assert requires_database_selection("postgresql") is True

    def test_cockroachdb_requires_database_selection(self):
        """CockroachDB should require database selection."""
        from sqlit.db.providers import requires_database_selection

        assert requires_database_selection("cockroachdb") is True

    def test_d1_requires_database_selection(self):
        """D1 should require database selection."""
        from sqlit.db.providers import requires_database_selection

        assert requires_database_selection("d1") is True

    def test_mssql_does_not_require_database_selection(self):
        """MSSQL should NOT require database selection."""
        from sqlit.db.providers import requires_database_selection

        assert requires_database_selection("mssql") is False

    def test_mysql_does_not_require_database_selection(self):
        """MySQL should NOT require database selection."""
        from sqlit.db.providers import requires_database_selection

        assert requires_database_selection("mysql") is False

    def test_clickhouse_does_not_require_database_selection(self):
        """ClickHouse should NOT require database selection."""
        from sqlit.db.providers import requires_database_selection

        assert requires_database_selection("clickhouse") is False

    def test_unknown_db_type_returns_false(self):
        """Unknown database type should return False (fail open)."""
        from sqlit.db.providers import requires_database_selection

        assert requires_database_selection("unknown_db_type") is False


class TestValidateDatabaseRequired:
    """Test the validate_database_required helper function."""

    def test_validate_database_required_raises_when_needed(self):
        """validate_database_required raises for databases that need it."""
        from sqlit.db.providers import validate_database_required

        # PostgreSQL requires database but validation doesn't block - user selects in explorer
        # This is now a no-op for UI flow, but still useful for programmatic validation
        with pytest.raises(ValueError):
            validate_database_required("postgresql", None)

    def test_validate_database_required_passes_with_database(self):
        """validate_database_required passes when database is provided."""
        from sqlit.db.providers import validate_database_required

        # Should not raise
        validate_database_required("postgresql", "mydb")

    def test_validate_database_required_passes_for_cross_db_adapters(self):
        """validate_database_required passes for adapters supporting cross-db queries."""
        from sqlit.db.providers import validate_database_required

        # Should not raise - MSSQL supports cross-database queries
        validate_database_required("mssql", None)
        validate_database_required("mssql", "")
