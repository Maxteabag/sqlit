"""Tree node data types for the explorer tree."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


@dataclass(frozen=True)
class ConnectionNode:
    """Node representing a database connection."""

    config: ConnectionConfig

    def get_connection_config(self) -> ConnectionConfig:
        return self.config

    def get_label_text(self) -> str:
        return self.config.name

    def get_node_kind(self) -> str:
        return "connection"

    def get_node_path_part(self) -> str:
        return f"conn:{self.config.name}"


@dataclass(frozen=True)
class ConnectionFolderNode:
    """Node representing a folder that groups connections."""

    name: str

    def get_label_text(self) -> str:
        return self.name

    def get_node_kind(self) -> str:
        return "connection_folder"

    def get_node_path_part(self) -> str:
        return f"conn_folder:{self.name}"


@dataclass(frozen=True)
class DatabaseNode:
    """Node representing a database in a multi-database server."""

    name: str

    def get_label_text(self) -> str:
        return self.name

    def get_node_kind(self) -> str:
        return "database"

    def get_node_path_part(self) -> str:
        return f"db:{self.name}"


@dataclass(frozen=True)
class FolderNode:
    """Node representing a folder (databases, tables, views, indexes, triggers, sequences, procedures)."""

    folder_type: str  # "databases", "tables", "views", "indexes", "triggers", "sequences", "procedures"
    database: str | None = None

    def get_label_text(self) -> str:
        return self.folder_type

    def get_node_kind(self) -> str:
        return "folder"

    def get_node_path_part(self) -> str:
        return f"folder:{self.folder_type}"


@dataclass(frozen=True)
class SchemaNode:
    """Node representing a schema grouping."""

    database: str | None
    schema: str
    folder_type: str

    def get_label_text(self) -> str:
        return self.schema

    def get_node_kind(self) -> str:
        return "schema"

    def get_node_path_part(self) -> str:
        return f"schema:{self.schema}"


@dataclass(frozen=True)
class TableNode:
    """Node representing a database table."""

    database: str | None
    schema: str
    name: str

    def get_label_text(self) -> str:
        return self.name

    def get_node_kind(self) -> str:
        return "table"

    def get_node_path_part(self) -> str:
        return f"table:{self.schema}.{self.name}"


@dataclass(frozen=True)
class ViewNode:
    """Node representing a database view."""

    database: str | None
    schema: str
    name: str

    def get_label_text(self) -> str:
        return self.name

    def get_node_kind(self) -> str:
        return "view"

    def get_node_path_part(self) -> str:
        return f"view:{self.schema}.{self.name}"


@dataclass(frozen=True)
class ProcedureNode:
    """Node representing a stored procedure."""

    database: str | None
    name: str

    def get_label_text(self) -> str:
        return self.name

    def get_node_kind(self) -> str:
        return "procedure"

    def get_node_path_part(self) -> str:
        return f"proc:{self.name}"


@dataclass(frozen=True)
class IndexNode:
    """Node representing a database index."""

    database: str | None
    name: str
    table_name: str

    def get_label_text(self) -> str:
        return self.name

    def get_node_kind(self) -> str:
        return "index"

    def get_node_path_part(self) -> str:
        return f"index:{self.name}"


@dataclass(frozen=True)
class TriggerNode:
    """Node representing a database trigger."""

    database: str | None
    name: str
    table_name: str

    def get_label_text(self) -> str:
        return self.name

    def get_node_kind(self) -> str:
        return "trigger"

    def get_node_path_part(self) -> str:
        return f"trigger:{self.name}"


@dataclass(frozen=True)
class SequenceNode:
    """Node representing a database sequence."""

    database: str | None
    name: str

    def get_label_text(self) -> str:
        return self.name

    def get_node_kind(self) -> str:
        return "sequence"

    def get_node_path_part(self) -> str:
        return f"sequence:{self.name}"


@dataclass(frozen=True)
class ColumnNode:
    """Node representing a table/view column."""

    database: str | None
    schema: str
    table: str
    name: str

    def get_label_text(self) -> str:
        return self.name

    def get_node_kind(self) -> str:
        return "column"

    def get_node_path_part(self) -> str:
        return ""


@dataclass(frozen=True)
class LoadingNode:
    """Placeholder node shown during async loading."""

    def get_label_text(self) -> str:
        return ""

    def get_node_kind(self) -> str:
        return "loading"

    def get_node_path_part(self) -> str:
        return ""


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
