"""UI tests for query history functionality."""

from __future__ import annotations

import pytest

from textual.widgets import OptionList

from sqlit.domains.query.store.history import QueryHistoryEntry
from sqlit.domains.query.store.memory import InMemoryHistoryStore
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

    @pytest.mark.asyncio
    async def test_show_history_for_unsaved_connection_with_duplicates(self) -> None:
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


class TestQueryHistoryStarringDuplicates:
    """Regression tests for starring behavior when multiple history entries
    share the same query text (e.g., same SQL run against multiple databases
    on one connection — file-backed dedup is per-(connection, database))."""

    def _make_screen(
        self,
        history: list[QueryHistoryEntry],
        starred: set[str],
        connection_name: str = "saved-db",
    ) -> QueryHistoryScreen:
        return QueryHistoryScreen(
            history=history,
            connection_name=connection_name,
            starred=starred,
        )

    def test_same_query_across_databases_collapses_to_single_row(self) -> None:
        history = [
            QueryHistoryEntry(
                query="SELECT 1",
                timestamp="2026-01-02T00:00:00",
                connection_name="saved-db",
                database="db_a",
            ),
            QueryHistoryEntry(
                query="SELECT 1",
                timestamp="2026-01-01T00:00:00",
                connection_name="saved-db",
                database="db_b",
            ),
        ]
        screen = self._make_screen(history, starred={"SELECT 1"})

        merged = screen._merge_entries()

        assert len(merged) == 1, (
            "Same query text from two databases should collapse to one row "
            "in the history display (starring is keyed by text, so the row "
            "count must match)."
        )
        assert merged[0].is_starred
        # Most-recent occurrence wins the row.
        assert merged[0].database == "db_a"

    @pytest.mark.asyncio
    async def test_starring_one_marks_duplicate_in_other_database(self) -> None:
        saved_conn = create_test_connection("saved-db", "sqlite")
        entries = [
            QueryHistoryEntry(
                query="SELECT 1",
                timestamp="2026-01-02T00:00:00",
                connection_name="saved-db",
                database="db_a",
            ),
            QueryHistoryEntry(
                query="SELECT 1",
                timestamp="2026-01-01T00:00:00",
                connection_name="saved-db",
                database="db_b",
            ),
        ]

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

            def save_query(self, connection_name, query, database=""):
                _ = connection_name
                _ = query
                _ = database

        history_store = StubHistoryStore(entries)
        services = build_test_services(
            connection_store=MockConnectionStore([saved_conn]),
            settings_store=MockSettingsStore({"theme": "tokyo-night"}),
            history_store=history_store,
        )
        app = SSMSTUI(services=services)

        async with app.run_test(size=(100, 35)) as pilot:
            app.connections = [saved_conn]
            app.current_config = saved_conn

            # Open history, star the first row (which corresponds to db_a),
            # close — emulates: user opens history, presses '*' on one row.
            app.action_show_history()
            await pilot.pause(0.2)
            screen = next(
                (s for s in app.screen_stack if isinstance(s, QueryHistoryScreen)),
                None,
            )
            assert screen is not None
            option_list = screen.query_one("#history-list", OptionList)
            # The two same-text rows should already be collapsed to one.
            assert option_list.option_count == 1
            assert option_list.highlighted == 0
            screen.action_toggle_star()
            await pilot.pause(0.2)

            # Re-open: exactly one starred row, not two.
            app.action_show_history()
            await pilot.pause(0.2)
            screen = next(
                (s for s in app.screen_stack if isinstance(s, QueryHistoryScreen)),
                None,
            )
            assert screen is not None
            starred_entries = [e for e in screen._merged_entries if e.is_starred]
            try:
                assert len(starred_entries) == 1, (
                    f"Expected exactly one starred row after toggling one; "
                    f"got {len(starred_entries)}"
                )
            finally:
                # The shared test config dir is module-scoped (see
                # tests/fixtures/utils.py), so any star we save here would
                # leak to later tests. Clean up.
                services.starred_store.clear_for_connection(saved_conn.name)


