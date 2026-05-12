"""Service for building ER diagrams from schema data."""

from __future__ import annotations

from typing import Any

from sqlit.domains.connections.providers.adapters.base import ColumnInfo, ForeignKeyInfo
from sqlit.domains.diagram.app.layout import build_layout, render_diagram


def build_diagram_text(
    table_names: list[str],
    columns_by_table: dict[str, list[ColumnInfo]],
    foreign_keys: list[ForeignKeyInfo],
    schemas: dict[str, str] | None = None,
) -> str:
    """Build diagram text from schema data."""
    tables: dict[str, list[tuple[str, str, bool]]] = {}
    for name in table_names:
        cols = columns_by_table.get(name, [])
        tables[name] = [(c.name, c.data_type, c.is_primary_key) for c in cols]

    table_set = set(table_names)
    fk_tuples: list[tuple[str, str, str, str]] = []
    for fk in foreign_keys:
        if fk.source_table in table_set:
            fk_tuples.append((fk.source_table, fk.source_column, fk.target_table, fk.target_column))

    layout = build_layout(tables, fk_tuples, schemas)
    lines = render_diagram(layout)
    return "\n".join(lines)


def fetch_diagram_data(
    schema_service: Any,
    database: str | None,
    table_names: list[str],
) -> tuple[dict[str, list[ColumnInfo]], list[ForeignKeyInfo]]:
    """Fetch columns and FK data for a set of tables."""
    columns_by_table: dict[str, list[ColumnInfo]] = {}
    for name in table_names:
        try:
            columns_by_table[name] = schema_service.list_columns(database, None, name)
        except Exception:
            columns_by_table[name] = []

    try:
        foreign_keys: list[ForeignKeyInfo] = schema_service.list_foreign_keys(database)
    except Exception:
        foreign_keys = []

    return columns_by_table, foreign_keys
