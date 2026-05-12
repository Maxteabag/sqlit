"""Unit tests for get_foreign_keys() across all database adapters."""

from __future__ import annotations

from unittest.mock import MagicMock

from sqlit.domains.connections.providers.adapters.base import ForeignKeyInfo


def _assert_fk_list(result: list, expected_count: int = 1) -> None:
    assert isinstance(result, list)
    assert len(result) == expected_count
    for fk in result:
        assert isinstance(fk, ForeignKeyInfo)
        assert fk.constraint_name
        assert fk.source_table
        assert fk.source_column
        assert fk.target_table
        assert fk.target_column


# -- PostgreSQL ----------------------------------------------------------------

class TestPostgreSQLForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter
        return PostgreSQLAdapter()

    def test_returns_fk_info(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = [
            ("fk_orders_user_id", "public", "orders", "user_id", "public", "users", "id"),
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)
        assert result[0].source_table == "orders"
        assert result[0].target_table == "users"
        assert result[0].source_schema == "public"

    def test_empty_result(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        result = adapter.get_foreign_keys(mock_conn)
        assert result == []

    def test_sql_contains_foreign_key_filter(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        adapter.get_foreign_keys(mock_conn)
        sql = cursor.execute.call_args[0][0]
        assert "FOREIGN KEY" in sql
        assert "table_constraints" in sql


# -- SQLite --------------------------------------------------------------------

class TestSQLiteForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.sqlite.adapter import SQLiteAdapter
        return SQLiteAdapter()

    def test_returns_fk_info(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        # get_tables calls sqlite_master -> returns raw name rows
        cursor.fetchall.side_effect = [
            [("orders",)],  # get_tables -> sqlite_master
            [(0, 0, "users", "user_id", "id", "", "", "")],  # PRAGMA foreign_key_list
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)
        assert result[0].source_table == "orders"
        assert result[0].source_column == "user_id"
        assert result[0].target_table == "users"
        assert result[0].target_column == "id"

    def test_empty_result(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.side_effect = [
            [("orders",)],  # get_tables
            [],  # PRAGMA foreign_key_list returns nothing
        ]
        result = adapter.get_foreign_keys(mock_conn)
        assert result == []


# -- DuckDB --------------------------------------------------------------------

class TestDuckDBForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.duckdb.adapter import DuckDBAdapter
        return DuckDBAdapter()

    def test_returns_fk_info(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        result_mock = MagicMock()
        mock_conn.execute.return_value = result_mock
        result_mock.fetchall.return_value = [
            ("fk_orders_user_id", "main", "orders", "user_id", "main", "users", "id"),
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)
        assert result[0].source_table == "orders"
        assert result[0].source_schema == "main"

    def test_empty_result(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        result_mock = MagicMock()
        mock_conn.execute.return_value = result_mock
        result_mock.fetchall.return_value = []
        result = adapter.get_foreign_keys(mock_conn)
        assert result == []

    def test_sql_contains_foreign_key_filter(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        result_mock = MagicMock()
        mock_conn.execute.return_value = result_mock
        result_mock.fetchall.return_value = []
        adapter.get_foreign_keys(mock_conn)
        sql = mock_conn.execute.call_args[0][0]
        assert "FOREIGN KEY" in sql
        assert "referential_constraints" in sql


# -- MySQL ---------------------------------------------------------------------

class TestMySQLForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.mysql.adapter import MySQLAdapter
        return MySQLAdapter()

    def test_returns_fk_info(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = [
            ("fk_orders_user_id", "orders", "user_id", "users", "id"),
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)
        assert result[0].source_table == "orders"
        assert result[0].target_table == "users"

    def test_empty_result(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        result = adapter.get_foreign_keys(mock_conn)
        assert result == []

    def test_with_database(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        adapter.get_foreign_keys(mock_conn, database="mydb")
        sql = cursor.execute.call_args[0][0]
        assert "table_schema = %s" in sql

    def test_without_database(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        adapter.get_foreign_keys(mock_conn)
        sql = cursor.execute.call_args[0][0]
        assert "DATABASE()" in sql


# -- MariaDB -------------------------------------------------------------------

class TestMariaDBForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.mariadb.adapter import MariaDBAdapter
        return MariaDBAdapter()

    def test_returns_fk_info(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = [
            ("fk_orders_user_id", "orders", "user_id", "users", "id"),
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)

    def test_with_database_uses_question_mark(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        adapter.get_foreign_keys(mock_conn, database="mydb")
        sql = cursor.execute.call_args[0][0]
        assert "table_schema = ?" in sql
        assert "%s" not in sql


# -- SQL Server ----------------------------------------------------------------

class TestMSSQLForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter
        return SQLServerAdapter()

    def test_returns_fk_info(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = [
            ("FK_orders_users", "dbo", "orders", "user_id", "dbo", "users", "id"),
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)
        assert result[0].source_schema == "dbo"
        assert result[0].target_schema == "dbo"

    def test_empty_result(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        result = adapter.get_foreign_keys(mock_conn)
        assert result == []

    def test_sql_uses_sys_foreign_keys(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        adapter.get_foreign_keys(mock_conn)
        sql = cursor.execute.call_args[0][0]
        assert "sys.foreign_keys" in sql


# -- Oracle --------------------------------------------------------------------

class TestOracleForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter
        return OracleAdapter()

    def test_returns_fk_info(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = [
            ("FK_ORDERS_USERS", "ORDERS", "USER_ID", "USERS", "ID"),
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)
        assert result[0].source_table == "ORDERS"

    def test_empty_result(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        result = adapter.get_foreign_keys(mock_conn)
        assert result == []

    def test_cursor_is_closed(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        adapter.get_foreign_keys(mock_conn)
        cursor.close.assert_called_once()


# -- Firebird ------------------------------------------------------------------

class TestFirebirdForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.firebird.adapter import FirebirdAdapter
        return FirebirdAdapter()

    def test_returns_fk_info_with_stripped_names(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = [
            ("FK_ORDERS    ", "ORDERS     ", "USER_ID    ", "USERS      ", "ID         "),
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)
        assert result[0].constraint_name == "FK_ORDERS"
        assert result[0].source_table == "ORDERS"
        assert result[0].source_column == "USER_ID"
        assert result[0].target_table == "USERS"
        assert result[0].target_column == "ID"

    def test_empty_result(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        result = adapter.get_foreign_keys(mock_conn)
        assert result == []


# -- Turso ---------------------------------------------------------------------

class TestTursoForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.turso.adapter import TursoAdapter
        return TursoAdapter()

    def test_returns_fk_info(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        # get_tables uses conn.execute().fetchall()
        tables_result = MagicMock()
        fk_result = MagicMock()
        mock_conn.execute.side_effect = [tables_result, fk_result]
        tables_result.fetchall.return_value = [("orders",)]
        fk_result.fetchall.return_value = [
            (0, 0, "users", "user_id", "id", "", "", ""),
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)
        assert result[0].source_table == "orders"
        assert result[0].target_table == "users"

    def test_empty_result(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        tables_result = MagicMock()
        fk_result = MagicMock()
        mock_conn.execute.side_effect = [tables_result, fk_result]
        tables_result.fetchall.return_value = [("orders",)]
        fk_result.fetchall.return_value = []
        result = adapter.get_foreign_keys(mock_conn)
        assert result == []


# -- Snowflake -----------------------------------------------------------------

class TestSnowflakeForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.snowflake.adapter import SnowflakeAdapter
        return SnowflakeAdapter()

    def test_returns_fk_info(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = [
            ("FK_ORDERS_USERS", "PUBLIC", "ORDERS", "USER_ID", "PUBLIC", "USERS", "ID"),
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)
        assert result[0].source_schema == "PUBLIC"

    def test_with_database_uses_prefix(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        adapter.get_foreign_keys(mock_conn, database="MYDB")
        sql = cursor.execute.call_args[0][0]
        assert '"MYDB".' in sql


# -- Spanner -------------------------------------------------------------------

class TestSpannerForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.spanner.adapter import SpannerAdapter
        return SpannerAdapter()

    def test_returns_fk_info(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        mock_conn.autocommit = False
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = [
            ("FK_Orders_Users", "Orders", "UserId", "Users", "Id"),
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)

    def test_empty_result(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        mock_conn.autocommit = False
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        result = adapter.get_foreign_keys(mock_conn)
        assert result == []


# -- HANA ----------------------------------------------------------------------

class TestHanaForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.hana.adapter import HanaAdapter
        return HanaAdapter()

    def test_returns_fk_info(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = [
            ("FK_ORDERS_USERS", "MYSCHEMA", "ORDERS", "USER_ID", "MYSCHEMA", "USERS", "ID"),
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)
        assert result[0].source_schema == "MYSCHEMA"

    def test_empty_result(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        result = adapter.get_foreign_keys(mock_conn)
        assert result == []


# -- DB2 -----------------------------------------------------------------------

class TestDb2ForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.db2.adapter import Db2Adapter
        return Db2Adapter()

    def test_returns_fk_info(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = [
            ("FK_ORDERS", "MYSCHEMA", "ORDERS", "USER_ID", "MYSCHEMA", "USERS", "ID"),
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)
        assert result[0].source_schema == "MYSCHEMA"

    def test_empty_result(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        result = adapter.get_foreign_keys(mock_conn)
        assert result == []

    def test_sql_uses_syscat(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        adapter.get_foreign_keys(mock_conn)
        sql = cursor.execute.call_args[0][0]
        assert "syscat.references" in sql


# -- Teradata ------------------------------------------------------------------

class TestTeradataForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.teradata.adapter import TeradataAdapter
        return TeradataAdapter()

    def test_returns_fk_info(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = [
            ("FK_ORDERS", "ORDERS", "USER_ID", "USERS", "ID", "MYDB", "MYDB"),
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)
        assert result[0].source_schema == "MYDB"

    def test_with_database(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        adapter.get_foreign_keys(mock_conn, database="MYDB")
        sql = cursor.execute.call_args[0][0]
        assert "ChildDB = ?" in sql

    def test_sql_uses_lock_row(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        adapter.get_foreign_keys(mock_conn)
        sql = cursor.execute.call_args[0][0]
        assert "lock row for access" in sql


# -- Redshift ------------------------------------------------------------------

class TestRedshiftForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.redshift.adapter import RedshiftAdapter
        return RedshiftAdapter()

    def test_returns_fk_info(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = [
            ("fk_orders_user_id", "public", "orders", "user_id", "public", "users", "id"),
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)
        assert result[0].source_schema == "public"

    def test_empty_result(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        result = adapter.get_foreign_keys(mock_conn)
        assert result == []

    def test_sql_excludes_system_schemas(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        adapter.get_foreign_keys(mock_conn)
        sql = cursor.execute.call_args[0][0]
        assert "pg_internal" in sql


# -- MotherDuck ----------------------------------------------------------------

class TestMotherDuckForeignKeys:
    def _make_adapter(self):
        from sqlit.domains.connections.providers.motherduck.adapter import MotherDuckAdapter
        return MotherDuckAdapter()

    def test_returns_fk_info(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("fk_orders_user_id", "main", "orders", "user_id", "main", "users", "id"),
        ]
        result = adapter.get_foreign_keys(mock_conn)
        _assert_fk_list(result, 1)
        assert result[0].source_schema == "main"

    def test_with_database_filters_by_catalog(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        adapter.get_foreign_keys(mock_conn, database="my_db")
        sql = mock_conn.execute.call_args[0][0]
        assert "table_catalog" in sql
        assert mock_conn.execute.call_args[0][1] == ("my_db",)

    def test_without_database_no_catalog_filter(self):
        adapter = self._make_adapter()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        adapter.get_foreign_keys(mock_conn)
        sql = mock_conn.execute.call_args[0][0]
        assert "table_catalog" not in sql