class TestQueryHistoryBracketIdentifierRendering:
    """Regression tests for MSSQL bracket identifiers like [dbo].[ServiceFeatures]
    being silently eaten by Textual markup when the bracket contents start with
    an uppercase letter (rich.markup.escape only escapes [a-z#/@] tags)."""

    @pytest.mark.asyncio
    async def test_bracket_identifier_with_uppercase_not_truncated(self) -> None:
        from textual.app import App
        from textual.widgets.option_list import Option

        # Drive the option directly through a minimal Textual app so we
        # observe what _build_option's text actually renders to.
        screen = QueryHistoryScreen(
            history=[
                QueryHistoryEntry(
                    query="SELECT TOP 100 * FROM [dbo].[ServiceFeatures]",
                    timestamp="2026-01-01T00:00:00",
                    connection_name="saved-db",
                ),
            ],
            connection_name="saved-db",
            starred=set(),
        )
        screen._merged_entries = screen._merge_entries()
        built = screen._build_option(screen._merged_entries[0])

        class _ProbeApp(App):
            def compose(self):
                yield OptionList(Option(built.prompt, id=built.id or "probe"), id="probe-list")

        app = _ProbeApp()
        async with app.run_test(size=(120, 10)) as pilot:
            await pilot.pause()
            option_list = app.query_one("#probe-list", OptionList)
            lines = option_list.render_lines(option_list.region)
            rendered_text = "\n".join(
                "".join(seg.text for seg in line) for line in lines
            )

        assert "[ServiceFeatures]" in rendered_text, (
            "Bracket identifier with uppercase first letter was silently "
            "swallowed by Textual markup (rich.markup.escape only escapes "
            "tags starting with [a-z#/@], so '[ServiceFeatures]' is left "
            "unescaped and the markup parser eats it). Visible text:\n"
            + rendered_text
        )


class TestQueryHistoryVimNavigation:
    """Tests for j/k vim-style navigation in the history screen."""

    @pytest.mark.asyncio
    async def test_j_moves_cursor_down_and_k_moves_up(self) -> None:
        saved_conn = create_test_connection("saved-db", "sqlite")
        entries = [
            QueryHistoryEntry(
                query=f"select {i}",
                timestamp=f"2026-01-0{i}T00:00:00",
                connection_name="saved-db",
            )
            for i in range(1, 4)
        ]

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

        history_store = StubHistoryStore(entries)
        services = build_test_services(
            connection_store=MockConnectionStore([saved_conn]),
            settings_store=MockSettingsStore({"theme": "tokyo-night"}),
            history_store=history_store,
        )
        app = SSMSTUI(services=services)

        async with app.run_test(size=(100, 35)) as pilot:
            app.connections = [saved_conn]
            app.current_config = saved_conn
            app.action_show_history()
            await pilot.pause(0.2)

            screen = next(
                (s for s in app.screen_stack if isinstance(s, QueryHistoryScreen)),
                None,
            )
            assert screen is not None

            option_list = screen.query_one("#history-list", OptionList)
            assert option_list.option_count == 3
            assert option_list.highlighted == 0

            await pilot.press("j")
            assert option_list.highlighted == 1

            await pilot.press("j")
            assert option_list.highlighted == 2

            await pilot.press("k")
            assert option_list.highlighted == 1

    @pytest.mark.asyncio
    async def test_j_and_k_typeable_when_filter_active(self) -> None:
        saved_conn = create_test_connection("saved-db", "sqlite")
        entries = [
            QueryHistoryEntry(
                query="select jk_marker",
                timestamp="2026-01-01T00:00:00",
                connection_name="saved-db",
            ),
            QueryHistoryEntry(
                query="select other",
                timestamp="2026-01-02T00:00:00",
                connection_name="saved-db",
            ),
        ]

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

        history_store = StubHistoryStore(entries)
        services = build_test_services(
            connection_store=MockConnectionStore([saved_conn]),
            settings_store=MockSettingsStore({"theme": "tokyo-night"}),
            history_store=history_store,
        )
        app = SSMSTUI(services=services)

        async with app.run_test(size=(100, 35)) as pilot:
            app.connections = [saved_conn]
            app.current_config = saved_conn
            app.action_show_history()
            await pilot.pause(0.2)

            screen = next(
                (s for s in app.screen_stack if isinstance(s, QueryHistoryScreen)),
                None,
            )
            assert screen is not None

            await pilot.press("slash")
            await pilot.pause()
            assert screen._filter_active

            await pilot.press("j")
            await pilot.press("k")
            await pilot.pause()
            assert screen._filter_text == "jk"
