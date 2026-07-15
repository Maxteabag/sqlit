"""Unit tests for MySQL-compatible adapter behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestMySQLProcedureDefinition:
    """Tests for stored procedure definition retrieval."""

    @pytest.fixture
    def mock_pymysql(self):
        """Create a mock pymysql module."""
        mock = MagicMock()
        with patch.dict("sys.modules", {"pymysql": mock}):
            yield mock

    @pytest.fixture
    def adapter(self, mock_pymysql):
        """Create a MySQL adapter instance."""
        from sqlit.domains.connections.providers.mysql.adapter import MySQLAdapter

        return MySQLAdapter()

    @pytest.fixture
    def mock_conn(self):
        """Create a mock connection with cursor."""
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def test_get_procedure_definition_with_database(self, adapter, mock_conn):
        """Test that SHOW CREATE PROCEDURE is qualified with the database."""
        cursor = mock_conn.cursor.return_value
        cursor.fetchone.return_value = (
            "my_proc",
            "STRICT_TRANS_TABLES",
            "CREATE PROCEDURE `my_proc`() BEGIN SELECT 1; END",
            "utf8mb4",
            "utf8mb4_general_ci",
            "utf8mb4_general_ci",
        )

        result = adapter.get_procedure_definition(mock_conn, "my_proc", database="mydb")

        assert result["name"] == "my_proc"
        assert result["schema"] == "mydb"
        assert result["language"] == "SQL"
        assert "CREATE PROCEDURE" in result["definition"]
        cursor.execute.assert_called_once()
        executed = cursor.execute.call_args[0][0]
        assert "SHOW CREATE PROCEDURE" in executed
        assert "`mydb`" in executed
        assert "`my_proc`" in executed

    def test_get_procedure_definition_without_database(self, adapter, mock_conn):
        """Test that SHOW CREATE PROCEDURE is unqualified when no database is given."""
        cursor = mock_conn.cursor.return_value
        cursor.fetchone.return_value = (
            "my_proc",
            "STRICT_TRANS_TABLES",
            "CREATE PROCEDURE `my_proc`() BEGIN SELECT 1; END",
            "utf8mb4",
            "utf8mb4_general_ci",
            "utf8mb4_general_ci",
        )

        result = adapter.get_procedure_definition(mock_conn, "my_proc")

        assert result["name"] == "my_proc"
        assert result["schema"] == ""
        assert result["language"] == "SQL"
        assert "CREATE PROCEDURE" in result["definition"]
        cursor.execute.assert_called_once()
        executed = cursor.execute.call_args[0][0]
        assert executed == "SHOW CREATE PROCEDURE `my_proc`"

    def test_get_procedure_definition_not_found(self, adapter, mock_conn):
        """Test that missing procedure returns empty definition."""
        cursor = mock_conn.cursor.return_value
        cursor.fetchone.return_value = None

        result = adapter.get_procedure_definition(mock_conn, "missing_proc", database="mydb")

        assert result["name"] == "missing_proc"
        assert result["definition"] is None
        assert result["language"] is None
