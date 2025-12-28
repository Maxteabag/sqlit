"""UI tests for query history functionality."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sqlit.app import SSMSTUI

from .mocks import MockConnectionStore, MockSettingsStore, create_test_connection


class TestQueryHistoryCursorMemory:
    """Tests for cursor position memory when switching between queries."""

    @pytest.mark.asyncio
    async def test_cursor_position_remembered_when_switching_queries(self):
        """Test that cursor position is saved and restored when switching queries via history."""
        connections = [create_test_connection("test-db", "sqlite")]
        mock_connections = MockConnectionStore(connections)
        mock_settings = MockSettingsStore({"theme": "tokyo-night"})

        with (
            patch("sqlit.app.load_connections", mock_connections.load_all),
            patch("sqlit.theme_manager.load_settings", mock_settings.load_all),
            patch("sqlit.theme_manager.save_settings", mock_settings.save_all),
        ):
            app = SSMSTUI()

            async with app.run_test(size=(100, 35)) as pilot:
                # Set first query and position cursor at a specific location
                query_a = "SELECT * FROM users"
                app.query_input.text = query_a
                await pilot.pause()

                # Move cursor to position (0, 7) - after "SELECT "
                app.query_input.cursor_location = (0, 7)
                await pilot.pause()

                # Verify cursor is at expected position
                assert app.query_input.cursor_location == (0, 7)

                # Simulate selecting a different query from history
                # This calls _handle_history_result directly
                query_b = "SELECT id, name FROM products"
                app._handle_history_result(("select", query_b))
                await pilot.pause()

                # Verify query changed
                assert app.query_input.text == query_b

                # Move cursor to a different position in query B
                app.query_input.cursor_location = (0, 10)
                await pilot.pause()

                # Now switch back to query A
                app._handle_history_result(("select", query_a))
                await pilot.pause()

                # Verify query A is back
                assert app.query_input.text == query_a

                # Verify cursor position is restored to (0, 7)
                assert app.query_input.cursor_location == (0, 7)

    @pytest.mark.asyncio
    async def test_cursor_position_at_end_for_new_query(self):
        """Test that cursor goes to end for a query not previously edited."""
        connections = [create_test_connection("test-db", "sqlite")]
        mock_connections = MockConnectionStore(connections)
        mock_settings = MockSettingsStore({"theme": "tokyo-night"})

        with (
            patch("sqlit.app.load_connections", mock_connections.load_all),
            patch("sqlit.theme_manager.load_settings", mock_settings.load_all),
            patch("sqlit.theme_manager.save_settings", mock_settings.save_all),
        ):
            app = SSMSTUI()

            async with app.run_test(size=(100, 35)) as pilot:
                # Start with empty query
                app.query_input.text = ""
                await pilot.pause()

                # Select a query from history that was never edited before
                new_query = "SELECT * FROM orders"
                app._handle_history_result(("select", new_query))
                await pilot.pause()

                # Verify cursor is at end of query
                expected_col = len(new_query)
                assert app.query_input.cursor_location == (0, expected_col)

    @pytest.mark.asyncio
    async def test_cursor_position_for_multiline_query(self):
        """Test cursor position memory works for multiline queries."""
        connections = [create_test_connection("test-db", "sqlite")]
        mock_connections = MockConnectionStore(connections)
        mock_settings = MockSettingsStore({"theme": "tokyo-night"})

        with (
            patch("sqlit.app.load_connections", mock_connections.load_all),
            patch("sqlit.theme_manager.load_settings", mock_settings.load_all),
            patch("sqlit.theme_manager.save_settings", mock_settings.save_all),
        ):
            app = SSMSTUI()

            async with app.run_test(size=(100, 35)) as pilot:
                # Set multiline query
                query_multiline = "SELECT *\nFROM users\nWHERE id = 1"
                app.query_input.text = query_multiline
                await pilot.pause()

                # Position cursor on second line (row 1, col 5) - "FROM "
                app.query_input.cursor_location = (1, 5)
                await pilot.pause()

                # Switch to another query
                query_other = "SELECT 1"
                app._handle_history_result(("select", query_other))
                await pilot.pause()

                # Switch back
                app._handle_history_result(("select", query_multiline))
                await pilot.pause()

                # Verify cursor is restored to (1, 5)
                assert app.query_input.cursor_location == (1, 5)

    @pytest.mark.asyncio
    async def test_cursor_cache_handles_same_query_text(self):
        """Test that identical query text shares cursor position."""
        connections = [create_test_connection("test-db", "sqlite")]
        mock_connections = MockConnectionStore(connections)
        mock_settings = MockSettingsStore({"theme": "tokyo-night"})

        with (
            patch("sqlit.app.load_connections", mock_connections.load_all),
            patch("sqlit.theme_manager.load_settings", mock_settings.load_all),
            patch("sqlit.theme_manager.save_settings", mock_settings.save_all),
        ):
            app = SSMSTUI()

            async with app.run_test(size=(100, 35)) as pilot:
                # Set query and cursor position
                query = "SELECT * FROM users"
                app.query_input.text = query
                app.query_input.cursor_location = (0, 5)
                await pilot.pause()

                # Switch away
                app._handle_history_result(("select", "SELECT 1"))
                await pilot.pause()

                # Select the same query text again (simulating it appearing twice in history)
                app._handle_history_result(("select", query))
                await pilot.pause()

                # Cursor should be at the remembered position
                assert app.query_input.cursor_location == (0, 5)
