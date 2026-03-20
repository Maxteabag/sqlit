"""UI test for telescope on fresh start (no active connection).

Regression tests:
1. _pending_telescope_query must be set before connecting so the
   post-connection callback can pick up the query.
2. When the connection config has no default database but the history
   query was run against a specific database, telescope should try to
   extract and apply the database context from the query.
"""

from __future__ import annotations

import pytest

from sqlit.domains.query.store.history import QueryHistoryEntry
from sqlit.domains.shell.app.main import SSMSTUI

from .mocks import (
    MockConnectionStore,
    MockSettingsStore,
    build_test_services,
    create_test_connection,
)


class StubHistoryStore:
    def __init__(self, entries):
        self._entries = list(entries)

    def load_all(self):
        return list(self._entries)

    def load_for_connection(self, cn):
        return [e for e in self._entries if e.connection_name == cn]

    def delete_entry(self, cn, ts):
        return False

    def save_query(self, cn, q):
        pass


def _make_app():
    saved_conn = create_test_connection("my-server", "sqlite")
    entry = QueryHistoryEntry(
        query="SELECT * FROM users",
        timestamp="2026-01-01T00:00:00",
        connection_name="my-server",
    )
    services = build_test_services(
        connection_store=MockConnectionStore([saved_conn]),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
        history_store=StubHistoryStore([entry]),
    )
    return SSMSTUI(services=services), saved_conn


class TestTelescopePendingQuery:
    """_pending_telescope_query must be set before connecting."""

    @pytest.mark.asyncio
    async def test_pending_query_set_before_connecting(self) -> None:
        app, saved_conn = _make_app()

        async with app.run_test(size=(120, 40)) as pilot:
            app.connections = [saved_conn]
            await pilot.pause()

            assert app.current_connection is None

            app._run_telescope_query("my-server", "SELECT * FROM users")

            pending = getattr(app, "_pending_telescope_query", None)
            assert pending is not None, (
                "_pending_telescope_query should be set before connecting, "
                "but it was None (cleared prematurely)"
            )
            assert pending[0] == "my-server"
            assert pending[1] == "SELECT * FROM users"

    @pytest.mark.asyncio
    async def test_no_error_after_telescope_select(self) -> None:
        app, saved_conn = _make_app()

        async with app.run_test(size=(120, 40)) as pilot:
            app.connections = [saved_conn]
            await pilot.pause()

            assert app.current_connection is None

            app._handle_telescope_result((
                "select",
                {"query": "SELECT * FROM users", "connection_name": "my-server"},
            ))
            await pilot.pause(1.0)

            from sqlit.shared.ui.screens.error import ErrorScreen
            error_screens = [s for s in app.screen_stack if isinstance(s, ErrorScreen)]
            assert not error_screens, "ErrorScreen should not appear after telescope select"

            assert app.current_connection is not None
            assert app.query_input.text == "SELECT * FROM users"
