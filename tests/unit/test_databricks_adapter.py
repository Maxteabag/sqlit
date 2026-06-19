"""Unit tests for Databricks adapter."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import ConnectionConfig


def _fake_databricks_sql() -> tuple[MagicMock, dict[str, types.ModuleType]]:
    """Build a fake `databricks.sql` module hierarchy."""
    databricks_pkg = types.ModuleType("databricks")
    databricks_sql = types.ModuleType("databricks.sql")
    connect = MagicMock(name="databricks.sql.connect")
    databricks_sql.connect = connect  # type: ignore[attr-defined]
    databricks_pkg.sql = databricks_sql  # type: ignore[attr-defined]
    modules = {"databricks": databricks_pkg, "databricks.sql": databricks_sql}
    return connect, modules


class TestDatabricksAdapter:
    def test_connect_pat_default(self):
        connect, modules = _fake_databricks_sql()
        with patch.dict(sys.modules, modules):
            from sqlit.domains.connections.providers.databricks.adapter import DatabricksAdapter

            adapter = DatabricksAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="databricks",
                server="dbc-xyz.cloud.databricks.com",
                database="main",
                options={
                    "http_path": "/sql/1.0/warehouses/abcdef",
                    "auth_type": "pat",
                    "access_token": "dapi-xxx",
                    "schema": "default",
                },
            )
            adapter.connect(config)
            connect.assert_called_once_with(
                server_hostname="dbc-xyz.cloud.databricks.com",
                http_path="/sql/1.0/warehouses/abcdef",
                catalog="main",
                schema="default",
                access_token="dapi-xxx",
            )

    def test_connect_pat_token_from_password_field(self):
        """If access_token isn't in options, the endpoint password is used."""
        connect, modules = _fake_databricks_sql()
        with patch.dict(sys.modules, modules):
            from sqlit.domains.connections.providers.databricks.adapter import DatabricksAdapter

            adapter = DatabricksAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="databricks",
                server="host",
                password="legacy-pat",
                options={"http_path": "/sql/1.0/warehouses/x"},
            )
            adapter.connect(config)
            args = connect.call_args.kwargs
            assert args["access_token"] == "legacy-pat"

    def test_connect_oauth_u2m(self):
        connect, modules = _fake_databricks_sql()
        with patch.dict(sys.modules, modules):
            from sqlit.domains.connections.providers.databricks.adapter import DatabricksAdapter

            adapter = DatabricksAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="databricks",
                server="host",
                options={
                    "http_path": "/sql/1.0/warehouses/x",
                    "auth_type": "oauth-u2m",
                },
            )
            adapter.connect(config)
            args = connect.call_args.kwargs
            assert args["auth_type"] == "databricks-oauth"
            assert "access_token" not in args

    def test_connect_missing_http_path_raises(self):
        _, modules = _fake_databricks_sql()
        with patch.dict(sys.modules, modules):
            from sqlit.domains.connections.providers.databricks.adapter import DatabricksAdapter

            adapter = DatabricksAdapter()
            config = ConnectionConfig(name="t", db_type="databricks", server="host", password="x")
            with pytest.raises(ValueError, match="HTTP Path"):
                adapter.connect(config)

    def test_connect_missing_pat_raises(self):
        _, modules = _fake_databricks_sql()
        with patch.dict(sys.modules, modules):
            from sqlit.domains.connections.providers.databricks.adapter import DatabricksAdapter

            adapter = DatabricksAdapter()
            config = ConnectionConfig(
                name="t",
                db_type="databricks",
                server="host",
                options={"http_path": "/sql/1.0/warehouses/x", "auth_type": "pat"},
            )
            with pytest.raises(ValueError, match="access token"):
                adapter.connect(config)

    def test_connect_m2m_requires_client_credentials(self):
        _, modules = _fake_databricks_sql()
        with patch.dict(sys.modules, modules):
            from sqlit.domains.connections.providers.databricks.adapter import DatabricksAdapter

            adapter = DatabricksAdapter()
            config = ConnectionConfig(
                name="t",
                db_type="databricks",
                server="host",
                options={"http_path": "/sql/1.0/warehouses/x", "auth_type": "oauth-m2m"},
            )
            with pytest.raises(ValueError, match="client_id"):
                adapter.connect(config)

    def test_get_databases_uses_show_catalogs(self):
        from sqlit.domains.connections.providers.databricks.adapter import DatabricksAdapter

        adapter = DatabricksAdapter()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [("main",), ("samples",), ("hive_metastore",)]

        result = adapter.get_databases(mock_conn)

        mock_cursor.execute.assert_called_with("SHOW CATALOGS")
        assert result == ["main", "samples", "hive_metastore"]

    def test_get_tables_with_catalog_uses_info_schema(self):
        from sqlit.domains.connections.providers.databricks.adapter import DatabricksAdapter

        adapter = DatabricksAdapter()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("default", "trips"),
            ("analytics", "events"),
        ]

        tables = adapter.get_tables(mock_conn, database="main")
        sql = mock_cursor.execute.call_args[0][0]
        assert "`main`.information_schema.tables" in sql
        assert tables == [("default", "trips"), ("analytics", "events")]

    def test_get_columns_uses_info_schema(self):
        from sqlit.domains.connections.providers.databricks.adapter import DatabricksAdapter

        adapter = DatabricksAdapter()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("id", "BIGINT"),
            ("name", "STRING"),
        ]

        cols = adapter.get_columns(
            mock_conn, "trips", database="main", schema="default"
        )

        args = mock_cursor.execute.call_args[0]
        assert "`main`.information_schema.columns" in args[0]
        assert args[1] == ("default", "trips")
        assert [c.name for c in cols] == ["id", "name"]
        assert cols[0].data_type == "BIGINT"

    def test_quote_identifier_uses_backticks(self):
        from sqlit.domains.connections.providers.databricks.adapter import DatabricksAdapter

        adapter = DatabricksAdapter()
        assert adapter.quote_identifier("foo") == "`foo`"
        assert adapter.quote_identifier("a`b") == "`a``b`"

    def test_build_select_query(self):
        from sqlit.domains.connections.providers.databricks.adapter import DatabricksAdapter

        adapter = DatabricksAdapter()
        assert (
            adapter.build_select_query("trips", 10, database="main", schema="default")
            == "SELECT * FROM `main`.`default`.`trips` LIMIT 10"
        )
        assert (
            adapter.build_select_query("trips", 10, schema="default")
            == "SELECT * FROM `default`.`trips` LIMIT 10"
        )

    def test_capabilities(self):
        from sqlit.domains.connections.providers.databricks.adapter import DatabricksAdapter

        adapter = DatabricksAdapter()
        assert adapter.supports_multiple_databases is True
        assert adapter.supports_cross_database_queries is True
        assert adapter.supports_stored_procedures is False
        assert adapter.supports_indexes is False
        assert adapter.supports_triggers is False
        assert adapter.supports_sequences is False
        assert adapter.default_schema == "default"

    def test_provider_registration(self):
        from sqlit.domains.connections.providers.catalog import (
            get_provider_schema,
            get_supported_db_types,
        )

        assert "databricks" in get_supported_db_types()
        schema = get_provider_schema("databricks")
        field_names = [f.name for f in schema.fields]
        assert "server" in field_names
        assert "http_path" in field_names
        assert "auth_type" in field_names
        assert "access_token" in field_names
