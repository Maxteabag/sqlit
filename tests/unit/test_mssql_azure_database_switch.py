"""Unit tests for switching databases on Azure SQL Database.

Azure SQL Database (EngineEdition 5/6) rejects USE outright:

    DDBC Error: USE statement is not supported to switch between databases.
    Use a new connection to connect to a different database.

The adapter falls back to opening a second connection bound to the target
database, so the explorer can still browse other databases on the server.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

USE_NOT_SUPPORTED = (
    "Driver Error: Syntax error or access violation; DDBC Error: USE statement "
    "is not supported to switch between databases. Use a new connection to "
    "connect to a different database."
)


class FakeCursor:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn

    def execute(self, sql: str, *args: object) -> None:
        self.conn.executed.append(sql)
        if sql.startswith("USE") and self.conn.use_error is not None:
            raise self.conn.use_error()

    def fetchall(self) -> list:
        return []

    def fetchone(self) -> None:
        return None


class FakeConnection:
    """Stand-in for an mssql_python connection.

    `use_error` builds the exception a USE statement should raise, or is None
    on a server where USE works.
    """

    def __init__(self, database: str, use_error) -> None:
        self.database = database
        self.use_error = use_error
        self.executed: list[str] = []
        self.closed = False
        self.autocommit = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def close(self) -> None:
        self.closed = True


def _database_from(conn_str: str) -> str:
    for part in conn_str.split(";"):
        key, _, value = part.partition("=")
        if key.strip().upper() == "DATABASE":
            return value.strip()
    return ""


@pytest.fixture
def driver():
    """Patch mssql_python so connect() hands back FakeConnections.

    Yields a factory: `adapter, opened = driver(use_error=...)`, where `opened`
    accumulates every connection the adapter opened, in order.
    """
    module = MagicMock()
    with patch.dict("sys.modules", {"mssql_python": module}):

        def _factory(use_error):
            from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

            opened: list[FakeConnection] = []

            def fake_connect(conn_str: str, attrs_before=None) -> FakeConnection:
                conn = FakeConnection(_database_from(conn_str), use_error)
                opened.append(conn)
                return conn

            module.connect.side_effect = fake_connect
            return SQLServerAdapter(), opened

        yield _factory


def azure_driver(driver):
    return driver(lambda: RuntimeError(USE_NOT_SUPPORTED))


def sql_server_driver(driver):
    return driver(None)


@pytest.fixture
def config():
    def _config(database: str):
        from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint

        return ConnectionConfig(
            name="test_mssql",
            db_type="mssql",
            endpoint=TcpEndpoint(
                host="server.database.windows.net",
                port="1433",
                database=database,
                username="sa",
                password="password",
            ),
            options={"auth_type": "sql"},
        )

    return _config


class TestAzureDatabaseSwitching:
    def test_use_failure_falls_back_to_a_new_connection(self, driver, config):
        adapter, opened = azure_driver(driver)
        root = adapter.connect(config("master"))

        adapter.get_tables(root, database="TestDB")

        assert root.executed == ["USE [TestDB]"]
        assert [conn.database for conn in opened] == ["master", "TestDB"]
        assert "INFORMATION_SCHEMA.TABLES" in opened[1].executed[0]

    def test_second_lookup_reuses_the_new_connection(self, driver, config):
        adapter, opened = azure_driver(driver)
        root = adapter.connect(config("master"))

        adapter.get_tables(root, database="TestDB")
        adapter.get_views(root, database="TestDB")

        assert len(opened) == 2, "Expected one extra connection, not one per lookup"
        # The rejected USE is probed once; after that the adapter knows better.
        assert root.executed == ["USE [TestDB]"]

    def test_each_database_gets_its_own_connection(self, driver, config):
        adapter, opened = azure_driver(driver)
        root = adapter.connect(config("master"))

        adapter.get_tables(root, database="TestDB")
        adapter.get_tables(root, database="OtherDB")

        assert [conn.database for conn in opened] == ["master", "TestDB", "OtherDB"]

    def test_current_database_needs_no_use_or_reconnect(self, driver, config):
        adapter, opened = azure_driver(driver)
        root = adapter.connect(config("TestDB"))

        adapter.get_tables(root, database="TestDB")

        assert len(opened) == 1
        assert not any(sql.startswith("USE") for sql in root.executed)

    def test_disconnect_closes_the_extra_connections(self, driver, config):
        adapter, opened = azure_driver(driver)
        root = adapter.connect(config("master"))

        adapter.get_tables(root, database="TestDB")
        adapter.get_tables(root, database="OtherDB")
        adapter.disconnect(root)

        assert all(conn.closed for conn in opened)
        assert adapter._db_conns == {}
        assert adapter._configs == {}

    def test_collected_connection_drops_its_bookkeeping(self, driver, config):
        """A connection closed by GC rather than disconnect() must not linger.

        The per-connection state is keyed by id(), which Python reuses once an
        object is collected - a stale entry would bind a later connection to
        the wrong database.
        """
        import gc

        adapter, opened = azure_driver(driver)
        root = adapter.connect(config("master"))
        adapter.get_tables(root, database="TestDB")
        sibling = opened[1]

        del root
        opened.clear()  # the fixture's bookkeeping would otherwise keep it alive
        gc.collect()

        assert adapter._configs == {}
        assert adapter._db_conns == {}
        assert sibling.closed is True

    def test_capability_flips_off_after_a_rejected_use(self, driver, config):
        adapter, _opened = azure_driver(driver)
        root = adapter.connect(config("master"))

        assert adapter.supports_cross_database_queries is True
        adapter.get_tables(root, database="TestDB")
        assert adapter.supports_cross_database_queries is False


class TestRegularSQLServerUnchanged:
    def test_use_is_still_the_happy_path(self, driver, config):
        adapter, opened = sql_server_driver(driver)
        root = adapter.connect(config("master"))

        adapter.get_tables(root, database="TestDB")

        assert len(opened) == 1, "Regular SQL Server should not open extra connections"
        assert root.executed[0] == "USE [TestDB]"

    def test_unrelated_use_errors_are_not_swallowed(self, driver, config):
        adapter, opened = driver(lambda: RuntimeError("Login failed for user 'sa'."))
        root = adapter.connect(config("master"))

        with pytest.raises(RuntimeError, match="Login failed"):
            adapter.get_tables(root, database="TestDB")

        assert len(opened) == 1, "A non-USE failure must not trigger a reconnect"
        assert adapter.supports_cross_database_queries is True
