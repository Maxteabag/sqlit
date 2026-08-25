"""Opt-in screenshot gallery for the saved-query document workflow."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from textual.widgets import Input

from sqlit.domains.explorer.ui.tree.builder import add_saved_query_nodes
from sqlit.domains.query.store.saved_queries import SavedQueryStore
from sqlit.domains.query.ui.screens import (
    ExternalQueryChangeScreen,
    QueryLibraryScreen,
    SavedQueryNameScreen,
    UnsavedQueryChangesScreen,
)
from sqlit.domains.shell.app.main import SSMSTUI
from sqlit.shared.ui.screens.confirm import ConfirmScreen
from sqlit.shared.ui.widgets import FilterInput
from tests.ui.mocks import (
    MockConnectionStore,
    MockHistoryStore,
    MockSettingsStore,
    build_test_services,
    create_test_connection,
)

_OUTPUT = os.environ.get("SQLIT_SAVED_QUERY_SCREENSHOTS_DIR")
pytestmark = pytest.mark.skipif(not _OUTPUT, reason="screenshot output is not configured")


def _shot(app: SSMSTUI, output: Path, name: str) -> None:
    app.save_screenshot(path=output, filename=f"{name}.svg")


@pytest.mark.asyncio
async def test_saved_query_workflow_gallery(tmp_path: Path) -> None:
    assert _OUTPUT is not None
    output = Path(_OUTPUT)
    output.mkdir(parents=True, exist_ok=True)
    for old in output.glob("*.svg"):
        old.unlink()

    connection = create_test_connection("production-reporting", "sqlite")
    empty_connection = create_test_connection("new-analytics", "sqlite")
    store = SavedQueryStore(tmp_path / "saved-queries")
    services = build_test_services(
        connection_store=MockConnectionStore([connection, empty_connection]),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
        history_store=MockHistoryStore(),
        saved_query_store=store,
    )
    app = SSMSTUI(services=services)
    app.connections = [connection, empty_connection]
    app.current_config = connection

    async with app.run_test(size=(128, 42)) as pilot:
        app.query_input.focus()
        app.query_input.text = "SELECT customer_id, SUM(total) AS revenue\nFROM orders\nGROUP BY customer_id;"
        await pilot.pause()
        app._update_section_labels()
        _shot(app, output, "01-untitled-dirty")

        app.action_save_query()
        await pilot.pause()
        assert isinstance(app.screen, SavedQueryNameScreen)
        _shot(app, output, "02-save-query-name")
        app.screen.query_one(Input).value = "reports/daily-revenue"
        app.screen.action_save()
        await pilot.pause()
        store.save(
            connection.name,
            "diagnostics/blocked-sessions",
            "SELECT session_id, wait_type\nFROM blocked_sessions\nORDER BY session_id;",
        )
        store.save(
            connection.name,
            "reports/monthly-summary",
            "SELECT month, SUM(total)\nFROM orders\nGROUP BY month;",
        )
        connection_node = app._find_connection_node_by_name(connection.name)
        assert connection_node is not None
        add_saved_query_nodes(app, connection_node)
        connection_node.expand()
        saved_root = connection_node.children[0]
        saved_root.expand()
        for child in saved_root.children:
            if child.data.get_node_kind() == "saved_query_folder":
                child.expand()
        app.query_input.focus()
        app._update_section_labels()
        _shot(app, output, "03-saved-clean-document")

        app.action_query_library()
        await pilot.pause()
        assert isinstance(app.screen, QueryLibraryScreen)
        _shot(app, output, "04-query-library")
        app.screen.action_open_filter()
        await pilot.press("b", "l", "o", "c", "k", "e", "d")
        assert app.screen.query_one(FilterInput).filter_text == "blocked"
        _shot(app, output, "05-query-library-search")
        # First Escape closes the transient filter, second closes the library.
        app.screen.action_cancel()
        await pilot.pause()
        app.screen.action_cancel()
        await pilot.pause()

        app.query_input.text += "\n-- local edit"
        app.action_new_query()
        await pilot.pause()
        assert isinstance(app.screen, UnsavedQueryChangesScreen)
        _shot(app, output, "06-unsaved-changes")
        app.screen.action_cancel()
        await pilot.pause()

        app.action_save_query_as()
        await pilot.pause()
        assert isinstance(app.screen, SavedQueryNameScreen)
        _shot(app, output, "07-save-query-as")
        app.screen.query_one(Input).value = "reports/monthly-summary"
        app.screen.action_save()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        _shot(app, output, "08-overwrite-confirmation")
        app.screen.action_cancel()
        await pilot.pause()

        current = app._get_query_document()
        assert current.relative_path is not None
        current_path = store.load(connection.name, current.relative_path).path
        current_path.write_text("SELECT changed_by_git;", encoding="utf-8")
        app.action_save_query()
        await pilot.pause()
        assert isinstance(app.screen, ExternalQueryChangeScreen)
        _shot(app, output, "09-external-change-conflict")
        app.screen.action_cancel()
        await pilot.pause()

        app._show_leader_menu()
        await pilot.pause()
        _shot(app, output, "10-leader-menu-actions")
        app.screen.dismiss(None)
        await pilot.pause()

        app.current_config = empty_connection
        app._reset_query_document(clear_text=True)
        app.action_query_library()
        await pilot.pause()
        assert isinstance(app.screen, QueryLibraryScreen)
        _shot(app, output, "11-empty-query-library")
