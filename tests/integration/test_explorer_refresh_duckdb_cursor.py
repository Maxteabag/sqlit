"""Integration tests for explorer refresh cursor behavior with DuckDB."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlit.domains.explorer.domain.tree_nodes import ColumnNode, TableNode
from sqlit.domains.shell.app.main import SSMSTUI
from tests.helpers import ConnectionConfig
from tests.integration.browsing_base import (
    find_connection_node,
    find_folder_node,
    find_table_node,
    has_loading_children,
    wait_for_condition,
)


def _build_duckdb_db(path: Path) -> None:
    try:
        import duckdb  # type: ignore
    except ImportError:
        pytest.skip("duckdb is not installed")

    conn = duckdb.connect(str(path))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR)")
    conn.close()


def _find_column_node(parent: Any, column_name: str) -> Any | None:
    for child in parent.children:
        data = getattr(child, "data", None)
        if isinstance(data, ColumnNode) and data.name == column_name:
            return child
    return None


async def _wait_for_folder_loaded(pilot: Any, node: Any, description: str) -> None:
    await wait_for_condition(
        pilot,
        lambda: not has_loading_children(node) and len(node.children) > 0,
        timeout_seconds=10.0,
        description=description,
    )


async def _wait_for_columns_loaded(pilot: Any, node: Any) -> None:
    await wait_for_condition(
        pilot,
        lambda: not has_loading_children(node) and _find_column_node(node, "id") is not None,
        timeout_seconds=10.0,
        description="columns to load",
    )


async def _refresh_tree(pilot: Any, app: SSMSTUI) -> None:
    before_token = getattr(app, "_tree_refresh_token", None)
    await pilot.press("f")
    await wait_for_condition(
        pilot,
        lambda: getattr(app, "_tree_refresh_token", None) is not before_token,
        timeout_seconds=5.0,
        description="tree refresh to start",
    )


async def _wait_for_folder_loaded_or_refresh(
    pilot: Any,
    app: SSMSTUI,
    node: Any,
    description: str,
    *,
    allow_refresh: bool,
) -> None:
    try:
        await _wait_for_folder_loaded(pilot, node, description)
        return
    except AssertionError:
        if not allow_refresh:
            raise
    await _refresh_tree(pilot, app)
    await pilot.pause(0.3)
    await _wait_for_folder_loaded(pilot, node, description)


def _set_auto_expanded_paths(app: SSMSTUI, config_name: str) -> None:
    app._expanded_paths = {
        f"conn:{config_name}",
        f"conn:{config_name}/folder:tables",
        f"conn:{config_name}/folder:tables/table:main.users",
        f"conn:{config_name}/folder:tables/table:main.users/column:main.users.id",
    }


def _find_table_in_tree(app: SSMSTUI, config_name: str, table_name: str) -> Any | None:
    connected_node = find_connection_node(app.object_tree.root, config_name)
    if connected_node is None:
        return None
    tables_folder = find_folder_node(connected_node, "tables")
    if tables_folder is None:
        return None
    return find_table_node(tables_folder, table_name)


async def _connect_and_expand(
    pilot: Any,
    app: SSMSTUI,
    config: ConnectionConfig,
    *,
    auto_expand: bool,
    allow_refresh_on_load: bool,
) -> tuple[Any, Any, Any]:
    app.connections = [config]
    app.refresh_tree()
    await pilot.pause(0.1)

    await wait_for_condition(
        pilot,
        lambda: len(app.object_tree.root.children) > 0,
        timeout_seconds=5.0,
        description="tree to be populated with connections",
    )

    app.connect_to_server(config)
    await pilot.pause(0.5)

    await wait_for_condition(
        pilot,
        lambda: app.current_connection is not None,
        timeout_seconds=15.0,
        description="connection to be established",
    )

    connected_node = find_connection_node(app.object_tree.root, config.name)
    assert connected_node is not None

    tables_folder = find_folder_node(connected_node, "tables")
    assert tables_folder is not None

    if auto_expand:
        _set_auto_expanded_paths(app, config.name)
        app.refresh_tree()
        await pilot.pause(0.3)
        connected_node = find_connection_node(app.object_tree.root, config.name)
        assert connected_node is not None
        tables_folder = find_folder_node(connected_node, "tables")
        assert tables_folder is not None
    else:
        tables_folder.expand()
    await pilot.pause(0.2)
    await _wait_for_folder_loaded_or_refresh(
        pilot,
        app,
        tables_folder,
        "tables to load",
        allow_refresh=allow_refresh_on_load,
    )

    table_node = find_table_node(tables_folder, "users")
    assert table_node is not None

    if auto_expand:
        assert table_node.is_expanded
    else:
        table_node.expand()
    await pilot.pause(0.2)
    await _wait_for_columns_loaded(pilot, table_node)

    column_node = _find_column_node(table_node, "id")
    assert column_node is not None

    return tables_folder, table_node, column_node


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("auto_expand", [False, True])
async def test_duckdb_tables_load_without_manual_refresh(tmp_path: Path, auto_expand: bool) -> None:
    db_path = tmp_path / "duckdb_initial_tables.db"
    _build_duckdb_db(db_path)

    config = ConnectionConfig(
        name="duckdb-initial-tables",
        db_type="duckdb",
        file_path=str(db_path),
    )

    app = SSMSTUI()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)

        app.connections = [config]
        app.refresh_tree()
        await pilot.pause(0.1)

        await wait_for_condition(
            pilot,
            lambda: len(app.object_tree.root.children) > 0,
            timeout_seconds=5.0,
            description="tree to be populated with connections",
        )

        app.connect_to_server(config)
        await pilot.pause(0.5)

        await wait_for_condition(
            pilot,
            lambda: app.current_connection is not None,
            timeout_seconds=15.0,
            description="connection to be established",
        )

        connected_node = find_connection_node(app.object_tree.root, config.name)
        assert connected_node is not None

        tables_folder = find_folder_node(connected_node, "tables")
        assert tables_folder is not None

        if auto_expand:
            _set_auto_expanded_paths(app, config.name)
            app.refresh_tree()
            await pilot.pause(0.3)
            connected_node = find_connection_node(app.object_tree.root, config.name)
            assert connected_node is not None
            tables_folder = find_folder_node(connected_node, "tables")
            assert tables_folder is not None
            assert tables_folder.is_expanded
        else:
            tables_folder.expand()
        await pilot.pause(0.2)

        await _wait_for_folder_loaded(
            pilot,
            tables_folder,
            "tables to load without manual refresh",
        )

@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("auto_expand", [False, True])
async def test_duckdb_refresh_keeps_cursor_on_table(tmp_path: Path, auto_expand: bool) -> None:
    db_path = tmp_path / "duckdb_refresh_table.db"
    _build_duckdb_db(db_path)

    config = ConnectionConfig(
        name="duckdb-refresh-table",
        db_type="duckdb",
        file_path=str(db_path),
    )

    app = SSMSTUI()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)

        _, table_node, _ = await _connect_and_expand(
            pilot,
            app,
            config,
            auto_expand=auto_expand,
            allow_refresh_on_load=True,
        )

        app.action_focus_explorer()
        await pilot.pause(0.05)
        app.object_tree.move_cursor(table_node)
        await pilot.pause(0.05)
        assert app.object_tree.cursor_node == table_node

        await _refresh_tree(pilot, app)
        await pilot.pause(0.5)

        refreshed_connection = find_connection_node(app.object_tree.root, config.name)
        assert refreshed_connection is not None
        refreshed_tables = find_folder_node(refreshed_connection, "tables")
        assert refreshed_tables is not None
        assert refreshed_tables.is_expanded

        await _wait_for_folder_loaded(pilot, refreshed_tables, "tables to reload")
        refreshed_table = find_table_node(refreshed_tables, "users")
        assert refreshed_table is not None

        cursor = app.object_tree.cursor_node
        assert cursor is not None
        assert isinstance(cursor.data, TableNode)
        assert cursor.data.name == "users"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("auto_expand", [False, True])
async def test_duckdb_refresh_keeps_cursor_on_column(tmp_path: Path, auto_expand: bool) -> None:
    db_path = tmp_path / "duckdb_refresh_column.db"
    _build_duckdb_db(db_path)

    config = ConnectionConfig(
        name="duckdb-refresh-column",
        db_type="duckdb",
        file_path=str(db_path),
    )

    app = SSMSTUI()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)

        _, table_node, column_node = await _connect_and_expand(
            pilot,
            app,
            config,
            auto_expand=auto_expand,
            allow_refresh_on_load=True,
        )

        app.action_focus_explorer()
        await pilot.pause(0.05)
        app.object_tree.move_cursor(column_node)
        await pilot.pause(0.05)
        assert app.object_tree.cursor_node == column_node

        await _refresh_tree(pilot, app)
        await pilot.pause(0.7)

        refreshed_connection = find_connection_node(app.object_tree.root, config.name)
        assert refreshed_connection is not None
        refreshed_tables = find_folder_node(refreshed_connection, "tables")
        assert refreshed_tables is not None
        assert refreshed_tables.is_expanded

        await _wait_for_folder_loaded(pilot, refreshed_tables, "tables to reload")
        refreshed_table = find_table_node(refreshed_tables, "users")
        assert refreshed_table is not None
        if not refreshed_table.is_expanded:
            refreshed_table.expand()
            await pilot.pause(0.2)

        await _wait_for_columns_loaded(pilot, refreshed_table)
        refreshed_column = _find_column_node(refreshed_table, "id")
        assert refreshed_column is not None

        cursor = app.object_tree.cursor_node
        assert cursor is not None
        assert isinstance(cursor.data, ColumnNode)
        assert cursor.data.name == "id"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_duckdb_auto_refresh_after_create_table(tmp_path: Path) -> None:
    db_path = tmp_path / "duckdb_auto_refresh.db"
    _build_duckdb_db(db_path)

    config = ConnectionConfig(
        name="duckdb-auto-refresh",
        db_type="duckdb",
        file_path=str(db_path),
    )

    app = SSMSTUI()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.1)

        tables_folder, _, _ = await _connect_and_expand(
            pilot,
            app,
            config,
            auto_expand=False,
            allow_refresh_on_load=True,
        )

        assert find_table_node(tables_folder, "users") is not None
        assert _find_table_in_tree(app, config.name, "users3") is None

        before_token = getattr(app, "_tree_refresh_token", None)
        app.query_input.text = "CREATE TABLE users3 (id INTEGER)"
        app.action_execute_query()

        await wait_for_condition(
            pilot,
            lambda: not getattr(app, "query_executing", False),
            timeout_seconds=15.0,
            description="query execution to finish",
        )

        await wait_for_condition(
            pilot,
            lambda: getattr(app, "_tree_refresh_token", None) is not before_token,
            timeout_seconds=10.0,
            description="tree refresh after DDL",
        )

        await wait_for_condition(
            pilot,
            lambda: _find_table_in_tree(app, config.name, "users3") is not None,
            timeout_seconds=10.0,
            description="new table to appear after auto refresh",
        )
