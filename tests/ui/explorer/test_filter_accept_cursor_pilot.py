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
