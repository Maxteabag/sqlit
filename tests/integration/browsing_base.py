"""Shared helpers and base class for database browsing flow tests."""

from __future__ import annotations

import os
import tempfile
import time
from typing import Any

import pytest

from sqlit.domains.explorer.domain.tree_nodes import (
    ConnectionNode,
    DatabaseNode,
    FolderNode,
    LoadingNode,
    SchemaNode,
    TableNode,
)
from sqlit.domains.shell.app.main import SSMSTUI
from tests.helpers import ConnectionConfig


async def wait_for_condition(
    pilot: Any,
    condition: callable,
    timeout_seconds: float = 10.0,
    poll_interval: float = 0.1,
    description: str = "",
) -> bool:
    """Wait for a condition to become true with timeout."""
    start = time.monotonic()
    while time.monotonic() - start < timeout_seconds:
        if condition():
            return True
        await pilot.pause(poll_interval)
    raise AssertionError(f"Timed out waiting for: {description or 'condition'}")


def find_node_by_type(node: Any, node_type: type, name: str | None = None) -> Any | None:
    """Recursively find a node by its data type and optionally name."""
    if node.data and isinstance(node.data, node_type):
        if name is None:
            return node
        if hasattr(node.data, "name") and node.data.name == name:
            return node
    for child in node.children:
        result = find_node_by_type(child, node_type, name)
        if result:
            return result
    return None


def find_database_node(tree_root: Any, db_name: str) -> Any | None:
    """Find a database node by name."""
    for child in tree_root.children:
        result = find_node_by_type(child, DatabaseNode, db_name)
        if result:
            return result
    return None


def find_folder_node(parent: Any, folder_type: str) -> Any | None:
    """Find a folder node (Tables, Views, etc.) under a parent."""
    for child in parent.children:
        if isinstance(child.data, FolderNode) and child.data.folder_type == folder_type:
            return child
    return None


def has_loading_children(node: Any) -> bool:
    """Check if a node has a loading placeholder child."""
    for child in node.children:
        if isinstance(child.data, LoadingNode):
            return True
    return False


def has_table_children(node: Any) -> bool:
    """Check if a node has TableNode children (directly or under schema folders)."""
    for child in node.children:
        if isinstance(child.data, TableNode):
            return True
        # Check under schema folders
        if isinstance(child.data, SchemaNode):
            for schema_child in child.children:
                if isinstance(schema_child.data, TableNode):
                    return True
    return False


def find_table_node(parent: Any, table_name: str) -> Any | None:
    """Find a table node by name, checking both direct children and schema folders."""
    for child in parent.children:
        if isinstance(child.data, TableNode) and child.data.name == table_name:
            return child
        # Check under schema folders
        if isinstance(child.data, SchemaNode):
            for schema_child in child.children:
                if isinstance(schema_child.data, TableNode) and schema_child.data.name == table_name:
                    return schema_child
    return None


