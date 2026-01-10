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

import pytest

from tests.helpers import ConnectionConfig
from tests.integration.browsing_base import (
    BaseDatabaseBrowsingTest,
    find_connection_node,
    find_database_node,
    find_folder_node,
    find_table_node,
    has_loading_children,
    has_table_children,
    wait_for_condition,
)

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
        yield

    @pytest.mark.asyncio
    async def test_browse_all_databases_and_query(self, connection_config: ConnectionConfig, temp_config_dir: str):
        """Test MySQL database browsing with empty database field."""
        await super().test_browse_all_databases_and_query(connection_config, temp_config_dir)

    @pytest.mark.asyncio
    async def test_select_database_then_unqualified_query(
        self, connection_config: ConnectionConfig, temp_config_dir: str
    ):
        """Select database in tree, then run unqualified query (regression for MySQL)."""
        from sqlit.domains.explorer.domain.tree_nodes import ConnectionNode
        from sqlit.domains.shell.app.main import SSMSTUI

        app = SSMSTUI()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)

            app.connections = [connection_config]
            app.refresh_tree()
            await pilot.pause(0.1)

            await wait_for_condition(
                pilot,
                lambda: len(app.object_tree.root.children) > 0,
                timeout_seconds=5.0,
                description="tree to be populated with connections",
            )

            cursor_node = find_connection_node(app.object_tree.root)
            assert cursor_node is not None
            assert isinstance(cursor_node.data, ConnectionNode)

            app.connect_to_server(connection_config)
            await pilot.pause(0.5)

            await wait_for_condition(
                pilot,
                lambda: app.current_connection is not None,
                timeout_seconds=15.0,
                description="connection to be established",
            )

            connected_node = find_connection_node(app.object_tree.root, connection_config.name)
            assert connected_node is not None, "Connected node not found"

            await wait_for_condition(
                pilot,
                lambda: len(connected_node.children) > 0,
                timeout_seconds=10.0,
                description="tree to be populated",
            )

            # Expand the Databases folder to load database list.
            databases_folder = find_folder_node(connected_node, "databases")
            assert databases_folder is not None, "Databases folder not found"

            databases_folder.expand()
            await pilot.pause(0.3)

            await wait_for_condition(
                pilot,
                lambda: not has_loading_children(databases_folder) and len(databases_folder.children) > 0,
                timeout_seconds=10.0,
                description="databases to be loaded",
            )

            db_node = find_database_node(app.object_tree.root, self.TEST_DATABASE)
            assert db_node is not None, f"Database '{self.TEST_DATABASE}' not found in tree"

            # Select database via UI (adds star).
            app.object_tree.move_cursor(db_node)
            app.action_use_database()
            await pilot.pause(0.2)

            await wait_for_condition(
                pilot,
                lambda: getattr(app, "_get_effective_database", lambda: None)() == self.TEST_DATABASE,
                timeout_seconds=5.0,
                description="active database to be set",
            )

            # Run unqualified query - should succeed if active DB is applied.
            app.query_input.text = "SELECT * FROM test_users LIMIT 1"
            app.action_execute_query()
            await pilot.pause(0.5)

            await wait_for_condition(
                pilot,
                lambda: not getattr(app, "query_executing", False),
                timeout_seconds=15.0,
                description="query to complete",
            )

            assert app._last_result_row_count > 0, "Query returned no results"
            assert app._last_result_columns, "Query returned no columns"
            assert "name" in [col.lower() for col in app._last_result_columns], (
                "Expected 'name' column in results (got error or unexpected result set)"
            )


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
        yield

    @pytest.mark.asyncio
    async def test_browse_all_databases_and_query(self, connection_config: ConnectionConfig, temp_config_dir: str):
        """Test PostgreSQL database browsing with empty database field."""
        await super().test_browse_all_databases_and_query(connection_config, temp_config_dir)


class TestMSSQLDatabaseBrowsing(BaseDatabaseBrowsingTest):
    """Test database browsing for SQL Server."""

    DB_TYPE = "mssql"
    TEST_DATABASE = os.environ.get("MSSQL_DATABASE", "test_sqlit")
    SERVER_HOST = os.environ.get("MSSQL_HOST", "localhost")
    SERVER_PORT = os.environ.get("MSSQL_PORT", "1434")
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
            options={"auth_type": "sql"},
        )

    @pytest.fixture(autouse=True)
    def check_mssql_available(self, mssql_server_ready: bool, mssql_db: str):
        """Skip if MSSQL is not available."""
        if not mssql_server_ready:
            pytest.skip("SQL Server is not available")
        self.TEST_DATABASE = mssql_db
        yield

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
        yield

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
        yield

    @pytest.mark.asyncio
    async def test_browse_all_databases_and_query(self, connection_config: ConnectionConfig, temp_config_dir: str):
        """Test CockroachDB database browsing with empty database field."""
        await super().test_browse_all_databases_and_query(connection_config, temp_config_dir)
