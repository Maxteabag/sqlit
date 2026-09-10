"""Run real adapter/catalog/UI contracts, not fabricated tree snapshots.

Opt in with SQLIT_SCHEMA_INTEGRATION=1. Requested providers fail on unavailable
infrastructure rather than reporting a passing, skipped integration lane.
"""

from __future__ import annotations

import asyncio

import pytest

from sqlit.domains.connections.providers.schema_explorer import load_schema_folder_items
from sqlit.domains.explorer.domain.tree_nodes import FolderNode, SchemaNode, TableNode
from sqlit.domains.shell.app.main import SSMSTUI
from sqlit.shared.app.runtime import RuntimeConfig
from tests.ui.mocks import MockConnectionStore, MockSettingsStore, build_test_services


def test_catalog_lists_empty_schema(provider_case):
    case = provider_case
    if case.name == "sqlite":
        assert not case.provider.capabilities.supports_schema_grouping
        return
    schemas = load_schema_folder_items(case.adapter, case.connection, case.database, "schemas", None)
    assert {case.billing, case.analytics, case.empty}.issubset(schemas)


@pytest.mark.parametrize("kind,name", [("tables", "orders"), ("views", "open_orders")])
def test_duplicate_objects_retain_schema_identity(provider_case, kind, name):
    case = provider_case
    if case.name == "sqlite":
        getter = case.adapter.get_tables if kind == "tables" else case.adapter.get_views
        assert any(row[1] == name for row in getter(case.connection))
        return
    for schema in [case.billing, case.analytics]:
        items = load_schema_folder_items(case.adapter, case.connection, case.database, kind, schema)
        assert (kind[:-1], schema, name) in items
        assert all(item[1] == schema for item in items)


def test_select_query_reads_correct_same_named_table(provider_case):
    case = provider_case
    for schema, expected in case.expected_rows.items():
        query = case.adapter.build_select_query("orders", 100, case.database, schema)
        columns, rows, truncated = case.adapter.execute_query(case.connection, query)
        assert columns == ["id", "customer", "total"]
        assert sorted(rows) == expected
        assert not truncated


def test_ancillary_metadata_and_definitions_are_scoped(provider_case):
    case = provider_case
    for schema, column, start in [(case.billing, "customer", 10000), (case.analytics, "total", 90000)]:
        for kind, expected in [("indexes", ("index", "orders_lookup", "orders")), ("triggers", ("trigger", "orders_audit", "orders")), ("sequences", ("sequence", "invoice_number", "")), ("procedures", ("procedure", schema, "close_month"))]:
            items = load_schema_folder_items(case.adapter, case.connection, case.database, kind, schema)
            assert expected in items
        index = case.adapter.get_index_definition(case.connection, "orders_lookup", "orders", case.database, schema=schema)
        assert column in index["definition"]
        # TDD regression: correct metadata is insufficient if copied DDL drops
        # its schema and could operate on another same-named table.
        qualified = f"[{schema}].[orders]" if case.name == "mssql" else f"{schema}.orders"
        assert qualified in index["definition"]
        sequence = case.adapter.get_sequence_definition(case.connection, "invoice_number", case.database, schema=schema)
        assert int(sequence["start_value"]) == start
        trigger = case.adapter.get_trigger_definition(case.connection, "orders_audit", "orders", case.database, schema=schema)
        assert case.adapter.quote_identifier(schema) in trigger["definition"] or schema in trigger["definition"]


async def settle(app, pilot):
    for _ in range(4):
        await pilot.pause(0.08)
        await app.workers.wait_for_complete()


def walk(root):
    yield root
    for child in root.children:
        yield from walk(child)


def find(app, cls, **fields):
    return next(node for node in walk(app.object_tree.root) if isinstance(node.data, cls) and all(getattr(node.data, key) == value for key, value in fields.items()))