class BaseDatabaseBrowsingTest:
    """Base class for database browsing tests."""

    # Subclasses must set these
    DB_TYPE: str = ""
    TEST_DATABASE: str = ""  # The database containing test tables
    SERVER_HOST: str = "localhost"
    SERVER_PORT: str = ""
    USERNAME: str = ""
    PASSWORD: str = ""

    # Whether this provider supports cross-database queries
    # MySQL, MariaDB, MSSQL: True
    # PostgreSQL, CockroachDB: False (each DB is isolated)
    SUPPORTS_CROSS_DB_QUERIES: bool = True

    # Whether this provider can fetch table metadata from other databases
    # MySQL, MariaDB, MSSQL: True
    # PostgreSQL, CockroachDB: False (can only see tables in connected database)
    CAN_FETCH_CROSS_DB_TABLES: bool = True

    @pytest.fixture
    def connection_config(self) -> ConnectionConfig:
        """Create a connection config with empty database field."""
        return ConnectionConfig(
            name=f"test-browse-{self.DB_TYPE}",
            db_type=self.DB_TYPE,
            server=self.SERVER_HOST,
            port=self.SERVER_PORT,
            database="",  # Empty to browse all databases
            username=self.USERNAME,
            password=self.PASSWORD,
        )

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary config directory for tests."""
        with tempfile.TemporaryDirectory(prefix="sqlit-test-") as tmpdir:
            original = os.environ.get("SQLIT_CONFIG_DIR")
            os.environ["SQLIT_CONFIG_DIR"] = tmpdir
            yield tmpdir
            if original:
                os.environ["SQLIT_CONFIG_DIR"] = original
            else:
                os.environ.pop("SQLIT_CONFIG_DIR", None)

    @pytest.mark.asyncio
    async def test_browse_all_databases_and_query(self, connection_config: ConnectionConfig, temp_config_dir: str):
        """Test: Connect without database, browse to DB, expand Tables, run query.

        For providers that don't support cross-database queries (PostgreSQL, CockroachDB),
        we only test tree navigation, not query execution.
        """
        app = SSMSTUI()

        async with app.run_test(size=(120, 40)) as pilot:
            # Wait for app to mount
            await pilot.pause(0.1)

            # Set connections AFTER mount (on_mount loads from disk, overwriting pre-set values)
            app.connections = [connection_config]
            app.refresh_tree()
            await pilot.pause(0.1)

            # Wait for tree to be populated
            await wait_for_condition(
                pilot,
                lambda: len(app.object_tree.root.children) > 0,
                timeout_seconds=5.0,
                description="tree to be populated with connections",
            )

            # Step 1: Get the connection node from the tree
            cursor_node = app.object_tree.root.children[0]
            assert cursor_node is not None
            assert isinstance(cursor_node.data, ConnectionNode)

            # Connect to the server
            app.connect_to_server(connection_config)
            await pilot.pause(0.5)

            # Step 2: Wait for connection and tree population
            # The tree should now show the connection with a "Databases" folder
            await wait_for_condition(
                pilot,
                lambda: app.current_connection is not None,
                timeout_seconds=15.0,
                description="connection to be established",
            )

            # Step 3: Verify database list is shown
            # The connected node should have children (Databases folder with databases)
            connected_node = None
            for child in app.object_tree.root.children:
                if isinstance(child.data, ConnectionNode) and child.data.config.name == connection_config.name:
                    connected_node = child
                    break
            assert connected_node is not None, "Connected node not found"

            # Wait for tree to be populated with databases
            await wait_for_condition(
                pilot,
                lambda: len(connected_node.children) > 0,
                timeout_seconds=10.0,
                description="tree to be populated",
            )

            # Find the test database node
            db_node = find_database_node(app.object_tree.root, self.TEST_DATABASE)
            assert db_node is not None, f"Database '{self.TEST_DATABASE}' not found in tree"

            # For providers that can't fetch cross-database tables (PostgreSQL, CockroachDB),
            # we can only verify that databases are visible. We can't expand tables from
            # other databases because the adapter can only see tables in the connected database.
            if not self.CAN_FETCH_CROSS_DB_TABLES:
                # Test passes - we verified connection and database visibility
                return

            # Step 4: Expand the database node to see Tables/Views
            db_node.expand()
            await pilot.pause(0.3)

            # Find the Tables folder
            tables_folder = find_folder_node(db_node, "tables")
            assert tables_folder is not None, "Tables folder not found"

            # Step 5: Expand Tables folder
            tables_folder.expand()
            await pilot.pause(0.5)

            # Wait for tables to load (not just the loading placeholder)
            await wait_for_condition(
                pilot,
                lambda: not has_loading_children(tables_folder) and len(tables_folder.children) > 0,
                timeout_seconds=10.0,
                description="tables to be loaded",
            )

            # Step 6: Verify tables are visible
            assert has_table_children(tables_folder), "No tables found in Tables folder"

            # Find our test table
            table_node = find_table_node(tables_folder, "test_users")
            assert table_node is not None, "test_users table not found"

            # Step 7: Execute a query (only for providers that support cross-DB queries)
            if self.SUPPORTS_CROSS_DB_QUERIES:
                # Use the adapter's build_select_query to get the right syntax
                query = app.current_adapter.build_select_query(
                    "test_users", 100, table_node.data.database, table_node.data.schema
                )
                app.query_input.text = query

                # Execute the query
                app.action_execute_query()
                await pilot.pause(0.5)

                # Wait for query to complete
                await wait_for_condition(
                    pilot,
                    lambda: not getattr(app, "_query_executing", False),
                    timeout_seconds=15.0,
                    description="query to complete",
                )

                # Step 8: Verify results
                # Check that we got some results (the test_users table should have data)
                assert app._last_result_row_count > 0, "Query returned no results"
                assert "name" in [col.lower() for col in app._last_result_columns], "Expected 'name' column in results"
