"""Explorer node providers for the tree UI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from sqlit.domains.connections.providers.model import (
    IndexInspector,
    ProcedureInspector,
    SchemaCapabilities,
    SchemaInspector,
    SequenceInspector,
    TriggerInspector,
)


@dataclass(frozen=True)
class ExplorerFolderSpec:
    kind: str
    label: str
    requires: Callable[[SchemaCapabilities], bool]


class ExplorerNodeProvider(Protocol):
    def get_root_folders(self, capabilities: SchemaCapabilities) -> list[ExplorerFolderSpec]: ...

    def load_folder_items(
        self,
        inspector: SchemaInspector,
        capabilities: SchemaCapabilities,
        conn: Any,
        folder_kind: str,
        database: str | None,
    ) -> list[tuple[str, str, str]]:
        ...


class DefaultExplorerNodeProvider:
    def get_root_folders(self, capabilities: SchemaCapabilities) -> list[ExplorerFolderSpec]:
        return [
            ExplorerFolderSpec("tables", "Tables", lambda caps: True),
            ExplorerFolderSpec("views", "Views", lambda caps: True),
            ExplorerFolderSpec("indexes", "Indexes", lambda caps: caps.supports_indexes),
            ExplorerFolderSpec("triggers", "Triggers", lambda caps: caps.supports_triggers),
            ExplorerFolderSpec("sequences", "Sequences", lambda caps: caps.supports_sequences),
            ExplorerFolderSpec(
                "procedures",
                "Stored Procedures",
                lambda caps: caps.supports_stored_procedures,
            ),
        ]

    def load_folder_items(
        self,
        inspector: SchemaInspector,
        capabilities: SchemaCapabilities,
        conn: Any,
        folder_kind: str,
        database: str | None,
    ) -> list[tuple[str, str, str]]:
        if folder_kind == "tables":
            return [("table", s, t) for s, t in inspector.get_tables(conn, database)]
        if folder_kind == "views":
            return [("view", s, v) for s, v in inspector.get_views(conn, database)]
        if folder_kind == "indexes" and isinstance(inspector, IndexInspector):
            return [("index", i.name, i.table_name) for i in inspector.get_indexes(conn, database)]
        if folder_kind == "triggers" and isinstance(inspector, TriggerInspector):
            return [("trigger", t.name, t.table_name) for t in inspector.get_triggers(conn, database)]
        if folder_kind == "sequences" and isinstance(inspector, SequenceInspector):
            return [("sequence", s.name, "") for s in inspector.get_sequences(conn, database)]
        if folder_kind == "procedures" and isinstance(inspector, ProcedureInspector):
            return [("procedure", "", p) for p in inspector.get_procedures(conn, database)]
        return []
