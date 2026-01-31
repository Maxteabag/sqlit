"""Integration test for explorer refresh cursor behavior."""

from __future__ import annotations

from typing import Any

import pytest

from sqlit.domains.explorer.ui.tree import builder as tree_builder
from sqlit.domains.shell.app.main import SSMSTUI
from tests.helpers import ConnectionConfig
from tests.ui.mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app(connections: list[ConnectionConfig]) -> SSMSTUI:
    services = build_test_services(
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
        connection_store=MockConnectionStore(connections),
    )
    return SSMSTUI(services=services)


def _find_connection_node(app: SSMSTUI, name: str) -> Any | None:
    stack = [app.object_tree.root]
    while stack:
        node = stack.pop()
        for child in node.children:
            data = getattr(child, "data", None)
            config = getattr(data, "config", None)
            if config and config.name == name:
                return child
            stack.append(child)
    return None


def _expand_ancestors(app: SSMSTUI, node: Any) -> None:
    ancestors = []
    current = getattr(node, "parent", None)
    while current and current != app.object_tree.root:
        ancestors.append(current)
        current = getattr(current, "parent", None)
    for ancestor in reversed(ancestors):
        ancestor.expand()




@pytest.mark.integration
@pytest.mark.asyncio
async def test_explorer_refresh_keeps_cursor_on_connection() -> None:
    connections = [
        ConnectionConfig(name="Alpha", db_type="sqlite", options={"file_path": "/tmp/alpha.db"}),
        ConnectionConfig(name="Bravo", db_type="sqlite", options={"file_path": "/tmp/bravo.db"}),
        ConnectionConfig(name="Charlie", db_type="sqlite", options={"file_path": "/tmp/charlie.db"}),
    ]
    app = _make_app(connections)

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()

        app.connections = connections
        tree_builder.refresh_tree(app)
        await pilot.pause(0.2)

        target = _find_connection_node(app, "Bravo")
        assert target is not None
        _expand_ancestors(app, target)

        app.action_focus_explorer()
        await pilot.pause()
        app.object_tree.move_cursor(target)
        await pilot.pause()
        assert app.object_tree.cursor_node == target

        # Simulate refresh with a reordered connection list (e.g. discovery/sort changes).
        # Keep the selected connection in the middle so a jump to first/last fails.
        # Update the store so refresh picks up the new order.
        app.services.connection_store.connections = [connections[2], connections[1], connections[0]]

        before_token = getattr(app, "_tree_refresh_token", None)
        await pilot.press("f")
        await pilot.pause(0.5)
        after_token = getattr(app, "_tree_refresh_token", None)
        assert before_token is not after_token

        cursor = app.object_tree.cursor_node
        assert cursor is not None
        data = getattr(cursor, "data", None)
        config = getattr(data, "config", None)
        assert config is not None

        ordered_names: list[str] = []
        for child in app.object_tree.root.children:
            child_data = getattr(child, "data", None)
            child_config = getattr(child_data, "config", None)
            if child_config:
                ordered_names.append(child_config.name)

        assert ordered_names == ["Charlie", "Bravo", "Alpha"]
        assert config.name == "Bravo"
        assert config.name not in {ordered_names[0], ordered_names[-1]}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_explorer_refresh_keeps_cursor_when_connection_moves_folder() -> None:
    connections = [
        ConnectionConfig(
            name="Alpha",
            db_type="sqlite",
            options={"file_path": "/tmp/alpha.db"},
            folder_path="A",
        ),
        ConnectionConfig(
            name="Bravo",
            db_type="sqlite",
            options={"file_path": "/tmp/bravo.db"},
            folder_path="A",
        ),
        ConnectionConfig(
            name="Charlie",
            db_type="sqlite",
            options={"file_path": "/tmp/charlie.db"},
            folder_path="A",
        ),
    ]
    app = _make_app(connections)

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()

        app.connections = connections
        tree_builder.refresh_tree(app)
        await pilot.pause(0.2)

        target = _find_connection_node(app, "Bravo")
        assert target is not None
        _expand_ancestors(app, target)

        app.action_focus_explorer()
        await pilot.pause()
        app.object_tree.move_cursor(target)
        await pilot.pause()
        assert app.object_tree.cursor_node == target

        # Move the selected connection to a different folder before refresh.
        # Update the store so refresh picks up the new folder assignments.
        app.services.connection_store.connections = [
            ConnectionConfig(
                name="Alpha",
                db_type="sqlite",
                options={"file_path": "/tmp/alpha.db"},
                folder_path="A",
            ),
            ConnectionConfig(
                name="Bravo",
                db_type="sqlite",
                options={"file_path": "/tmp/bravo.db"},
                folder_path="B",
            ),
            ConnectionConfig(
                name="Charlie",
                db_type="sqlite",
                options={"file_path": "/tmp/charlie.db"},
                folder_path="A",
            ),
        ]

        await pilot.press("f")
        await pilot.pause(0.5)

        cursor = app.object_tree.cursor_node
        assert cursor is not None
        data = getattr(cursor, "data", None)
        config = getattr(data, "config", None)
        assert config is not None
        assert config.name == "Bravo"

        parent = getattr(cursor, "parent", None)
        parent_data = getattr(parent, "data", None)
        assert getattr(parent_data, "name", None) == "B"
