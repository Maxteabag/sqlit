"""Integration tests for browsing all databases without pre-selecting one.

This test module verifies that when connecting with an empty database field:
1. The connection succeeds
2. All databases are visible in the explorer tree
3. Clicking on a database expands to show Tables/Views folders
4. Clicking on Tables shows the tables
5. Queries can be executed successfully (where supported)

Applicable providers: MySQL, PostgreSQL, MSSQL, MariaDB, CockroachDB
(All providers that support multiple databases)

Note: PostgreSQL and CockroachDB don't support cross-database queries.
When connected without a database, they connect to a default database (postgres/defaultdb)
and can only query tables in that database. For these providers, we test tree
navigation only.
"""

from __future__ import annotations

import os
import tempfile
import time
from typing import Any

import pytest

from sqlit.app import SSMSTUI
from sqlit.config import ConnectionConfig
from sqlit.ui.tree_nodes import (
    ConnectionNode,
    DatabaseNode,
    FolderNode,
    LoadingNode,
    SchemaNode,
    TableNode,
)

# ==============================================================================
# Test Helpers
# ==============================================================================


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


# ==============================================================================
# Base Test Class
# ==============================================================================


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


# ==============================================================================
# Provider-Specific Tests
# ==============================================================================


class TestMySQLDatabaseBrowsing(BaseDatabaseBrowsingTest):
    """Test database browsing for MySQL."""

    DB_TYPE = "mysql"
    TEST_DATABASE = os.environ.get("MYSQL_DATABASE", "test_sqlit")
    SERVER_HOST = os.environ.get("MYSQL_HOST", "localhost")
    SERVER_PORT = os.environ.get("MYSQL_PORT", "3306")
    USERNAME = os.environ.get("MYSQL_USER", "root")
    PASSWORD = os.environ.get("MYSQL_PASSWORD", "TestPassword123!")

    @pytest.fixture
    def connection_config(self) -> ConnectionConfig:
        return ConnectionConfig(
            name="test-browse-mysql",
            db_type="mysql",
            server=self.SERVER_HOST,
            port=self.SERVER_PORT,
            database="",  # Empty to browse all databases
            username=self.USERNAME,
            password=self.PASSWORD,
        )

    @pytest.fixture(autouse=True)
    def check_mysql_available(self, mysql_server_ready: bool, mysql_db: str):
        """Skip if MySQL is not available."""
        if not mysql_server_ready:
            pytest.skip("MySQL is not available")
        # Update TEST_DATABASE with the actual database name from fixture
        self.TEST_DATABASE = mysql_db

    @pytest.mark.asyncio
    async def test_browse_all_databases_and_query(self, connection_config: ConnectionConfig, temp_config_dir: str):
        """Test MySQL database browsing with empty database field."""
        await super().test_browse_all_databases_and_query(connection_config, temp_config_dir)


class TestPostgreSQLDatabaseBrowsing(BaseDatabaseBrowsingTest):
    """Test database browsing for PostgreSQL.

    Note: PostgreSQL doesn't support cross-database queries. Each database is isolated.
    When connected without a database, it connects to 'postgres' by default.
    We can see all databases but can only query tables in the connected database.
    """

    DB_TYPE = "postgresql"
    TEST_DATABASE = os.environ.get("POSTGRES_DATABASE", "test_sqlit")
    SERVER_HOST = os.environ.get("POSTGRES_HOST", "localhost")
    SERVER_PORT = os.environ.get("POSTGRES_PORT", "5432")
    USERNAME = os.environ.get("POSTGRES_USER", "testuser")
    PASSWORD = os.environ.get("POSTGRES_PASSWORD", "TestPassword123!")
    SUPPORTS_CROSS_DB_QUERIES = False
    CAN_FETCH_CROSS_DB_TABLES = False

    @pytest.fixture
    def connection_config(self) -> ConnectionConfig:
        return ConnectionConfig(
            name="test-browse-postgresql",
            db_type="postgresql",
            server=self.SERVER_HOST,
            port=self.SERVER_PORT,
            database="",  # Empty to browse all databases
            username=self.USERNAME,
            password=self.PASSWORD,
        )

    @pytest.fixture(autouse=True)
    def check_postgres_available(self, postgres_server_ready: bool, postgres_db: str):
        """Skip if PostgreSQL is not available."""
        if not postgres_server_ready:
            pytest.skip("PostgreSQL is not available")
        self.TEST_DATABASE = postgres_db

    @pytest.mark.asyncio
    async def test_browse_all_databases_and_query(self, connection_config: ConnectionConfig, temp_config_dir: str):
        """Test PostgreSQL database browsing with empty database field."""
        await super().test_browse_all_databases_and_query(connection_config, temp_config_dir)


