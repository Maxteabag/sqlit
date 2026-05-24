"""Unit tests for the osquery adapter.

osquery isn't a normal networked database - it uses a local Unix socket
(or named pipe on Windows) via Thrift to talk to osqueryd, or spawns an
embedded instance. These tests mock the `osquery` Python SDK entirely so
they run with zero external dependencies (no daemon, no docker, no install).
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import ConnectionConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_osquery_module() -> MagicMock:
    """Build a fake osquery SDK module with SpawnInstance and ExtensionClient."""
    module = MagicMock(name="osquery_module")
    return module


def _install_fake_osquery(fake_module: MagicMock) -> None:
    """Put the fake module into sys.modules so _import_driver_module finds it."""
    sys.modules["osquery"] = fake_module


def _uninstall_fake_osquery() -> None:
    sys.modules.pop("osquery", None)


def _make_query_result(code: int, message: str, response: list[dict]) -> SimpleNamespace:
    """Build a fake osquery query result with .status.code/.message and .response."""
    return SimpleNamespace(
        status=SimpleNamespace(code=code, message=message),
        response=response,
    )


# ---------------------------------------------------------------------------
# Provider metadata / schema
# ---------------------------------------------------------------------------


class TestOsqueryProviderMetadata:
    """The key bug fix from pr-162 lives in the provider/schema metadata."""

    def test_provider_is_file_based_false(self):
        """Locks in the fix: osquery must NOT be treated as file-based."""
        from sqlit.domains.connections.providers.catalog import get_provider

        provider = get_provider("osquery")
        assert provider is not None
        assert provider.metadata.is_file_based is False

    def test_schema_is_file_based_false(self):
        """The connection schema also marks osquery as not file-based."""
        from sqlit.domains.connections.providers.osquery.schema import SCHEMA

        assert SCHEMA.is_file_based is False

    def test_provider_registered_in_catalog(self):
        from sqlit.domains.connections.providers.catalog import get_supported_db_types

        assert "osquery" in get_supported_db_types()

    def test_database_type_enum_has_osquery(self):
        from sqlit.domains.connections.domain.config import DatabaseType

        assert DatabaseType.OSQUERY.value == "osquery"

    def test_provider_does_not_require_auth(self):
        from sqlit.domains.connections.providers.catalog import get_provider

        provider = get_provider("osquery")
        assert provider.metadata.requires_auth is False
        assert provider.metadata.supports_ssh is False


# ---------------------------------------------------------------------------
# Adapter capability flags
# ---------------------------------------------------------------------------


class TestOsqueryAdapterCapabilities:
    """osquery is read-only virtual tables - most SQL features don't apply."""

    def _adapter(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        return OsqueryAdapter()

    def test_name(self):
        assert self._adapter().name == "osquery"

    def test_install_extra(self):
        assert self._adapter().install_extra == "osquery"

    def test_install_package(self):
        assert self._adapter().install_package == "osquery"

    def test_driver_import_names(self):
        assert self._adapter().driver_import_names == ("osquery",)

    def test_supports_multiple_databases_false(self):
        assert self._adapter().supports_multiple_databases is False

    def test_supports_cross_database_queries_false(self):
        assert self._adapter().supports_cross_database_queries is False

    def test_supports_stored_procedures_false(self):
        assert self._adapter().supports_stored_procedures is False

    def test_supports_indexes_false(self):
        assert self._adapter().supports_indexes is False

    def test_supports_triggers_false(self):
        assert self._adapter().supports_triggers is False

    def test_supports_sequences_false(self):
        assert self._adapter().supports_sequences is False

    def test_supports_process_worker_false(self):
        # Spawned embedded instances don't cross process boundaries well.
        assert self._adapter().supports_process_worker is False

    def test_default_schema_empty(self):
        assert self._adapter().default_schema == ""

    def test_test_query(self):
        assert self._adapter().test_query == "SELECT 1 AS test"

    def test_classify_query_always_select_like(self):
        adapter = self._adapter()
        # osquery is read-only; everything classifies as "returns rows".
        assert adapter.classify_query("SELECT * FROM processes") is True
        assert adapter.classify_query("INSERT INTO x VALUES (1)") is True

    def test_quote_identifier_double_quotes(self):
        adapter = self._adapter()
        assert adapter.quote_identifier("processes") == '"processes"'
        assert adapter.quote_identifier('we"ird') == '"we""ird"'

    def test_build_select_query(self):
        adapter = self._adapter()
        assert adapter.build_select_query("users", 50) == 'SELECT * FROM "users" LIMIT 50'

    def test_get_databases_returns_single_virtual_db(self):
        adapter = self._adapter()
        assert adapter.get_databases(MagicMock()) == ["main"]

    def test_get_views_empty(self):
        assert self._adapter().get_views(MagicMock()) == []

    def test_get_procedures_empty(self):
        assert self._adapter().get_procedures(MagicMock()) == []

    def test_get_indexes_empty(self):
        assert self._adapter().get_indexes(MagicMock()) == []

    def test_get_triggers_empty(self):
        assert self._adapter().get_triggers(MagicMock()) == []

    def test_get_sequences_empty(self):
        assert self._adapter().get_sequences(MagicMock()) == []


# ---------------------------------------------------------------------------
# Default socket path (platform-dependent)
# ---------------------------------------------------------------------------


class TestOsqueryDefaultSocketPath:
    def _adapter(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        return OsqueryAdapter()

    def test_default_socket_path_linux(self):
        adapter = self._adapter()
        with patch("platform.system", return_value="Linux"):
            assert adapter._get_default_socket_path() == "/var/osquery/osquery.em"

    def test_default_socket_path_macos(self):
        adapter = self._adapter()
        with patch("platform.system", return_value="Darwin"):
            assert adapter._get_default_socket_path() == "/var/osquery/osquery.em"

    def test_default_socket_path_windows(self):
        adapter = self._adapter()
        with patch("platform.system", return_value="Windows"):
            assert adapter._get_default_socket_path() == r"\\.\pipe\osquery.em"


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


class TestOsqueryAdapterConnect:
    """connect() should pick between SpawnInstance and ExtensionClient."""

    def setup_method(self):
        self.fake_module = _fake_osquery_module()
        _install_fake_osquery(self.fake_module)

    def teardown_method(self):
        _uninstall_fake_osquery()

    def test_connect_defaults_to_spawn(self):
        """No connection_mode option -> spawn embedded instance."""
        from sqlit.domains.connections.providers.osquery.adapter import (
            OsqueryAdapter,
            OsqueryConnection,
        )

        fake_instance = MagicMock(name="spawn_instance")
        self.fake_module.SpawnInstance.return_value = fake_instance

        config = ConnectionConfig(name="osq-spawn", db_type="osquery")
        adapter = OsqueryAdapter()

        conn = adapter.connect(config)

        self.fake_module.SpawnInstance.assert_called_once_with()
        fake_instance.open.assert_called_once_with()
        self.fake_module.ExtensionClient.assert_not_called()

        assert isinstance(conn, OsqueryConnection)
        assert conn.is_spawned is True
        assert conn.instance is fake_instance

    def test_connect_spawn_explicit(self):
        """connection_mode='spawn' -> SpawnInstance()."""
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        fake_instance = MagicMock(name="spawn_instance")
        self.fake_module.SpawnInstance.return_value = fake_instance

        config = ConnectionConfig(
            name="osq-spawn", db_type="osquery", options={"connection_mode": "spawn"}
        )
        conn = OsqueryAdapter().connect(config)

        self.fake_module.SpawnInstance.assert_called_once_with()
        fake_instance.open.assert_called_once_with()
        assert conn.is_spawned is True

    def test_connect_socket_with_explicit_path(self):
        """connection_mode='socket' with socket_path -> ExtensionClient(path)."""
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        fake_instance = MagicMock(name="extension_client")
        self.fake_module.ExtensionClient.return_value = fake_instance

        config = ConnectionConfig(
            name="osq-sock",
            db_type="osquery",
            options={
                "connection_mode": "socket",
                "socket_path": "/tmp/custom/osquery.em",
            },
        )
        conn = OsqueryAdapter().connect(config)

        self.fake_module.ExtensionClient.assert_called_once_with("/tmp/custom/osquery.em")
        fake_instance.open.assert_called_once_with()
        self.fake_module.SpawnInstance.assert_not_called()
        assert conn.is_spawned is False
        assert conn.instance is fake_instance

    def test_connect_socket_falls_back_to_default_path(self):
        """connection_mode='socket' with no socket_path -> use platform default."""
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        fake_instance = MagicMock(name="extension_client")
        self.fake_module.ExtensionClient.return_value = fake_instance

        config = ConnectionConfig(
            name="osq-sock",
            db_type="osquery",
            options={"connection_mode": "socket"},
        )

        with patch("platform.system", return_value="Linux"):
            OsqueryAdapter().connect(config)

        self.fake_module.ExtensionClient.assert_called_once_with("/var/osquery/osquery.em")
        fake_instance.open.assert_called_once_with()

    def test_connect_socket_default_path_windows(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        fake_instance = MagicMock(name="extension_client")
        self.fake_module.ExtensionClient.return_value = fake_instance

        config = ConnectionConfig(
            name="osq-sock",
            db_type="osquery",
            options={"connection_mode": "socket"},
        )

        with patch("platform.system", return_value="Windows"):
            OsqueryAdapter().connect(config)

        self.fake_module.ExtensionClient.assert_called_once_with(r"\\.\pipe\osquery.em")


# ---------------------------------------------------------------------------
# OsqueryConnection wrapper
# ---------------------------------------------------------------------------


class TestOsqueryConnectionWrapper:
    def test_client_lazily_cached(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryConnection

        client_a = MagicMock(name="client_a")
        instance = MagicMock()
        instance.client = client_a

        conn = OsqueryConnection(instance, is_spawned=True)
        assert conn.client is client_a
        # swap the underlying instance.client; wrapper should keep the cached one
        instance.client = MagicMock(name="client_b")
        assert conn.client is client_a

    def test_close_spawned_is_noop(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryConnection

        instance = MagicMock()
        conn = OsqueryConnection(instance, is_spawned=True)
        conn.close()
        instance.close.assert_not_called()

    def test_close_socket_calls_instance_close(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryConnection

        instance = MagicMock()
        conn = OsqueryConnection(instance, is_spawned=False)
        conn.close()
        instance.close.assert_called_once_with()

    def test_adapter_disconnect_delegates_to_wrapper(self):
        from sqlit.domains.connections.providers.osquery.adapter import (
            OsqueryAdapter,
            OsqueryConnection,
        )

        instance = MagicMock()
        conn = OsqueryConnection(instance, is_spawned=False)
        OsqueryAdapter().disconnect(conn)
        instance.close.assert_called_once_with()

    def test_adapter_disconnect_ignores_non_wrapper(self):
        """disconnect() on something that isn't an OsqueryConnection is a no-op."""
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        something_else = MagicMock()
        OsqueryAdapter().disconnect(something_else)
        something_else.close.assert_not_called()


# ---------------------------------------------------------------------------
# execute_test_query
# ---------------------------------------------------------------------------


class TestOsqueryExecuteTestQuery:
    def _conn_returning(self, result) -> MagicMock:
        conn = MagicMock()
        conn.client.query.return_value = result
        return conn

    def test_success_path(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        conn = self._conn_returning(
            _make_query_result(code=0, message="", response=[{"test": 1}])
        )
        # should not raise
        OsqueryAdapter().execute_test_query(conn)
        conn.client.query.assert_called_once_with("SELECT 1 AS test")

    def test_failure_raises(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        conn = self._conn_returning(
            _make_query_result(code=1, message="something broke", response=[])
        )
        with pytest.raises(Exception, match="osquery test failed: something broke"):
            OsqueryAdapter().execute_test_query(conn)


# ---------------------------------------------------------------------------
# get_tables
# ---------------------------------------------------------------------------


class TestOsqueryGetTables:
    EXPECTED_SQL = (
        "SELECT name FROM osquery_registry WHERE registry = 'table' ORDER BY name"
    )

    def _conn_returning(self, result) -> MagicMock:
        conn = MagicMock()
        conn.client.query.return_value = result
        return conn

    def test_get_tables_returns_tuples(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        conn = self._conn_returning(
            _make_query_result(
                code=0,
                message="",
                response=[
                    {"name": "processes"},
                    {"name": "users"},
                    {"name": "listening_ports"},
                ],
            )
        )
        tables = OsqueryAdapter().get_tables(conn)

        conn.client.query.assert_called_once_with(self.EXPECTED_SQL)
        assert tables == [
            ("", "processes"),
            ("", "users"),
            ("", "listening_ports"),
        ]

    def test_get_tables_filters_rows_without_name(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        conn = self._conn_returning(
            _make_query_result(
                code=0,
                message="",
                response=[{"name": "processes"}, {"name": ""}, {"other": "x"}],
            )
        )
        assert OsqueryAdapter().get_tables(conn) == [("", "processes")]

    def test_get_tables_returns_empty_on_error(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        conn = self._conn_returning(
            _make_query_result(code=1, message="boom", response=[])
        )
        assert OsqueryAdapter().get_tables(conn) == []


# ---------------------------------------------------------------------------
# execute_query / execute_non_query
# ---------------------------------------------------------------------------


class TestOsqueryExecuteQuery:
    def _conn_returning(self, result) -> MagicMock:
        conn = MagicMock()
        conn.client.query.return_value = result
        return conn

    def test_execute_query_empty_response(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        conn = self._conn_returning(_make_query_result(code=0, message="", response=[]))
        cols, rows, truncated = OsqueryAdapter().execute_query(conn, "SELECT 1")
        assert cols == []
        assert rows == []
        assert truncated is False

    def test_execute_query_with_rows(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        conn = self._conn_returning(
            _make_query_result(
                code=0,
                message="",
                response=[
                    {"pid": "1", "name": "init"},
                    {"pid": "2", "name": "kthreadd"},
                ],
            )
        )
        cols, rows, truncated = OsqueryAdapter().execute_query(conn, "SELECT pid, name FROM processes")
        assert cols == ["pid", "name"]
        assert rows == [("1", "init"), ("2", "kthreadd")]
        assert truncated is False

    def test_execute_query_respects_max_rows(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        conn = self._conn_returning(
            _make_query_result(
                code=0,
                message="",
                response=[{"n": str(i)} for i in range(5)],
            )
        )
        cols, rows, truncated = OsqueryAdapter().execute_query(
            conn, "SELECT n FROM x", max_rows=3
        )
        assert cols == ["n"]
        assert len(rows) == 3
        assert truncated is True

    def test_execute_query_raises_on_error(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        conn = self._conn_returning(
            _make_query_result(code=1, message="bad SQL", response=[])
        )
        with pytest.raises(Exception, match="osquery error: bad SQL"):
            OsqueryAdapter().execute_query(conn, "SELECT bogus")

    def test_execute_non_query_success(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        conn = self._conn_returning(_make_query_result(code=0, message="", response=[]))
        result = OsqueryAdapter().execute_non_query(conn, "SELECT 1")
        # osquery is read-only; always returns 0 rows affected
        assert result == 0

    def test_execute_non_query_raises_on_error(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        conn = self._conn_returning(_make_query_result(code=1, message="nope", response=[]))
        with pytest.raises(Exception, match="osquery error: nope"):
            OsqueryAdapter().execute_non_query(conn, "DELETE FROM processes")


# ---------------------------------------------------------------------------
# get_columns
# ---------------------------------------------------------------------------


class TestOsqueryGetColumns:
    def test_get_columns_via_pragma(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        conn = MagicMock()
        conn.client.query.return_value = _make_query_result(
            code=0,
            message="",
            response=[
                {"name": "pid", "type": "BIGINT"},
                {"name": "name", "type": "TEXT"},
                {"name": "", "type": "TEXT"},  # filtered out
            ],
        )

        columns = OsqueryAdapter().get_columns(conn, "processes")

        conn.client.query.assert_called_once_with("PRAGMA table_info(processes)")
        assert [c.name for c in columns] == ["pid", "name"]
        assert [c.data_type for c in columns] == ["BIGINT", "TEXT"]

    def test_get_columns_returns_empty_on_error(self):
        from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

        conn = MagicMock()
        conn.client.query.return_value = _make_query_result(
            code=1, message="no such table", response=[]
        )
        assert OsqueryAdapter().get_columns(conn, "missing") == []
