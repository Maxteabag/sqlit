"""Tests for mock database adapters and profiles."""

from __future__ import annotations

from sqlit.config import ConnectionConfig
from sqlit.db.adapters.base import ColumnInfo
from sqlit.mocks import (
    MockConnection,
    MockDatabaseAdapter,
    MockProfile,
    get_default_mock_adapter,
    get_mock_profile,
)


class TestMockDatabaseAdapter:
    """Tests for MockDatabaseAdapter behavior."""

    def test_connect_returns_connection(self):
        adapter = MockDatabaseAdapter()
        config = ConnectionConfig(name="test", db_type="sqlite", file_path="/tmp/test.db")
        conn = adapter.connect(config)
        assert isinstance(conn, MockConnection)
        assert not conn.closed
        conn.close()
        assert conn.closed

    def test_returns_configured_tables(self):
        tables = [("public", "users"), ("public", "orders")]
        adapter = MockDatabaseAdapter(tables=tables)
        assert adapter.get_tables(MockConnection()) == tables

    def test_returns_configured_columns(self):
        columns = {"users": [ColumnInfo("id", "INT"), ColumnInfo("name", "TEXT")]}
        adapter = MockDatabaseAdapter(columns=columns)
        result = adapter.get_columns(MockConnection(), "users")
        assert len(result) == 2
        assert result[0].name == "id"

    def test_unknown_table_returns_empty_columns(self):
        adapter = MockDatabaseAdapter(columns={"users": [ColumnInfo("id", "INT")]})
        assert adapter.get_columns(MockConnection(), "nonexistent") == []

    def test_execute_query_pattern_matching(self):
        adapter = MockDatabaseAdapter(
            query_results={
                "users": (["id", "name"], [(1, "Alice"), (2, "Bob")]),
            }
        )
        cols, rows, truncated = adapter.execute_query(MockConnection(), "SELECT * FROM users WHERE id = 1")
        assert cols == ["id", "name"]
        assert len(rows) == 2
        assert not truncated

    def test_execute_query_case_insensitive(self):
        adapter = MockDatabaseAdapter(query_results={"users": (["id"], [(1,)])})
        cols, _, _ = adapter.execute_query(MockConnection(), "SELECT * FROM USERS")
        assert cols == ["id"]

    def test_execute_query_returns_default_for_unknown(self):
        adapter = MockDatabaseAdapter(
            query_results={"specific": (["x"], [(1,)])},
            default_query_result=(["result"], [("default",)]),
        )
        cols, rows, _ = adapter.execute_query(MockConnection(), "SELECT something_else")
        assert cols == ["result"]
        assert rows == [("default",)]

    def test_execute_query_respects_max_rows(self):
        adapter = MockDatabaseAdapter(
            query_results={
                "users": (["id"], [(1,), (2,), (3,), (4,), (5,)]),
            }
        )
        cols, rows, truncated = adapter.execute_query(MockConnection(), "SELECT * FROM users", max_rows=2)
        assert len(rows) == 2
        assert truncated is True


class TestMockProfile:
    """Tests for MockProfile behavior."""

    def test_get_adapter_returns_custom(self):
        custom = MockDatabaseAdapter(name="Custom")
        profile = MockProfile(name="test", adapters={"sqlite": custom})
        assert profile.get_adapter("sqlite").name == "Custom"

    def test_get_adapter_falls_back_to_default(self):
        profile = MockProfile(name="test", use_default_adapters=True)
        adapter = profile.get_adapter("sqlite")
        assert adapter is not None

    def test_get_adapter_no_fallback_creates_generic(self):
        profile = MockProfile(name="test", use_default_adapters=False)
        adapter = profile.get_adapter("sqlite")
        assert "sqlite" in adapter.name.lower()

    def test_unknown_profile_returns_none(self):
        assert get_mock_profile("nonexistent") is None

    def test_unknown_adapter_type_returns_generic(self):
        adapter = get_default_mock_adapter("unknown_db_type")
        assert adapter is not None


class TestMockIntegration:
    """Integration tests for mock database operations."""

    def test_full_workflow(self):
        profile = get_mock_profile("sqlite-demo")
        adapter = profile.get_adapter("sqlite")
        config = profile.connections[0]

        conn = adapter.connect(config)
        tables = adapter.get_tables(conn)
        assert len(tables) > 0

        for schema, table_name in tables:
            columns = adapter.get_columns(conn, table_name)
            assert len(columns) > 0

        conn.close()

    def test_query_columns_match_table_columns(self):
        profile = get_mock_profile("sqlite-demo")
        adapter = profile.get_adapter("sqlite")

        table_cols = {c.name for c in adapter.get_columns(MockConnection(), "users")}
        query_cols, _, _ = adapter.execute_query(MockConnection(), "SELECT * FROM users")

        assert set(query_cols) == table_cols


class TestAdapterInterfaceCompliance:
    """Tests that MockDatabaseAdapter matches DatabaseAdapter interface."""

    def test_method_signatures_match_base(self):
        import inspect

        from sqlit.db.adapters.base import DatabaseAdapter

        for method_name in ["build_select_query", "execute_query"]:
            base_params = list(inspect.signature(getattr(DatabaseAdapter, method_name)).parameters.keys())
            mock_params = list(inspect.signature(getattr(MockDatabaseAdapter, method_name)).parameters.keys())

            assert base_params == mock_params, f"{method_name}: {mock_params} != {base_params}"

    def test_all_abstract_methods_callable(self):
        adapter = MockDatabaseAdapter()
        conn = MockConnection()
        config = ConnectionConfig(name="t", db_type="sqlite", file_path="/tmp/t.db")

        _ = adapter.name
        _ = adapter.default_schema
        _ = adapter.supports_multiple_databases
        _ = adapter.supports_stored_procedures
        _ = adapter.connect(config)
        _ = adapter.get_databases(conn)
        _ = adapter.get_tables(conn)
        _ = adapter.get_views(conn)
        _ = adapter.get_columns(conn, "t")
        _ = adapter.get_procedures(conn)
        _ = adapter.quote_identifier("t")
        _ = adapter.build_select_query("t", 100, None, None)
        _ = adapter.execute_query(conn, "SELECT 1")
        _ = adapter.execute_non_query(conn, "INSERT INTO t VALUES (1)")