class TestMSSQLDatabaseBrowsing(BaseDatabaseBrowsingTest):
    """Test database browsing for SQL Server."""

    DB_TYPE = "mssql"
    TEST_DATABASE = os.environ.get("MSSQL_DATABASE", "test_sqlit")
    SERVER_HOST = os.environ.get("MSSQL_HOST", "localhost")
    SERVER_PORT = os.environ.get("MSSQL_PORT", "1433")
    USERNAME = os.environ.get("MSSQL_USER", "sa")
    PASSWORD = os.environ.get("MSSQL_PASSWORD", "TestPassword123!")

    @pytest.fixture
    def connection_config(self) -> ConnectionConfig:
        server = self.SERVER_HOST
        if self.SERVER_PORT and self.SERVER_PORT != "1433":
            server = f"{self.SERVER_HOST},{self.SERVER_PORT}"
        return ConnectionConfig(
            name="test-browse-mssql",
            db_type="mssql",
            server=server,
            port="",  # Port included in server for MSSQL
            database="",  # Empty to browse all databases
            username=self.USERNAME,
            password=self.PASSWORD,
            auth_type="sql",
        )

    @pytest.fixture(autouse=True)
    def check_mssql_available(self, mssql_server_ready: bool, mssql_db: str):
        """Skip if MSSQL is not available."""
        if not mssql_server_ready:
            pytest.skip("SQL Server is not available")
        self.TEST_DATABASE = mssql_db

    @pytest.mark.asyncio
    async def test_browse_all_databases_and_query(self, connection_config: ConnectionConfig, temp_config_dir: str):
        """Test SQL Server database browsing with empty database field."""
        await super().test_browse_all_databases_and_query(connection_config, temp_config_dir)


class TestMariaDBDatabaseBrowsing(BaseDatabaseBrowsingTest):
    """Test database browsing for MariaDB."""

    DB_TYPE = "mariadb"
    TEST_DATABASE = os.environ.get("MARIADB_DATABASE", "test_sqlit")
    SERVER_HOST = os.environ.get("MARIADB_HOST", "127.0.0.1")
    SERVER_PORT = os.environ.get("MARIADB_PORT", "3307")
    USERNAME = os.environ.get("MARIADB_USER", "root")
    PASSWORD = os.environ.get("MARIADB_PASSWORD", "TestPassword123!")

    @pytest.fixture
    def connection_config(self) -> ConnectionConfig:
        return ConnectionConfig(
            name="test-browse-mariadb",
            db_type="mariadb",
            server=self.SERVER_HOST,
            port=self.SERVER_PORT,
            database="",  # Empty to browse all databases
            username=self.USERNAME,
            password=self.PASSWORD,
        )

    @pytest.fixture(autouse=True)
    def check_mariadb_available(self, mariadb_server_ready: bool, mariadb_db: str):
        """Skip if MariaDB is not available."""
        if not mariadb_server_ready:
            pytest.skip("MariaDB is not available")
        self.TEST_DATABASE = mariadb_db

    @pytest.mark.asyncio
    async def test_browse_all_databases_and_query(self, connection_config: ConnectionConfig, temp_config_dir: str):
        """Test MariaDB database browsing with empty database field."""
        await super().test_browse_all_databases_and_query(connection_config, temp_config_dir)


class TestCockroachDBDatabaseBrowsing(BaseDatabaseBrowsingTest):
    """Test database browsing for CockroachDB.

    Note: CockroachDB uses PostgreSQL wire protocol and has the same limitation -
    it doesn't support cross-database queries. Each database is isolated.
    """

    DB_TYPE = "cockroachdb"
    TEST_DATABASE = os.environ.get("COCKROACHDB_DATABASE", "test_sqlit")
    SERVER_HOST = os.environ.get("COCKROACHDB_HOST", "localhost")
    SERVER_PORT = os.environ.get("COCKROACHDB_PORT", "26257")
    USERNAME = os.environ.get("COCKROACHDB_USER", "root")
    PASSWORD = os.environ.get("COCKROACHDB_PASSWORD", "")
    SUPPORTS_CROSS_DB_QUERIES = False
    CAN_FETCH_CROSS_DB_TABLES = False

    @pytest.fixture
    def connection_config(self) -> ConnectionConfig:
        return ConnectionConfig(
            name="test-browse-cockroachdb",
            db_type="cockroachdb",
            server=self.SERVER_HOST,
            port=self.SERVER_PORT,
            database="",  # Empty to browse all databases
            username=self.USERNAME,
            password=self.PASSWORD,
        )

    @pytest.fixture(autouse=True)
    def check_cockroachdb_available(self, cockroachdb_server_ready: bool, cockroachdb_db: str):
        """Skip if CockroachDB is not available."""
        if not cockroachdb_server_ready:
            pytest.skip("CockroachDB is not available")
        self.TEST_DATABASE = cockroachdb_db

    @pytest.mark.asyncio
    async def test_browse_all_databases_and_query(self, connection_config: ConnectionConfig, temp_config_dir: str):
        """Test CockroachDB database browsing with empty database field."""
        await super().test_browse_all_databases_and_query(connection_config, temp_config_dir)
