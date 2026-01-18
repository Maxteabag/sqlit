"""UI tests for query history functionality."""

from __future__ import annotations

import pytest

from textual.widgets import OptionList

from sqlit.domains.query.store.history import QueryHistoryEntry
from sqlit.domains.query.ui.screens.query_history import QueryHistoryScreen
from sqlit.domains.shell.app.main import SSMSTUI

from .mocks import (
    MockConnectionStore,
    MockHistoryStore,
    MockSettingsStore,
    build_test_services,
    create_test_connection,
)


class TestQueryHistoryCursorMemory:
    """Tests for cursor position memory when switching between queries."""

    @pytest.mark.asyncio
    async def test_cursor_position_remembered_when_switching_queries(self):
        """Test that cursor position is saved and restored when switching queries via history."""
        connections = [create_test_connection("test-db", "sqlite")]
        mock_connections = MockConnectionStore(connections)
        mock_settings = MockSettingsStore({"theme": "tokyo-night"})

        services = build_test_services(
            connection_store=mock_connections,
            settings_store=mock_settings,
        )
        app = SSMSTUI(services=services)

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

        services = build_test_services(
            connection_store=mock_connections,
            settings_store=mock_settings,
        )
        app = SSMSTUI(services=services)

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

        services = build_test_services(
            connection_store=mock_connections,
            settings_store=mock_settings,
        )
        app = SSMSTUI(services=services)

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

        services = build_test_services(
            connection_store=mock_connections,
            settings_store=mock_settings,
        )
        app = SSMSTUI(services=services)

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


class TestQueryHistorySavePolicy:
    """Tests for query history behavior across saved and unsaved connections."""

    @pytest.mark.asyncio
    async def test_show_history_for_unsaved_connection_uses_session_history(self) -> None:
        unsaved_conn = create_test_connection("temp-db", "sqlite")
        history_store = MockHistoryStore()
        services = build_test_services(
            connection_store=MockConnectionStore([]),
            settings_store=MockSettingsStore({"theme": "tokyo-night"}),
            history_store=history_store,
        )
        app = SSMSTUI(services=services)

        async with app.run_test(size=(100, 35)) as pilot:
            app.current_config = unsaved_conn
            app._save_query_history(unsaved_conn, "SELECT 1")

            app.action_show_history()
            await pilot.pause(0.2)

            screen = next(
                (s for s in app.screen_stack if isinstance(s, QueryHistoryScreen)),
                None,
            )
            assert screen is not None, "History screen should be present"

            option_list = screen.query_one("#history-list", OptionList)
            assert option_list.option_count == 1

    def test_saved_connection_queries_saved(self) -> None:
        saved_conn = create_test_connection("saved-db", "sqlite")
        history_store = MockHistoryStore()
        services = build_test_services(
            connection_store=MockConnectionStore([saved_conn]),
            settings_store=MockSettingsStore({"theme": "tokyo-night"}),
            history_store=history_store,
        )
        app = SSMSTUI(services=services)
        app.connections = [saved_conn]

        app._save_query_history(saved_conn, "SELECT 1")

        assert history_store.entries["saved-db"][0]["query"] == "SELECT 1"

    @pytest.mark.asyncio
    async def test_telescope_hides_unavailable_unsaved_history(self) -> None:
        saved_conn = create_test_connection("saved-db", "sqlite")
        saved_entry = QueryHistoryEntry(
            query="select 1",
            timestamp="2026-01-01T00:00:00",
            connection_name="saved-db",
        )
        unsaved_entry = QueryHistoryEntry(
            query="select 2",
            timestamp="2026-01-02T00:00:00",
            connection_name="temp-db",
        )

        class StubHistoryStore:
            def __init__(self, entries):
                self._entries = entries

            def load_all(self):
                return list(self._entries)

            def load_for_connection(self, connection_name):
                return [e for e in self._entries if e.connection_name == connection_name]

            def delete_entry(self, connection_name, timestamp):
                _ = connection_name
                _ = timestamp
                return False

            def save_query(self, connection_name, query):
                _ = connection_name
                _ = query

        history_store = StubHistoryStore([saved_entry, unsaved_entry])
        services = build_test_services(
            connection_store=MockConnectionStore([saved_conn]),
            settings_store=MockSettingsStore({"theme": "tokyo-night"}),
            history_store=history_store,
        )
        app = SSMSTUI(services=services)

        async with app.run_test(size=(100, 35)) as pilot:
            app.connections = [saved_conn]
            app.action_telescope()
            await pilot.pause(0.2)

            screen = next(
                (s for s in app.screen_stack if isinstance(s, QueryHistoryScreen)),
                None,
            )
            assert screen is not None, "Telescope screen should be present"

            option_list = screen.query_one("#history-list", OptionList)
            assert option_list.option_count == 1
            assert all(entry.connection_name == "saved-db" for entry in screen._merged_entries)
