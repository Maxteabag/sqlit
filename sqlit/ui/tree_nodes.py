"""Tree node data types for the explorer tree."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import ConnectionConfig


@dataclass(frozen=True)
class ConnectionNode:
    """Node representing a database connection."""

    config: ConnectionConfig


@dataclass(frozen=True)
class DatabaseNode:
    """Node representing a database in a multi-database server."""

    name: str


@dataclass(frozen=True)
class FolderNode:
    """Node representing a folder (databases, tables, views, indexes, triggers, sequences, procedures)."""

    folder_type: str  # "databases", "tables", "views", "indexes", "triggers", "sequences", "procedures"
    database: str | None = None


@dataclass(frozen=True)
class SchemaNode:
    """Node representing a schema grouping."""

    database: str | None
    schema: str
    folder_type: str


@dataclass(frozen=True)
class TableNode:
    """Node representing a database table."""

    database: str | None
    schema: str
    name: str


@dataclass(frozen=True)
class ViewNode:
    """Node representing a database view."""

    database: str | None
    schema: str
    name: str


@dataclass(frozen=True)
class ProcedureNode:
    """Node representing a stored procedure."""

    database: str | None
    name: str


@dataclass(frozen=True)
class IndexNode:
    """Node representing a database index."""

    database: str | None
    name: str
    table_name: str


@dataclass(frozen=True)
class TriggerNode:
    """Node representing a database trigger."""

    database: str | None
    name: str
    table_name: str


@dataclass(frozen=True)
class SequenceNode:
    """Node representing a database sequence."""

    database: str | None
    name: str


@dataclass(frozen=True)
class ColumnNode:
    """Node representing a table/view column."""

    database: str | None
    schema: str
    table: str
    name: str


@dataclass(frozen=True)
class LoadingNode:
    """Placeholder node shown during async loading."""

    pass


# Type alias for all node data types
NodeData = (
    ConnectionNode
    | DatabaseNode
    | FolderNode
    | SchemaNode
    | TableNode
    | ViewNode
    | ProcedureNode
    | IndexNode
    | TriggerNode
    | SequenceNode
    | ColumnNode
    | LoadingNode
)
