"""Schema-scoped catalog loading shared by the UI and process worker."""

from __future__ import annotations

from typing import Any


def load_schema_folder_items(
    inspector: Any,
    conn: Any,
    database: str | None,
    folder_type: str,
    schema: str | None,
) -> list[Any]:
    """Return existing explorer tuples, retaining exact schema ownership.

    Only providers advertising supports_schema_grouping use this path. Their
    ancillary metadata must carry schema names; unqualified names are never
    guessed to belong to a schema, even when table names happen to match.
    """
    if folder_type == "schemas":
        return list(inspector.get_schemas(conn, database))
    if schema is None:
        raise ValueError("A schema is required for schema-scoped folders")
    if folder_type in {"tables", "views"}:
        getter = inspector.get_tables if folder_type == "tables" else inspector.get_views
        kind = "table" if folder_type == "tables" else "view"
        return [(kind, owner, name) for owner, name in getter(conn, database) if owner == schema]
    if folder_type in {"indexes", "triggers"}:
        getter = inspector.get_indexes if folder_type == "indexes" else inspector.get_triggers
        kind = "index" if folder_type == "indexes" else "trigger"
        return [(kind, item.name, item.table_name) for item in getter(conn, database) if item.schema == schema]
    if folder_type == "sequences":
        return [("sequence", item.name, "") for item in inspector.get_sequences(conn, database) if item.schema == schema]
    if folder_type == "procedures":
        return [("procedure", schema, str(item)) for item in inspector.get_procedures(conn, database) if getattr(item, "schema", None) == schema]
    raise ValueError(f"Unsupported schema folder: {folder_type}")
