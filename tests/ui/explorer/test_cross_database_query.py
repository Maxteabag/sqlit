"""Tests for cross-database query behavior in multi-database servers.

These tests verify that selecting a table from a different database
properly handles the database context for query execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from sqlit.domains.connections.providers.model import SchemaCapabilities
from sqlit.domains.explorer.domain.tree_nodes import TableNode
from sqlit.domains.explorer.ui.mixins.tree import TreeMixin


@dataclass
class MockEndpoint:
    """Mock TCP endpoint."""
    host: str = "localhost"
    port: int = 5432
    database: str = "norway_culture"
    username: str = "viking"
    password: str = "odin123"


class MockConfig:
    """Mock connection config."""

    def __init__(self, name: str = "test_conn", database: str = "norway_culture"):
        self.name = name
        self.db_type = "postgres"
        self._endpoint = MockEndpoint(database=database)

    @property
    def tcp_endpoint(self):
        return self._endpoint


class MockDialect:
    """Mock SQL dialect."""

    def __init__(self):
        self.last_query_database = None

    def build_select_query(
        self, table: str, limit: int, database: str | None = None, schema: str | None = None
    ) -> str:
        self.last_query_database = database
        schema_prefix = f"{schema}." if schema else ""
        return f"SELECT * FROM {schema_prefix}{table} LIMIT {limit}"


class MockTreeNode:
    """Mock tree node."""

    def __init__(self, label: str = "", data=None):
        self.label = label
        self.data = data
        self.children = []


class MockTree:
    """Mock Tree widget."""

    def __init__(self):
        self.root = MockTreeNode("root")
        self.cursor_node: MockTreeNode | None = None


class MockQueryInput:
    """Mock query input widget."""

    def __init__(self):
        self.text = ""


class TestCrossDatabaseQuery:
    """Tests for querying tables from different databases."""

    def _create_tree_mixin(
        self,
        connected_database: str = "norway_culture",
        supports_cross_db: bool = False,
    ):
        """Create a TreeMixin with mocked dependencies."""
        mixin = object.__new__(TreeMixin)

        # Mock provider with multi-database support but no cross-db queries (like PostgreSQL)
        mixin.current_provider = MagicMock()
        mixin.current_provider.capabilities = SchemaCapabilities(
            supports_multiple_databases=True,
            supports_cross_database_queries=supports_cross_db,
            supports_stored_procedures=False,
            supports_indexes=False,
            supports_triggers=False,
            supports_sequences=False,
            default_schema="public",
            system_databases=frozenset({"template0", "template1"}),
        )
        mixin.current_provider.dialect = MockDialect()
        mixin.current_provider.apply_database_override = MagicMock(
            side_effect=lambda config, _db: config  # Default: no override (like PostgreSQL)
        )

        # Mock session and connection
        mixin._session = MagicMock()
        mixin._session.provider = mixin.current_provider
        mixin.current_connection = MagicMock()
        mixin.current_config = MockConfig(database=connected_database)

        # Mock tree with cursor on a table from a DIFFERENT database
        mixin.object_tree = MockTree()
        mixin.query_input = MockQueryInput()

        # Mock methods
        mixin._get_node_kind = lambda node: "table" if isinstance(node.data, TableNode) else ""
        mixin._last_query_table = None
        mixin._prime_last_query_table_columns = MagicMock()
        mixin.action_execute_query = MagicMock()
        mixin._query_target_database = None

        return mixin

    def test_select_table_from_different_database_sets_target_database(self):
        """Selecting a table from database2 while connected to database1 should set target database.

        Scenario:
        - Connected to: norway_culture
        - Table selected: fjords (in norway_geography)
        - Expected: _query_target_database should be set to "norway_geography"
        """
        mixin = self._create_tree_mixin(connected_database="norway_culture")

        # Create a table node from a DIFFERENT database (norway_geography)
        table_node = MockTreeNode(
            label="fjords",
            data=TableNode(database="norway_geography", schema="public", name="fjords"),
        )
        mixin.object_tree.cursor_node = table_node

        # Execute action_select_table
        mixin.action_select_table()

        # Verify target database was set correctly
        assert mixin._query_target_database == "norway_geography", (
            f"Expected target database to be 'norway_geography' (where the table is), "
            f"but got '{mixin._query_target_database}'"
        )

    def test_select_table_from_different_database_without_cross_db_support_should_warn_or_switch(
        self,
    ):
        """When cross-database queries aren't supported, selecting from another database should handle it.

        Bug scenario:
        - Connected to: norway_culture (database1)
        - Table selected: fjords in norway_geography (database2)
        - PostgreSQL does NOT support cross-database queries
        - Current behavior: Query runs against norway_culture and FAILS

        Expected behavior (one of):
        a) Switch connection to norway_geography before executing, OR
        b) Warn user that cross-database queries aren't supported, OR
        c) apply_database_override creates a new connection to the target database

        This test verifies option (c) - that apply_database_override is called
        and should modify the config to point to the target database.
        """
        mixin = self._create_tree_mixin(
            connected_database="norway_culture",
            supports_cross_db=False,  # PostgreSQL-like behavior
        )

        # Track what config is passed to execute_query
        executed_configs = []
        original_execute = mixin.action_execute_query

        def track_execute():
            # The config should have been overridden to target norway_geography
            executed_configs.append(mixin._query_target_database)
            original_execute()

        mixin.action_execute_query = track_execute

        # Create a table node from norway_geography
        table_node = MockTreeNode(
            label="fjords",
            data=TableNode(database="norway_geography", schema="public", name="fjords"),
        )
        mixin.object_tree.cursor_node = table_node

        # Execute action_select_table
        mixin.action_select_table()

        # Verify the query was built with the correct database context
        assert mixin.current_provider.dialect.last_query_database == "norway_geography", (
            "Query should be built targeting norway_geography database"
        )

        # The bug: apply_database_override does nothing for PostgreSQL,
        # so the query runs against norway_culture and fails.
        #
        # This test documents the expected behavior:
        # When supports_cross_database_queries=False and we're querying a table
        # from a different database, the system should either:
        # 1. Override the connection to use the target database, OR
        # 2. Prevent the action and notify the user

        # For now, we verify that _query_target_database is at least set correctly
        # (the action_select_table part works)
        assert executed_configs[0] == "norway_geography"

    def test_postgres_apply_database_override_should_modify_config(self):
        """PostgreSQL should handle database override by modifying the connection config.

        BUG: PostgreSQL's apply_database_override returns the config unchanged,
        meaning queries against tables in other databases will fail with
        "relation does not exist" error.

        Scenario:
        - Connected to: norway_culture
        - User clicks on table 'fjords' in norway_geography
        - User presses 's' to SELECT TOP 100
        - Query runs against norway_culture (wrong!)
        - Error: relation "public.fjords" does not exist

        Expected: The config should be modified to connect to norway_geography
        so the query runs against the correct database.
        """
        from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter

        adapter = PostgreSQLAdapter()

        # Verify PostgreSQL doesn't support cross-database queries
        assert adapter.supports_cross_database_queries is False, (
            "PostgreSQL should not support cross-database queries"
        )

        # Create a config pointing to norway_culture
        from tests.helpers import ConnectionConfig

        original_config = ConnectionConfig.from_dict({
            "name": "norwegian-postgres",
            "db_type": "postgres",
            "server": "localhost",
            "port": "5434",
            "database": "norway_culture",
            "username": "viking",
            "password": "odin123",
        })

        # Call apply_database_override to switch to norway_geography
        overridden_config = adapter.apply_database_override(original_config, "norway_geography")

        # BUG: This assertion FAILS because apply_database_override returns unchanged config
        # The fix should make this pass by returning a config with database="norway_geography"
        assert overridden_config.tcp_endpoint.database == "norway_geography", (
            "apply_database_override should modify config to use target database. "
            f"Expected database='norway_geography', got '{overridden_config.tcp_endpoint.database}'. "
            "This causes queries on tables from other databases to fail with 'relation does not exist'."
        )


class TestSameDatabaseQuery:
    """Tests for querying tables from the same (connected) database."""

    def test_select_table_from_same_database_works(self):
        """Selecting a table from the connected database should work normally."""
        mixin = object.__new__(TreeMixin)

        mixin.current_provider = MagicMock()
        mixin.current_provider.capabilities = SchemaCapabilities(
            supports_multiple_databases=True,
            supports_cross_database_queries=False,
            supports_stored_procedures=False,
            supports_indexes=False,
            supports_triggers=False,
            supports_sequences=False,
            default_schema="public",
            system_databases=frozenset(),
        )
        mixin.current_provider.dialect = MockDialect()

        mixin._session = MagicMock()
        mixin._session.provider = mixin.current_provider
        mixin.current_connection = MagicMock()
        mixin.current_config = MockConfig(database="norway_culture")

        mixin.object_tree = MockTree()
        mixin.query_input = MockQueryInput()

        mixin._get_node_kind = lambda node: "table" if isinstance(node.data, TableNode) else ""
        mixin._last_query_table = None
        mixin._prime_last_query_table_columns = MagicMock()
        mixin.action_execute_query = MagicMock()
        mixin._query_target_database = None

        # Table from SAME database as connection
        table_node = MockTreeNode(
            label="traditional_foods",
            data=TableNode(database="norway_culture", schema="public", name="traditional_foods"),
        )
        mixin.object_tree.cursor_node = table_node

        mixin.action_select_table()

        # Target database matches connected database - no override needed
        assert mixin._query_target_database == "norway_culture"
        assert mixin.action_execute_query.called
