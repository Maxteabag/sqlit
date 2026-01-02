"""Object information display helpers for explorer tree mixins."""

from __future__ import annotations

from typing import Any

from sqlit.domains.explorer.domain.tree_nodes import IndexNode, SequenceNode, TriggerNode
from sqlit.shared.ui.protocols import TreeMixinHost


def show_index_info(host: TreeMixinHost, data: IndexNode) -> None:
    """Show index definition in the results panel."""
    schema_service = host._get_schema_service()
    if not schema_service:
        return

    try:
        info = schema_service.get_index_definition(data.database, data.name, data.table_name)
        if info is None:
            host.notify("Indexes not supported for this database.", severity="warning")
            return
        display_object_info(host, "Index", info)
    except Exception as error:
        host.notify(f"Error getting index info: {error}", severity="error")


def show_trigger_info(host: TreeMixinHost, data: TriggerNode) -> None:
    """Show trigger definition in the results panel."""
    schema_service = host._get_schema_service()
    if not schema_service:
        return

    try:
        info = schema_service.get_trigger_definition(data.database, data.name, data.table_name)
        if info is None:
            host.notify("Triggers not supported for this database.", severity="warning")
            return
        display_object_info(host, "Trigger", info)
    except Exception as error:
        host.notify(f"Error getting trigger info: {error}", severity="error")


def show_sequence_info(host: TreeMixinHost, data: SequenceNode) -> None:
    """Show sequence information in the results panel."""
    schema_service = host._get_schema_service()
    if not schema_service:
        return

    try:
        info = schema_service.get_sequence_definition(data.database, data.name)
        if info is None:
            host.notify("Sequences not supported for this database.", severity="warning")
            return
        display_object_info(host, "Sequence", info)
    except Exception as error:
        host.notify(f"Error getting sequence info: {error}", severity="error")


def display_object_info(host: TreeMixinHost, object_type: str, info: dict[str, Any]) -> None:
    """Display object info in the results table as a Property/Value view."""
    rows: list[tuple[str, str]] = []
    for key, value in info.items():
        if value is None:
            continue
        display_key = key.replace("_", " ").title()
        if isinstance(value, list):
            display_value = ", ".join(str(v) for v in value) if value else "(none)"
        elif isinstance(value, bool):
            display_value = "Yes" if value else "No"
        else:
            display_value = str(value)
        rows.append((display_key, display_value))

    host._replace_results_table(["Property", "Value"], rows)

    host._last_result_columns = ["Property", "Value"]
    host._last_result_rows = rows
    host._last_result_row_count = len(rows)

    host.notify(f"{object_type}: {info.get('name', 'Unknown')}")

    definition = info.get("definition")
    if definition:
        host.query_input.text = f"/*\n{definition}\n*/"
