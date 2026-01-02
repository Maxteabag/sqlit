"""Unit tests for Snowflake adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests.helpers import ConnectionConfig


class TestSnowflakeAdapter:
    """Test Snowflake adapter operations."""

    def test_connect_standard_args(self):
        """Test connecting with standard arguments."""
        mock_snowflake = MagicMock()

        with patch.dict("sys.modules", {"snowflake.connector": mock_snowflake}):
            from sqlit.domains.connections.providers.snowflake.adapter import SnowflakeAdapter

            adapter = SnowflakeAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="snowflake",
                server="xy12345.us-east-1",
                database="TEST_DB",
                username="testuser",
                password="testpass",
            )

            adapter.connect(config)

            mock_snowflake.connect.assert_called_once_with(
                user="testuser",
                password="testpass",
                account="xy12345.us-east-1",
                database="TEST_DB",
            )

    def test_connect_with_extra_args(self):
        """Test connecting with warehouse, schema, and role."""
        mock_snowflake = MagicMock()

        with patch.dict("sys.modules", {"snowflake.connector": mock_snowflake}):
            from sqlit.domains.connections.providers.snowflake.adapter import SnowflakeAdapter

            adapter = SnowflakeAdapter()
            # Simulate extras passing via dynamic attribute or similar if possible.
            # In real app, extras might be passed via config.options or similar.
            # My adapter implementation checks `getattr(config, "extras", {})`.

            # Since ConnectionConfig is a dataclass/Pydantic model, we can't easily add attributes if it's frozen or slotted.
            # But let's see if we can subclass or mock ConnectionConfig.

            config = ConnectionConfig(
                name="test",
                db_type="snowflake",
                server="xy12345",
                database="TEST_DB",
                username="testuser",
                password="testpass",
                options={
                    "warehouse": "COMPUTE_WH",
                    "schema": "ANALYTICS",
                    "role": "DATA_ENGINEER",
                }
            )

            adapter.connect(config)

            mock_snowflake.connect.assert_called_once_with(
                user="testuser",
                password="testpass",
                account="xy12345",
                database="TEST_DB",
                warehouse="COMPUTE_WH",
                schema="ANALYTICS",
                role="DATA_ENGINEER",
            )

    def test_get_databases(self):
        """Test fetching database list."""
        mock_snowflake = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_snowflake.connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock SHOW DATABASES response
        # created_on, name, is_default, is_current, origin, owner, comment, options, retention_time
        mock_cursor.fetchall.return_value = [
            ("date", "DB1", "N", "N", "", "", "", "", 1),
            ("date", "DB2", "N", "N", "", "", "", "", 1),
        ]

        with patch.dict("sys.modules", {"snowflake.connector": mock_snowflake}):
            from sqlit.domains.connections.providers.snowflake.adapter import SnowflakeAdapter
            adapter = SnowflakeAdapter()

            dbs = adapter.get_databases(mock_conn)

            mock_cursor.execute.assert_called_with("SHOW DATABASES")
            assert dbs == ["DB1", "DB2"]

    def test_get_tables(self):
        """Test fetching tables."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        # Mock SHOW TABLES output
        # created_on, name, database_name, schema_name, kind, comment, cluster_by, owner, bytes, rows, retention_time
        # We need row[1] (name) and row[3] (schema_name)
        mock_cursor.fetchall.return_value = [
            ("date", "TABLE1", "DB", "PUBLIC", "TABLE", "", "", "", 0, 0, 1),
            ("date", "TABLE2", "DB", "OTHER_SCHEMA", "TABLE", "", "", "", 0, 0, 1),
        ]

        # Test default fallback to information_schema if SHOW TABLES behavior is tricky to mock perfectly?
        # My implementation uses get_tables_via_info_schema by default now (in final code I wrote).
        # Let's check what I wrote:
        # def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        #    return self.get_tables_via_info_schema(conn, database)

        # So I should mock info schema query results.
        mock_cursor.fetchall.return_value = [
            ("PUBLIC", "TABLE1"),
            ("OTHER_SCHEMA", "TABLE2"),
        ]

        with patch.dict("sys.modules", {"snowflake.connector": MagicMock()}):
            from sqlit.domains.connections.providers.snowflake.adapter import SnowflakeAdapter
            adapter = SnowflakeAdapter()

            tables = adapter.get_tables(mock_conn, database="TEST_DB")

            assert tables == [("PUBLIC", "TABLE1"), ("OTHER_SCHEMA", "TABLE2")]
            # Verify correct query
            mock_cursor.execute.assert_called()
            call_arg = mock_cursor.execute.call_args[0][0]
            assert "information_schema.tables" in call_arg
            assert "TEST_DB" in call_arg

    def test_get_columns(self):
        """Test fetching columns."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        # Mock columns query result
        # column_name, data_type, ordinal_position
        mock_cursor.fetchall.side_effect = [
            [("col1", "VARCHAR", 1), ("col2", "NUMBER", 2)], # First call for columns
            [("col1",)], # Second call for PKs
        ]

        with patch.dict("sys.modules", {"snowflake.connector": MagicMock()}):
            from sqlit.domains.connections.providers.snowflake.adapter import SnowflakeAdapter
            adapter = SnowflakeAdapter()

            cols = adapter.get_columns(mock_conn, "MY_TABLE", database="TEST_DB", schema="PUBLIC")

            assert len(cols) == 2
            assert cols[0].name == "col1"
            assert cols[0].data_type == "VARCHAR"
            assert cols[0].is_primary_key is True
            assert cols[1].name == "col2"
            assert cols[1].is_primary_key is False

    def test_quote_identifier(self):
        with patch.dict("sys.modules", {"snowflake.connector": MagicMock()}):
            from sqlit.domains.connections.providers.snowflake.adapter import SnowflakeAdapter
            adapter = SnowflakeAdapter()

            assert adapter.quote_identifier("foo") == '"foo"'
            assert adapter.quote_identifier('foo"bar') == '"foo""bar"'

    def test_build_select_query(self):
        with patch.dict("sys.modules", {"snowflake.connector": MagicMock()}):
            from sqlit.domains.connections.providers.snowflake.adapter import SnowflakeAdapter
            adapter = SnowflakeAdapter()

            query = adapter.build_select_query("MY_TABLE", 10, schema="MYSCHEMA")
            assert query == 'SELECT * FROM "MYSCHEMA"."MY_TABLE" LIMIT 10'
