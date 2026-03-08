"""Tests for Oracle adapter cursor cleanup.

These tests verify that the Oracle adapter properly closes cursors after use.
Unclosed cursors can cause executor hangs on exit.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter


class TestOracleAdapterCursorCleanup:
    """Tests that Oracle adapter closes cursors after each operation.

    When VPN drops and reconnects, unclosed cursors hold stale
    network handles, causing the executor thread to hang on exit.
    """

    @pytest.fixture
    def adapter(self) -> OracleAdapter:
        return OracleAdapter()

    @pytest.fixture
    def mock_conn(self) -> MagicMock:
        """Create a mock connection that tracks cursor creation and closure."""
        conn = MagicMock()
        cursors: list[MagicMock] = []

        def create_cursor() -> MagicMock:
            cursor = MagicMock()
            cursor.fetchall.return_value = []
            cursor.fetchone.return_value = None
            cursor.fetchmany.return_value = []
            cursor.description = None
            cursor.rowcount = 0
            cursors.append(cursor)
            return cursor

        conn.cursor.side_effect = create_cursor
        conn._cursors = cursors  # Store for assertion access
        return conn

    def test_get_tables_closes_cursor(self, adapter: OracleAdapter, mock_conn: MagicMock) -> None:
        """get_tables should close its cursor after use."""
        adapter.get_tables(mock_conn)

        assert len(mock_conn._cursors) == 1
        mock_conn._cursors[0].close.assert_called_once()

    def test_get_views_closes_cursor(self, adapter: OracleAdapter, mock_conn: MagicMock) -> None:
        """get_views should close its cursor after use."""
        adapter.get_views(mock_conn)

        assert len(mock_conn._cursors) == 1
        mock_conn._cursors[0].close.assert_called_once()

    def test_get_columns_closes_all_cursors(self, adapter: OracleAdapter, mock_conn: MagicMock) -> None:
        """get_columns creates 2 cursors (pk lookup + columns) and should close both."""
        adapter.get_columns(mock_conn, "TEST_TABLE")

        # get_columns uses 2 cursors: one for PK, one for columns
        assert len(mock_conn._cursors) == 2
        for cursor in mock_conn._cursors:
            cursor.close.assert_called_once()

    def test_get_procedures_closes_cursor(self, adapter: OracleAdapter, mock_conn: MagicMock) -> None:
        """get_procedures should close its cursor after use."""
        adapter.get_procedures(mock_conn)

        assert len(mock_conn._cursors) == 1
        mock_conn._cursors[0].close.assert_called_once()

    def test_get_indexes_closes_cursor(self, adapter: OracleAdapter, mock_conn: MagicMock) -> None:
        """get_indexes should close its cursor after use."""
        adapter.get_indexes(mock_conn)

        assert len(mock_conn._cursors) == 1
        mock_conn._cursors[0].close.assert_called_once()

    def test_get_triggers_closes_cursor(self, adapter: OracleAdapter, mock_conn: MagicMock) -> None:
        """get_triggers should close its cursor after use."""
        adapter.get_triggers(mock_conn)

        assert len(mock_conn._cursors) == 1
        mock_conn._cursors[0].close.assert_called_once()

    def test_get_sequences_closes_cursor(self, adapter: OracleAdapter, mock_conn: MagicMock) -> None:
        """get_sequences should close its cursor after use."""
        adapter.get_sequences(mock_conn)

        assert len(mock_conn._cursors) == 1
        mock_conn._cursors[0].close.assert_called_once()

    def test_get_index_definition_closes_all_cursors(self, adapter: OracleAdapter, mock_conn: MagicMock) -> None:
        """get_index_definition creates multiple cursors and should close all."""
        # Setup mock to return data for first query
        mock_conn._cursors = []  # Reset

        def create_cursor() -> MagicMock:
            cursor = MagicMock()
            cursor.fetchall.return_value = []
            cursor.fetchone.return_value = ("UNIQUE", "NORMAL")
            cursor.description = None
            mock_conn._cursors.append(cursor)
            return cursor

        mock_conn.cursor.side_effect = create_cursor

        adapter.get_index_definition(mock_conn, "TEST_IDX", "TEST_TABLE")

        # get_index_definition uses 3 cursors: index info, columns, DDL
        assert len(mock_conn._cursors) >= 2
        for cursor in mock_conn._cursors:
            cursor.close.assert_called_once()

    def test_get_trigger_definition_closes_cursor(self, adapter: OracleAdapter, mock_conn: MagicMock) -> None:
        """get_trigger_definition should close its cursor after use."""
        adapter.get_trigger_definition(mock_conn, "TEST_TRG", "TEST_TABLE")

        assert len(mock_conn._cursors) == 1
        mock_conn._cursors[0].close.assert_called_once()

    def test_get_sequence_definition_closes_cursor(self, adapter: OracleAdapter, mock_conn: MagicMock) -> None:
        """get_sequence_definition should close its cursor after use."""
        adapter.get_sequence_definition(mock_conn, "TEST_SEQ")

        assert len(mock_conn._cursors) == 1
        mock_conn._cursors[0].close.assert_called_once()

    def test_execute_query_closes_cursor(self, adapter: OracleAdapter, mock_conn: MagicMock) -> None:
        """execute_query should close its cursor after use."""
        adapter.execute_query(mock_conn, "SELECT 1 FROM DUAL")

        assert len(mock_conn._cursors) == 1
        mock_conn._cursors[0].close.assert_called_once()

    def test_execute_non_query_closes_cursor(self, adapter: OracleAdapter, mock_conn: MagicMock) -> None:
        """execute_non_query should close its cursor after use."""
        adapter.execute_non_query(mock_conn, "UPDATE test SET x = 1")

        assert len(mock_conn._cursors) == 1
        mock_conn._cursors[0].close.assert_called_once()

    def test_cursor_closed_even_on_exception(self, adapter: OracleAdapter, mock_conn: MagicMock) -> None:
        """Cursors should be closed even if an exception occurs during execution."""
        mock_conn._cursors = []

        def create_failing_cursor() -> MagicMock:
            cursor = MagicMock()
            cursor.execute.side_effect = Exception("DB Error")
            mock_conn._cursors.append(cursor)
            return cursor

        mock_conn.cursor.side_effect = create_failing_cursor

        with pytest.raises(Exception, match="DB Error"):
            adapter.get_tables(mock_conn)

        # Cursor should still be closed even though execute() raised
        assert len(mock_conn._cursors) == 1
        mock_conn._cursors[0].close.assert_called_once()
