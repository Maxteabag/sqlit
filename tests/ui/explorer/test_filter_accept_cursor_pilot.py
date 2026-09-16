"""Pilot-driven test for cursor position after accepting a filter match.

Runs the real Textual app + Tree widget via `app.run_test()` and presses
real keys. Asserts that pressing Enter on a filtered match leaves the
cursor on that match in the rebuilt tree (the failure mode the user
sees is that it lands somewhere else — e.g. the top node).
"""

from __future__ import annotations

import pytest

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
