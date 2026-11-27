"""Pilot-driven test for cursor position after accepting a filter match.

Runs the real Textual app + Tree widget via `app.run_test()` and presses
real keys. Asserts that pressing Enter on a filtered match leaves the
cursor on that match in the rebuilt tree (the failure mode the user
sees is that it lands somewhere else — e.g. the top node).
"""

from __future__ import annotations

import pytest

from sqlit.domains.explorer.domain.tree_nodes import FolderNode, TableNode
from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import (
    MockConnectionStore,
    MockSettingsStore,
    build_test_services,
    create_test_connection,
)


def _connection_name_of(node) -> str | None:
    data = getattr(node, "data", None)
    if data is None:
        return None
    config = getattr(data, "config", None)
    if config is None:
        return None
    return getattr(config, "name", None)


@pytest.mark.asyncio
async def test_filter_accept_lands_cursor_on_matched_connection():
    """Repro of the issue the user demonstrated: after `/` then typing a
    substring and pressing Enter, the explorer cursor should be on the
    matched connection — not on the top node."""
    connections = [
        create_test_connection("alpha", "sqlite"),
        create_test_connection("test-server", "sqlite"),
        create_test_connection("production", "sqlite"),
    ]
    services = build_test_services(
        connection_store=MockConnectionStore(connections),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    app = SSMSTUI(services=services)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        # Focus the explorer so key events reach the tree filter mixin.
        app.action_focus_explorer()
        await pilot.pause()
        assert app.object_tree.has_focus

        # Open the filter, type a substring of one connection, accept.
        await pilot.press("slash")
        await pilot.pause()
        for ch in "test":
            await pilot.press(ch)
            await pilot.pause()

        # Sanity: a single match was found.
        assert len(app._tree_filter_matches) == 1, (
            f"expected exactly one match for 'test'; "
            f"got {len(app._tree_filter_matches)}"
        )

        await pilot.press("enter")
        await pilot.pause()

        cursor = app.object_tree.cursor_node
        assert cursor is not None, "cursor unexpectedly None after accept"
        name = _connection_name_of(cursor)
        assert name == "test-server", (
            "Cursor landed on the wrong element after accepting the filter "
            f"match. Expected 'test-server', got node with connection "
            f"name={name!r} (cursor.label={getattr(cursor, 'label', None)!r})."
        )


@pytest.mark.asyncio
async def test_filter_accept_activates_arrow_highlighted_match():
    """Arrowing to a later match and pressing Enter selects that match, not the first one."""
    connections = [
        create_test_connection("warehouse-a", "sqlite"),
        create_test_connection("warehouse-b", "sqlite"),
        create_test_connection("warehouse-c", "sqlite"),
        create_test_connection("other", "sqlite"),
    ]
    services = build_test_services(
        connection_store=MockConnectionStore(connections),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    app = SSMSTUI(services=services)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_focus_explorer()
        await pilot.pause()

        await pilot.press("slash")
        await pilot.pause()
        for ch in "warehouse":
            await pilot.press(ch)
            await pilot.pause()
        assert len(app._tree_filter_matches) == 3

        await pilot.press("down", "down")
        await pilot.pause()
        assert _connection_name_of(app.object_tree.cursor_node) == "warehouse-c"

        await pilot.press("enter")
        await pilot.pause()

        assert _connection_name_of(app.object_tree.cursor_node) == "warehouse-c"


@pytest.mark.asyncio
async def test_filter_accept_centers_selected_node():
    connections = [create_test_connection(f"conn-{i:02d}", "sqlite") for i in range(80)]
    services = build_test_services(
        connection_store=MockConnectionStore(connections),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    app = SSMSTUI(services=services)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_focus_explorer()
        await pilot.pause()

        await pilot.press("slash")
        await pilot.pause()
        for ch in "conn-60":
            await pilot.press(ch)
            await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        tree = app.object_tree
        cursor = tree.cursor_node
        assert _connection_name_of(cursor) == "conn-60"
        height = tree.scrollable_content_region.height
        assert tree.max_scroll_y > 0
        assert abs((cursor.line - tree.scroll_offset.y) - height // 2) <= 1


def _add_tables_under_first_connection(app: SSMSTUI, names: list[str]) -> None:
    """Hang a Tables folder with the given tables under the first connection,
    as if they had been lazy-loaded, so the matches sit below line 0."""
    connection = app.object_tree.root.children[0]
    tables = connection.add("Tables", data=FolderNode(folder_type="tables"), expand=True)
    for name in names:
        tables.add_leaf(name, data=TableNode(database=None, schema="main", name=name))
    connection.expand()


def _nested_table_services():
    return build_test_services(
        connection_store=MockConnectionStore([create_test_connection("warehouse", "sqlite")]),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )


@pytest.mark.asyncio
async def test_filter_moves_cursor_to_first_nested_match():
    """Typing a filter puts the cursor on the first match even when it is
    nested, so Enter without arrowing selects that match."""
    app = SSMSTUI(services=_nested_table_services())

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_focus_explorer()
        _add_tables_under_first_connection(app, ["customers", "orders_2023", "orders_2024"])
        await pilot.pause()

        await pilot.press("slash", *"orders")
        await pilot.pause()
        assert app.object_tree.cursor_node.label.plain == "orders_2023"

        await pilot.press("enter")
        await pilot.pause()
        assert app.object_tree.cursor_node.label.plain == "orders_2023"


@pytest.mark.asyncio
async def test_filter_accept_activates_arrow_highlighted_nested_match():
    app = SSMSTUI(services=_nested_table_services())

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_focus_explorer()
        _add_tables_under_first_connection(app, ["customers", "orders_2023", "orders_2024", "orders_2025"])
        await pilot.pause()

        await pilot.press("slash", *"orders")
        await pilot.pause()
        await pilot.press("down", "down")
        await pilot.pause()
        assert app.object_tree.cursor_node.label.plain == "orders_2025"

        await pilot.press("enter")
        await pilot.pause()
        assert app.object_tree.cursor_node.label.plain == "orders_2025"
