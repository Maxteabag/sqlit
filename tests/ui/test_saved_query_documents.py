"""End-to-end UI coverage for saved query documents."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from textual import events
from textual.widgets import Input

from sqlit.domains.connections.app.credentials import CredentialsPersistError
from sqlit.domains.explorer.domain.tree_nodes import TableNode
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

from .mocks import (
    MockConnectionStore,
    MockHistoryStore,
    MockSettingsStore,
    build_test_services,
    create_test_connection,
)


def _make_app(tmp_path: Path) -> tuple[SSMSTUI, SavedQueryStore]:
    connection = create_test_connection("production-reporting", "sqlite")
    store = SavedQueryStore(tmp_path / "saved-queries")
    services = build_test_services(
        connection_store=MockConnectionStore([connection]),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
        history_store=MockHistoryStore(),
        saved_query_store=store,
    )
    app = SSMSTUI(services=services)
    app.connections = [connection]
    app.current_config = connection
    return app, store


@pytest.mark.asyncio
async def test_first_save_creates_lazy_library_and_clears_dirty_marker(
    tmp_path: Path,
) -> None:
    app, store = _make_app(tmp_path)
    assert not store.connection_dir("production-reporting").exists()

    async with app.run_test(size=(120, 40)) as pilot:
        app.query_input.text = "SELECT * FROM sales"
        await pilot.pause()
        assert app._document_is_dirty()
        assert "Untitled" not in str(app.query_area.border_title)
        assert "●" not in str(app.query_area.border_title)

        app.action_save_query()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SavedQueryNameScreen)
        screen.query_one("#saved-query-name-input", Input).value = "reports/daily-sales"
        screen.action_save()
        await pilot.pause()

        assert store.connection_dir("production-reporting").is_dir()
        assert store.load("production-reporting", "reports/daily-sales.sql").query == ("SELECT * FROM sales")
        assert not app._document_is_dirty()
        assert "daily-sales.sql" in str(app.query_area.border_title)
        assert "●" not in str(app.query_area.border_title)


@pytest.mark.asyncio
async def test_edit_undo_and_save_existing_document_update_dirty_state(
    tmp_path: Path,
) -> None:
    app, store = _make_app(tmp_path)
    entry = store.save("production-reporting", "health", "SELECT 1")

    async with app.run_test(size=(120, 40)) as pilot:
        app._load_saved_query_entry(entry)
        app.query_input.text = "SELECT 2"
        await pilot.pause()
        assert app._document_is_dirty()

        app.query_input.text = "SELECT 1"
        await pilot.pause()
        assert not app._document_is_dirty()

        app.query_input.text = "SELECT 3"
        app.action_save_query()
        await pilot.pause()

        assert store.load("production-reporting", "health.sql").query == "SELECT 3"
        assert not app._document_is_dirty()


@pytest.mark.asyncio
async def test_library_search_preview_and_open_never_executes(
    tmp_path: Path,
) -> None:
    app, store = _make_app(tmp_path)
    store.save("production-reporting", "reports/daily-sales", "SELECT * FROM sales")
    store.save("production-reporting", "diagnostics/health", "SELECT 1")

    async with app.run_test(size=(120, 40)) as pilot:
        app.action_query_library()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, QueryLibraryScreen)
        screen.action_open_filter()
        await pilot.press("d", "a", "i", "l", "y")
        assert "SELECT * FROM sales" in str(screen.query_one("#query-library-preview").render())

        screen.action_select()
        await pilot.pause()

        assert app.query_input.text == "SELECT * FROM sales"
        assert app._get_query_document().relative_path == "reports/daily-sales.sql"
        assert app._last_result_columns == []


@pytest.mark.asyncio
async def test_library_reloads_file_changed_while_picker_is_open(
    tmp_path: Path,
) -> None:
    app, store = _make_app(tmp_path)
    entry = store.save("production-reporting", "shared", "SELECT old")

    async with app.run_test(size=(120, 40)) as pilot:
        app.action_query_library()
        await pilot.pause()
        assert isinstance(app.screen, QueryLibraryScreen)
        entry.path.write_text("SELECT newest", encoding="utf-8")

        app.screen.action_select()
        await pilot.pause()

        assert app.query_input.text == "SELECT newest"
        assert app._get_query_document().saved_text == "SELECT newest"


@pytest.mark.asyncio
async def test_library_search_accepts_q_character(tmp_path: Path) -> None:
    app, store = _make_app(tmp_path)
    store.save("production-reporting", "quarterly-report", "SELECT 1")

    async with app.run_test(size=(120, 40)) as pilot:
        app.action_query_library()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, QueryLibraryScreen)
        screen.action_open_filter()

        await pilot.press("q")

        assert app.screen is screen
        assert screen.query_one("#query-library-filter", FilterInput).filter_text == "q"


@pytest.mark.asyncio
async def test_library_search_accepts_folder_separator(tmp_path: Path) -> None:
    app, store = _make_app(tmp_path)
    store.save("production-reporting", "reports/quarterly", "SELECT 1")

    async with app.run_test(size=(120, 40)) as pilot:
        app.action_query_library()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, QueryLibraryScreen)
        screen.action_open_filter()

        await pilot.press("r", "e", "p", "o", "r", "t", "s", "/")

        assert screen.query_one(FilterInput).filter_text == "reports/"
        assert screen._selected_entry() is not None
        assert screen._selected_entry().relative_path == "reports/quarterly.sql"

        screen.on_paste(events.Paste("quarterly"))

        assert screen.query_one(FilterInput).filter_text == "reports/quarterly"


@pytest.mark.asyncio
async def test_opening_another_query_protects_dirty_document(tmp_path: Path) -> None:
    app, store = _make_app(tmp_path)
    first = store.save("production-reporting", "first", "SELECT 1")
    second = store.save("production-reporting", "second", "SELECT 2")

    async with app.run_test(size=(120, 40)) as pilot:
        app._load_saved_query_entry(first)
        app.query_input.text = "SELECT changed"
        app._request_query_document_transition(lambda: app._load_saved_query_entry(second))
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, UnsavedQueryChangesScreen)
        assert app.query_input.text == "SELECT changed"
        screen.query_one(".document-choice-list").highlighted = 1
        screen.action_select()
        await pilot.pause()

        assert app.query_input.text == "SELECT 2"
        assert app._get_query_document().relative_path == "second.sql"


@pytest.mark.asyncio
async def test_save_as_requires_confirmation_before_overwrite(tmp_path: Path) -> None:
    app, store = _make_app(tmp_path)
    store.save("production-reporting", "existing", "SELECT old")

    async with app.run_test(size=(120, 40)) as pilot:
        app.query_input.text = "SELECT new"
        app.action_save_query_as()
        await pilot.pause()
        name_screen = app.screen
        assert isinstance(name_screen, SavedQueryNameScreen)
        name_screen.query_one(Input).value = "existing"
        name_screen.action_save()
        await pilot.pause()

        confirm = app.screen
        assert isinstance(confirm, ConfirmScreen)
        assert store.load("production-reporting", "existing.sql").query == "SELECT old"
        confirm.action_yes()
        await pilot.pause()

        assert store.load("production-reporting", "existing.sql").query == "SELECT new"


@pytest.mark.asyncio
async def test_save_as_reconfirms_when_destination_changes_during_prompt(
    tmp_path: Path,
) -> None:
    app, store = _make_app(tmp_path)
    existing = store.save("production-reporting", "existing", "SELECT old")

    async with app.run_test(size=(120, 40)) as pilot:
        app.query_input.text = "SELECT from_sqlit"
        app.action_save_query_as()
        await pilot.pause()
        name_screen = app.screen
        assert isinstance(name_screen, SavedQueryNameScreen)
        name_screen.query_one(Input).value = "existing"
        name_screen.action_save()
        await pilot.pause()

        first_confirm = app.screen
        assert isinstance(first_confirm, ConfirmScreen)
        existing.path.write_text("SELECT newest", encoding="utf-8")
        first_confirm.action_yes()
        await pilot.pause()

        assert isinstance(app.screen, ConfirmScreen)
        assert existing.path.read_text(encoding="utf-8") == "SELECT newest"
        app.screen.action_cancel()


@pytest.mark.asyncio
async def test_external_change_is_detected_before_save(tmp_path: Path) -> None:
    app, store = _make_app(tmp_path)
    entry = store.save("production-reporting", "shared", "SELECT original")

    async with app.run_test(size=(120, 40)) as pilot:
        app._load_saved_query_entry(entry)
        app.query_input.text = "SELECT from_sqlit"
        entry.path.write_text("SELECT from_git", encoding="utf-8")

        app.action_save_query()
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, ExternalQueryChangeScreen)
        assert entry.path.read_text(encoding="utf-8") == "SELECT from_git"
        screen.query_one(".document-choice-list").highlighted = 0
        screen.action_select()
        await pilot.pause()

        assert app.query_input.text == "SELECT from_git"
        assert not app._document_is_dirty()


@pytest.mark.asyncio
async def test_new_query_replaces_scratchpad_without_prompt(tmp_path: Path) -> None:
    app, _store = _make_app(tmp_path)

    async with app.run_test(size=(120, 40)) as pilot:
        app.query_input.text = "SELECT unfinished"
        app.action_new_query()
        await pilot.pause()

        assert app.query_input.text == ""
        assert not isinstance(app.screen, UnsavedQueryChangesScreen)


@pytest.mark.asyncio
async def test_discard_marks_transition_clean_before_nested_connection_guard(
    tmp_path: Path,
) -> None:
    app, store = _make_app(tmp_path)
    continued: list[bool] = []

    async with app.run_test(size=(120, 40)) as pilot:
        entry = store.save("production-reporting", "saved", "SELECT original")
        app._load_saved_query_entry(entry)
        app.query_input.text = "SELECT unfinished"
        app._request_query_document_transition(lambda: app._request_query_document_transition(lambda: continued.append(True)))
        await pilot.pause()

        prompt = app.screen
        assert isinstance(prompt, UnsavedQueryChangesScreen)
        prompt.query_one(".document-choice-list").highlighted = 1
        prompt.action_select()
        await pilot.pause()

        assert continued == [True]
        assert not isinstance(app.screen, UnsavedQueryChangesScreen)


@pytest.mark.asyncio
async def test_save_and_continue_saves_named_query_before_new_scratchpad(
    tmp_path: Path,
) -> None:
    app, store = _make_app(tmp_path)

    async with app.run_test(size=(120, 40)) as pilot:
        entry = store.save("production-reporting", "kept-before-new", "SELECT old")
        app._load_saved_query_entry(entry)
        app.query_input.text = "SELECT worth_keeping"
        app.action_new_query()
        await pilot.pause()

        prompt = app.screen
        assert isinstance(prompt, UnsavedQueryChangesScreen)
        prompt.query_one(".document-choice-list").highlighted = 0
        prompt.action_select()
        await pilot.pause()

        assert store.load("production-reporting", "kept-before-new.sql").query == ("SELECT worth_keeping")
        assert app.query_input.text == ""
        assert app._get_query_document().name == "Untitled"
        assert not app._document_is_dirty()


@pytest.mark.asyncio
async def test_external_change_can_be_explicitly_overwritten(tmp_path: Path) -> None:
    app, store = _make_app(tmp_path)
    entry = store.save("production-reporting", "shared", "SELECT original")

    async with app.run_test(size=(120, 40)) as pilot:
        app._load_saved_query_entry(entry)
        app.query_input.text = "SELECT from_sqlit"
        entry.path.write_text("SELECT from_git", encoding="utf-8")
        app.action_save_query()
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, ExternalQueryChangeScreen)
        screen.query_one(".document-choice-list").highlighted = 1
        screen.action_select()
        await pilot.pause()

        assert entry.path.read_text(encoding="utf-8") == "SELECT from_sqlit"
        assert not app._document_is_dirty()


@pytest.mark.asyncio
async def test_reload_conflict_continues_pending_transition(tmp_path: Path) -> None:
    app, store = _make_app(tmp_path)
    entry = store.save("production-reporting", "shared", "SELECT original")
    continued: list[bool] = []

    async with app.run_test(size=(120, 40)) as pilot:
        app._load_saved_query_entry(entry)
        app.query_input.text = "SELECT from_sqlit"
        entry.path.write_text("SELECT from_git", encoding="utf-8")
        app._save_existing_query_document(
            "production-reporting",
            app._get_query_document(),
            after_save=lambda: continued.append(True),
        )
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, ExternalQueryChangeScreen)
        screen.query_one(".document-choice-list").highlighted = 0
        screen.action_select()
        await pilot.pause()

        assert app.query_input.text == "SELECT from_git"
        assert continued == [True]


@pytest.mark.asyncio
async def test_telescope_history_detaches_previous_saved_file(tmp_path: Path) -> None:
    app, store = _make_app(tmp_path)
    entry = store.save("production-reporting", "saved", "SELECT saved")

    async with app.run_test(size=(120, 40)) as pilot:
        app.current_connection = object()
        app._load_saved_query_entry(entry)

        app._run_telescope_query("production-reporting", "SELECT history")
        await pilot.pause()

        assert app.query_input.text == "SELECT history"
        assert app._get_query_document().relative_path is None
        assert app._document_is_dirty()


@pytest.mark.asyncio
async def test_table_selection_protects_and_detaches_saved_document(
    tmp_path: Path,
) -> None:
    app, store = _make_app(tmp_path)
    entry = store.save("production-reporting", "saved", "SELECT saved")

    async with app.run_test(size=(120, 40)) as pilot:
        app._load_saved_query_entry(entry)
        app.query_input.text = "SELECT edited"
        provider = MagicMock()
        provider.dialect.build_select_query.return_value = "SELECT * FROM customers LIMIT 100"
        app.current_provider = provider
        app._session = SimpleNamespace()
        app._prime_last_query_table_columns = MagicMock()  # type: ignore[method-assign]
        app.action_execute_query = MagicMock()  # type: ignore[method-assign]
        await pilot.pause()
        connection_node = app._find_connection_node_by_name("production-reporting")
        assert connection_node is not None
        node = connection_node.add_leaf("customers")
        node.data = TableNode(database=None, schema="", name="customers")
        connection_node.expand()
        app.object_tree.refresh(layout=True)
        await pilot.pause()
        app.object_tree.select_node(node)
        await pilot.pause()
        assert app.object_tree.cursor_node is node

        app.action_select_table()
        await pilot.pause()
        prompt = app.screen
        assert isinstance(prompt, UnsavedQueryChangesScreen)
        prompt.query_one(".document-choice-list").highlighted = 1
        prompt.action_select()
        await pilot.pause()

        assert app.query_input.text == "SELECT * FROM customers LIMIT 100"
        assert app._get_query_document().relative_path is None
        app.action_execute_query.assert_called_once()


@pytest.mark.asyncio
async def test_empty_library_explains_how_to_create_first_query(tmp_path: Path) -> None:
    app, _store = _make_app(tmp_path)

    async with app.run_test(size=(120, 40)) as pilot:
        app.action_query_library()
        await pilot.pause()

        assert isinstance(app.screen, QueryLibraryScreen)
        assert "No saved queries yet" in str(app.screen.query_one("#query-library-empty").render())


@pytest.mark.asyncio
async def test_connection_rename_is_aborted_when_library_cannot_move(
    tmp_path: Path,
) -> None:
    app, store = _make_app(tmp_path)
    old_config = app.connections[0]
    new_config = replace(old_config, name="renamed-reporting")
    store.save(old_config.name, "old-query", "SELECT old")
    store.save(new_config.name, "collision", "SELECT collision")

    async with app.run_test(size=(120, 40)) as pilot:
        app.notify = MagicMock()  # type: ignore[method-assign]
        app.handle_connection_result(("save", new_config, old_config.name))
        await pilot.pause()

        assert [config.name for config in app.connections] == [old_config.name]
        assert app.services.connection_store.get_by_name(old_config.name) is not None
        assert app.services.connection_store.get_by_name(new_config.name) is None
        assert store.load(old_config.name, "old-query.sql").query == "SELECT old"


@pytest.mark.asyncio
async def test_active_document_follows_successful_connection_rename(
    tmp_path: Path,
) -> None:
    app, store = _make_app(tmp_path)
    old_config = app.connections[0]
    entry = store.save(old_config.name, "report", "SELECT 1")
    new_config = replace(old_config, name="renamed-reporting")

    async with app.run_test(size=(120, 40)) as pilot:
        app._load_saved_query_entry(entry)
        app.notify = MagicMock()  # type: ignore[method-assign]
        app.handle_connection_result(("save", new_config, old_config.name))
        await pilot.pause()

        assert app.current_config is not None
        assert app.current_config.name == new_config.name
        assert app._get_query_document().connection_name == new_config.name
        assert store.load(new_config.name, "report.sql").query == "SELECT 1"

        app.query_input.text = "SELECT 2"
        app.action_save_query()
        await pilot.pause()
        assert store.load(new_config.name, "report.sql").query == "SELECT 2"


@pytest.mark.asyncio
async def test_precommit_credential_failure_rolls_back_library_rename(
    tmp_path: Path,
) -> None:
    app, store = _make_app(tmp_path)
    old_config = app.connections[0]
    new_config = replace(old_config, name="renamed-reporting")
    store.save(old_config.name, "report", "SELECT 1")
    connection_store = app.services.connection_store

    def fail_before_index(*_args, **_kwargs) -> None:
        raise CredentialsPersistError([])

    connection_store.save_one = fail_before_index  # type: ignore[method-assign]

    async with app.run_test(size=(120, 40)) as pilot:
        app.notify = MagicMock()  # type: ignore[method-assign]
        app.handle_connection_result(("save", new_config, old_config.name))
        await pilot.pause()

        assert [config.name for config in app.connections] == [old_config.name]
        assert store.load(old_config.name, "report.sql").query == "SELECT 1"
        assert store.list_for_connection(new_config.name) == []


@pytest.mark.asyncio
async def test_deleting_active_connection_protects_dirty_document(
    tmp_path: Path,
) -> None:
    app, store = _make_app(tmp_path)
    config = app.connections[0]
    entry = store.save(config.name, "report", "SELECT 1")

    async with app.run_test(size=(120, 40)) as pilot:
        app.current_connection = object()
        app._load_saved_query_entry(entry)
        app.query_input.text = "SELECT edited"
        await pilot.pause()

        app.action_delete_connection()
        await pilot.pause()
        confirm = app.screen
        assert isinstance(confirm, ConfirmScreen)
        confirm.action_yes()
        await pilot.pause()

        prompt = app.screen
        assert isinstance(prompt, UnsavedQueryChangesScreen)
        prompt.action_cancel()
        await pilot.pause()

        assert app.services.connection_store.get_by_name(config.name) is not None
        assert app._document_is_dirty()
