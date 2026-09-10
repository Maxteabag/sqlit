"""Schema ownership must survive same-named objects and both catalog paths."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from sqlit.domains.connections.providers.adapters.base import IndexInfo, RoutineInfo, SequenceInfo, TriggerInfo
from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter
from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter
from sqlit.domains.connections.providers.schema_explorer import load_schema_folder_items
from sqlit.domains.connections.providers.snowflake.adapter import SnowflakeAdapter
from sqlit.domains.explorer.app.schema_service import ExplorerSchemaService


@pytest.mark.parametrize(
    "kind,method,data,expected",
    [
        ("tables", "get_tables", [("billing", "orders"), ("analytics", "orders")], [("table", "billing", "orders")]),
        ("views", "get_views", [("billing", "summary"), ("analytics", "summary")], [("view", "billing", "summary")]),
        ("indexes", "get_indexes", [IndexInfo("lookup", "orders", schema="billing"), IndexInfo("lookup", "orders", schema="analytics"), IndexInfo("unowned", "orders")], [("index", "lookup", "orders")]),
        ("triggers", "get_triggers", [TriggerInfo("audit", "orders", schema="billing"), TriggerInfo("audit", "orders", schema="analytics")], [("trigger", "audit", "orders")]),
        ("sequences", "get_sequences", [SequenceInfo("id", schema="billing"), SequenceInfo("id", schema="analytics")], [("sequence", "id", "")]),
        ("procedures", "get_procedures", [RoutineInfo("close_month", schema="billing"), RoutineInfo("close_month", schema="analytics"), "unknown"], [("procedure", "billing", "close_month")]),
    ],
)
def test_schema_scoping_never_guesses_ownership(kind, method, data, expected):
    inspector = SimpleNamespace(**{method: lambda conn, database: data})
    assert load_schema_folder_items(inspector, object(), "workbench", kind, "billing") == expected
    assert load_schema_folder_items(inspector, object(), "workbench", kind, "BILLING") == []


def test_empty_schema_is_not_inferred_from_tables():
    inspector = SimpleNamespace(get_schemas=lambda conn, database: ["billing", "empty_lab"])
    assert load_schema_folder_items(inspector, object(), None, "schemas", None) == ["billing", "empty_lab"]


def test_service_cache_separates_schema_and_database():
    inspector = MagicMock()
    inspector.get_tables.side_effect = lambda conn, db: [("billing", db + "_orders"), ("analytics", db + "_report")]
    session = SimpleNamespace(provider=SimpleNamespace(schema_inspector=inspector, capabilities=SimpleNamespace(supports_schema_grouping=True)), connection=object())
    service = ExplorerSchemaService(session=session, object_cache={})
    service._run_with_retry = lambda fn, database: fn()
    assert service.list_folder_items("tables", "one", "billing") == [("table", "billing", "one_orders")]
    assert service.list_folder_items("tables", "one", "analytics") == [("table", "analytics", "one_report")]
    assert service.list_folder_items("tables", "two", "billing") == [("table", "billing", "two_orders")]
    service.list_folder_items("tables", "one", "billing")
    assert inspector.get_tables.call_count == 3


@pytest.mark.parametrize("adapter_cls", [PostgreSQLAdapter, SQLServerAdapter, SnowflakeAdapter])
def test_advertised_providers_retain_routine_schema(adapter_cls):
    adapter = adapter_cls()
    conn = MagicMock()
    cursor = conn.cursor.return_value
    adapter._get_cursor_for_database = lambda conn, db: cursor
    cursor.fetchall.return_value = [("close_month", "billing"), ("close_month", "analytics")]
    if adapter_cls is SnowflakeAdapter:
        cursor.description = [("name",), ("schema_name",), ("is_builtin",)]
        cursor.fetchall.return_value = [("close_month", "billing", "N"), ("close_month", "analytics", "N")]
    result = adapter.get_procedures(conn, "workbench")
    assert sorted((item.schema, str(item)) for item in result) == [("analytics", "close_month"), ("billing", "close_month")]
    assert adapter.supports_schema_grouping


@pytest.mark.parametrize("adapter_cls", [PostgreSQLAdapter, SQLServerAdapter])
def test_index_schema_is_parameterized_not_interpolated(adapter_cls):
    adapter = adapter_cls()
    conn = MagicMock()
    cursor = conn.cursor.return_value
    adapter._get_cursor_for_database = lambda conn, db: cursor
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = None
    schema = "billing' OR 1=1 --"
    adapter.get_index_definition(conn, "lookup", "orders", "db", schema=schema)
    query, params = cursor.execute.call_args.args
    assert schema not in query
    assert params[-1] == schema


@pytest.mark.parametrize("adapter_cls", [PostgreSQLAdapter, SQLServerAdapter])
def test_ancillary_metadata_carries_schema(adapter_cls):
    adapter = adapter_cls()
    conn = MagicMock()
    cursor = conn.cursor.return_value
    adapter._get_cursor_for_database = lambda conn, db: cursor
    cursor.fetchall.return_value = [("same", "orders", True, "billing"), ("same", "orders", False, "analytics")]
    assert [i.schema for i in adapter.get_indexes(conn)] == ["billing", "analytics"]
    cursor.fetchall.return_value = [("same", "orders", "billing"), ("same", "orders", "analytics")]
    assert [i.schema for i in adapter.get_triggers(conn)] == ["billing", "analytics"]
    cursor.fetchall.return_value = [("same", "billing"), ("same", "analytics")]
    assert [i.schema for i in adapter.get_sequences(conn)] == ["billing", "analytics"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stale_by", ["refresh", "session", "removed", "none"])
async def test_late_folder_response_cannot_mutate_a_replaced_tree(monkeypatch, stale_by):
    from textual.widgets import Tree

    from sqlit.domains.explorer.domain.tree_nodes import FolderNode
    from sqlit.domains.explorer.ui.tree import loaders

    tree = Tree("root")
    node = tree.root.add("Tables", data=FolderNode("tables", "db", "billing"))
    jobs = []
    timers = []
    delivered = []
    host = SimpleNamespace(
        object_tree=tree,
        _session=object(),
        _tree_refresh_token=object(),
        services=SimpleNamespace(runtime=SimpleNamespace(process_worker=False)),
        _get_schema_service=lambda: SimpleNamespace(list_folder_items=lambda *args: [("table", "billing", "orders")]),
        run_worker=lambda coro, **kwargs: jobs.append(coro),
        set_timer=lambda delay, callback: timers.append(callback),
    )
    monkeypatch.setattr(loaders, "on_folder_loaded", lambda *args: delivered.append(args))
    loaders.load_folder_async(host, node, node.data)
    await jobs[0]
    if stale_by == "refresh":
        host._tree_refresh_token = object()
    elif stale_by == "session":
        host._session = object()
    elif stale_by == "removed":
        node.remove()
    for callback in timers:
        callback()
    assert len(delivered) == (1 if stale_by == "none" else 0)
    assert host._folder_load_tokens == {}


def test_closed_database_does_not_load_schemas(monkeypatch):
    from textual.widgets import Tree

    from sqlit.domains.explorer.domain.tree_nodes import DatabaseNode
    from sqlit.domains.explorer.ui.tree import builder, loaders

    tree = Tree("root")
    database = tree.root.add("workbench", data=DatabaseNode("workbench"))
    loaded = []
    host = SimpleNamespace(
        current_provider=SimpleNamespace(capabilities=SimpleNamespace(supports_schema_grouping=True), explorer_nodes=object()),
        services=SimpleNamespace(settings_store={"explorer_hierarchy": "schema"}),
    )
    monkeypatch.setattr(loaders, "load_folder_async", lambda *args: loaded.append(args))
    builder.add_database_object_nodes(host, database, "workbench")
    assert not loaded and not database.children
    database.expand()
    builder.add_database_object_nodes(host, database, "workbench")
    assert len(loaded) == 1
    assert loaded[0][2].folder_type == "schemas"
