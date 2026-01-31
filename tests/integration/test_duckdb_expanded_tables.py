"""Integration test for DuckDB manual refresh expansion loading."""

from __future__ import annotations

import pytest

from sqlit.domains.connections.providers.duckdb.adapter import DuckDBAdapter
from sqlit.domains.shell.app.main import SSMSTUI
from tests.helpers import ConnectionConfig
from tests.integration.browsing_base import find_connection_node, find_folder_node, has_table_children, wait_for_condition


@pytest.mark.integration
@pytest.mark.asyncio
async def test_duckdb_expanded_tables_load_on_manual_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        import duckdb  # type: ignore
    except ImportError:
        pytest.skip("duckdb is not installed")

    connection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE test_users(id INTEGER, name VARCHAR)")

    def connect_in_memory(self: DuckDBAdapter, config) -> object:
        _ = config
        return connection

    monkeypatch.setattr(DuckDBAdapter, "connect", connect_in_memory)

    config = ConnectionConfig(
        name="duckdb-memory",
        db_type="duckdb",
        file_path=":memory:",
    )

    app = SSMSTUI()

    try:
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

            app._expanded_paths = {f"conn:{config.name}/folder:tables"}

            app.connect_to_server(config)
            await pilot.pause(0.5)

            await wait_for_condition(
                pilot,
                lambda: app.current_connection is not None,
                timeout_seconds=10.0,
                description="duckdb connection to be established",
            )

            connected_node = find_connection_node(app.object_tree.root, config.name)
            assert connected_node is not None

            await wait_for_condition(
                pilot,
                lambda: len(connected_node.children) > 0,
                timeout_seconds=5.0,
                description="connected node to be populated",
            )

            tables_folder = find_folder_node(connected_node, "tables")
            assert tables_folder is not None

            assert not getattr(tables_folder, "is_expanded", False)

            await pilot.press("f")
            await pilot.pause(0.2)

            await wait_for_condition(
                pilot,
                lambda: has_table_children(tables_folder),
                timeout_seconds=10.0,
                description="tables to load after manual refresh",
            )
            app.action_disconnect()
            app.exit()
            await pilot.pause(0.1)
    finally:
        connection.close()
