"""The new layout is optional, cancellable, and harmless on SQLite."""

import sqlite3

import pytest

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.explorer.domain.tree_nodes import FolderNode, SchemaNode
from sqlit.domains.shell.app.main import SSMSTUI
from sqlit.domains.shell.ui.screens.explorer_layout import ExplorerLayoutScreen
from sqlit.shared.app.runtime import RuntimeConfig
from tests.ui.mocks import MockConnectionStore, MockSettingsStore, build_test_services


@pytest.mark.asyncio
async def test_layout_picker_cancel_and_invalid_value_do_not_change_settings():
    settings = MockSettingsStore({"theme": "vesper", "explorer_hierarchy": "type"})
    app = SSMSTUI(services=build_test_services(settings_store=settings, connection_store=MockConnectionStore()))
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        app._run_command("explorer")
        await pilot.pause()
        assert isinstance(app.screen, ExplorerLayoutScreen)
        await pilot.press("down", "escape")
        assert settings.get("explorer_hierarchy") == "type"
        app._run_command("explorer invalid")
        assert settings.get("explorer_hierarchy") == "type"
        app._run_command("explorer schema unexpected")
        assert settings.get("explorer_hierarchy") == "type"


@pytest.mark.asyncio
async def test_sqlite_stays_flat_and_layout_switch_preserves_query(tmp_path):
    path = tmp_path / "db.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE orders (id INTEGER)")
    config = ConnectionConfig.from_dict({"name": "SQLite demo", "db_type": "sqlite", "file_path": str(path)})
    settings = MockSettingsStore({"theme": "vesper", "explorer_hierarchy": "schema"})
    services = build_test_services(runtime=RuntimeConfig(process_worker=False), settings_store=settings, connection_store=MockConnectionStore([config]))
    app = SSMSTUI(services=services)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        app.connect_to_server(config)
        for _ in range(3):
            await pilot.pause(0.05)
            await app.workers.wait_for_complete()
        assert app.current_connection is not None
        connection = app.object_tree.root.children[0]
        assert any(isinstance(n.data, FolderNode) and n.data.folder_type == "tables" for n in connection.children)
        assert not any(isinstance(n.data, SchemaNode) for n in connection.children)
        app.query_input.text = "SELECT * FROM orders;"
        app._run_command("explorer")
        await pilot.pause()
        assert app.screen.supported is False
        await pilot.press("escape")
        app.action_tree_filter()
        app._run_command("explorer type")
        await pilot.pause()
        assert not app._tree_filter_visible
        assert app.query_input.text == "SELECT * FROM orders;"
        assert settings.get("explorer_hierarchy") == "type"