@pytest.mark.asyncio
async def test_ui_layout_query_refresh_and_screenshot(provider_case, tmp_path, capture_dir):
    case = provider_case
    settings = MockSettingsStore({"theme": "vesper", "explorer_hierarchy": "type"})
    services = build_test_services(runtime=RuntimeConfig(settings_path=tmp_path / "settings.json", process_worker=False, process_worker_warm_on_idle=False), settings_store=settings, connection_store=MockConnectionStore([case.config]))
    app = SSMSTUI(services=services)
    async with app.run_test(size=(140, 44)) as pilot:
        await settle(app, pilot)
        app.connect_to_server(case.config)
        await settle(app, pilot)
        assert app.current_connection is not None, getattr(app.screen, "message", "Connection failed")
        app._run_command("explorer schema")
        await settle(app, pilot)
        assert settings.get("explorer_hierarchy") == "schema"
        if case.name == "sqlite":
            assert not any(isinstance(n.data, SchemaNode) for n in walk(app.object_tree.root))
            folder = find(app, FolderNode, folder_type="tables")
        else:
            schema = find(app, SchemaNode, schema=case.billing, folder_type="")
            schema.expand()
            folder = find(app, FolderNode, folder_type="tables", schema=case.billing)
        folder.expand()
        await settle(app, pilot)
        orders = find(app, TableNode, schema=case.billing, name="orders")
        orders.expand()
        await settle(app, pilot)
        assert orders.children
        app.object_tree.move_cursor(orders)
        app.action_select_table()
        await settle(app, pilot)
        assert app.results_table.row_count == len(case.expected_rows[case.billing])
        query = app.query_input.text
        assert case.adapter.quote_identifier("orders") in query
        if case.name != "sqlite":
            assert case.adapter.quote_identifier(case.billing) in query
            # Exercise every enabled object folder before capturing proof.
            # The Snowflake emulator returns an empty procedure catalog; it
            # cannot establish live routine creation/execution support.
            owner = find(app, SchemaNode, schema=case.billing, folder_type="")
            for child in owner.children:
                if isinstance(child.data, FolderNode):
                    child.expand()
                    await settle(app, pilot)
            assert not getattr(app.screen, "message", "")
        app.object_tree.focus()
        await pilot.pause()
        if capture_dir:
            capture_dir.mkdir(parents=True, exist_ok=True)
            (capture_dir / f"{case.name}.svg").write_text(app.export_screenshot(title=f"sqlit · schema hierarchy · {case.evidence}"))
        app._refresh_tree_common(notify=False)
        await settle(app, pilot)
        assert find(app, TableNode, schema=case.billing, name="orders")
        assert app.query_input.text == query
        app._run_command("explorer type")
        await settle(app, pilot)
        assert app.query_input.text == query
        assert not any(isinstance(n.data, SchemaNode) and not n.data.folder_type for n in walk(app.object_tree.root))


@pytest.mark.asyncio
async def test_process_worker_metadata_matches_direct_provider(provider_case):
    case = provider_case
    from sqlit.domains.process_worker.app.process_worker_client import ProcessWorkerClient

    client = ProcessWorkerClient()
    try:
        for schema in [case.billing, case.analytics]:
            for kind in ["tables", "views", "indexes", "triggers", "sequences", "procedures"]:
                result = await asyncio.to_thread(client.list_folder_items, config=case.config, database=case.database, folder_type=kind, schema=schema)
                assert not result.error and not result.cancelled
                assert result.items == load_schema_folder_items(case.adapter, case.connection, case.database, kind, schema)
    finally:
        client.close()


def test_every_advertised_object_folder_loads(provider_case):
    """Opening any enabled folder must not fail on its catalog query."""
    case = provider_case
    for folder in case.provider.explorer_nodes.get_root_folders(case.provider.capabilities):
        if not folder.requires(case.provider.capabilities):
            continue
        if case.name == "sqlite":
            items = case.provider.explorer_nodes.load_folder_items(case.adapter, case.provider.capabilities, case.connection, folder.kind, None)
        else:
            items = load_schema_folder_items(case.adapter, case.connection, case.database, folder.kind, case.billing)
        assert isinstance(items, list)
