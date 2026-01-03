"""Schema rendering helpers for explorer tree mixins."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from rich.markup import escape as escape_markup

from sqlit.domains.explorer.domain.tree_nodes import SchemaNode, TableNode, ViewNode
from sqlit.shared.ui.protocols import TreeMixinHost

MIN_TIMER_DELAY_S = 0.001


def add_schema_grouped_items(
    host: TreeMixinHost,
    node: Any,
    db_name: str | None,
    folder_type: str,
    items: list[Any],
    default_schema: str,
) -> None:
    """Add tables/views grouped by schema."""
    by_schema: dict[str, list[Any]] = defaultdict(list)
    for item in items:
        by_schema[item[1]].append(item)

    def schema_sort_key(schema: str) -> tuple[int, str]:
        if not schema or schema == default_schema:
            return (0, schema)
        return (1, schema.lower())

    sorted_schemas = sorted(by_schema.keys(), key=schema_sort_key)
    has_multiple_schemas = len(sorted_schemas) > 1
    schema_nodes: dict[str, Any] = {}
    items_to_add: list[tuple[Any, str, str, str]] = []

    for schema in sorted_schemas:
        schema_items = by_schema[schema]
        is_default = not schema or schema == default_schema

        if is_default and not has_multiple_schemas:
            parent = node
        else:
            if schema not in schema_nodes:
                display_name = schema if schema else default_schema
                escaped_name = escape_markup(display_name)
                schema_node = node.add(f"[dim]\\[{escaped_name}][/]")
                schema_node.data = SchemaNode(
                    database=db_name, schema=schema or default_schema, folder_type=folder_type
                )
                schema_node.allow_expand = True
                schema_nodes[schema] = schema_node
            parent = schema_nodes[schema]

        for item in schema_items:
            item_type, schema_name, obj_name = item[0], item[1], item[2]
            items_to_add.append((parent, item_type, schema_name, obj_name))

    if not items_to_add:
        return

    batch_size = 200
    idx = 0
    token = object()
    tokens = getattr(host, "_schema_render_tokens", None)
    if tokens is None:
        tokens = {}
        setattr(host, "_schema_render_tokens", tokens)
    tokens[id(node)] = token

    def render_batch() -> None:
        nonlocal idx
        if tokens.get(id(node)) is not token:
            return
        end = min(idx + batch_size, len(items_to_add))
        for parent, item_type, schema_name, obj_name in items_to_add[idx:end]:
            try:
                child = parent.add(escape_markup(obj_name))
            except Exception:
                return
            if item_type == "table":
                child.data = TableNode(database=db_name, schema=schema_name, name=obj_name)
            else:
                child.data = ViewNode(database=db_name, schema=schema_name, name=obj_name)
            child.allow_expand = True
        idx = end
        if idx < len(items_to_add):
            host.set_timer(MIN_TIMER_DELAY_S, render_batch)

    render_batch()
