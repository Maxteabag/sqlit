"""Tests ensuring expanded nodes trigger loading after restore."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import nullcontext
from unittest.mock import MagicMock

from sqlit.domains.connections.providers.explorer_nodes import DefaultExplorerNodeProvider
from sqlit.domains.connections.providers.model import SchemaCapabilities
from sqlit.domains.explorer.domain.tree_nodes import ConnectionNode, FolderNode
from sqlit.domains.explorer.ui.tree import builder as tree_builder
from sqlit.domains.explorer.ui.tree import loaders as tree_loaders


@dataclass
class MockEndpoint:
    host: str = "localhost"
    port: int = 5432
    database: str = ""


class MockConfig:
    def __init__(self, name: str = "Local", db_type: str = "mock") -> None:
        self.name = name
        self.db_type = db_type
        self.folder_path = ""
        self._endpoint = MockEndpoint()

    @property
    def tcp_endpoint(self):
        return self._endpoint

    def get_source_emoji(self) -> str:
        return ""


class MockProvider:
    def __init__(self) -> None:
        self.capabilities = SchemaCapabilities(
            supports_multiple_databases=False,
            supports_cross_database_queries=False,
            supports_stored_procedures=False,
            supports_indexes=True,
            supports_triggers=False,
            supports_sequences=False,
            default_schema="public",
            system_databases=frozenset(),
        )
        self.explorer_nodes = DefaultExplorerNodeProvider()


class MockTreeNode:
    def __init__(self, label: str = "", data=None, parent: "MockTreeNode | None" = None) -> None:
        self.label = label
        self.data = data
        self.parent = parent
        self.children: list[MockTreeNode] = []
        self.allow_expand = False
        self.is_expanded = False

    def add(self, label: str) -> "MockTreeNode":
        child = MockTreeNode(label, parent=self)
        self.children.append(child)
        return child

    def add_leaf(self, label: str) -> "MockTreeNode":
        return self.add(label)

    def set_label(self, label: str) -> None:
        self.label = label

    def remove(self) -> None:
        if self.parent:
            self.parent.children.remove(self)

    def remove_children(self) -> None:
        self.children = []

    def expand(self) -> None:
        self.is_expanded = True

    def collapse(self) -> None:
        self.is_expanded = False


class MockTree:
    def __init__(self) -> None:
        self.root = MockTreeNode("root")
        self.cursor_node = None

    def clear(self) -> None:
        self.root.children = []


class MockHost:
    def __init__(self) -> None:
        self.object_tree = MockTree()
        self.connections = [MockConfig("Local")]
        self.current_config = self.connections[0]
        self.current_connection = MagicMock()
        self.current_provider = MockProvider()
        self._session = MagicMock()
        self._session.provider = self.current_provider
        self._selected_connection_names = set()
        self._connecting_config = None
        self._connect_spinner = None
        self._expanded_paths = set()
        self._loading_nodes = set()
        self.services = MagicMock()
        self.services.runtime = MagicMock()
        self.services.runtime.process_worker = False
        self.folder_load_calls: list[str] = []
        self.column_load_calls: list[str] = []

    def _format_connection_label(self, config, status, spinner=None) -> str:
        return config.name

    def _db_type_badge(self, db_type: str) -> str:
        return db_type.upper()

    def _connect_spinner_frame(self) -> str:
        return "..."

    def _get_node_kind(self, node) -> str:
        data = getattr(node, "data", None)
        if data is None:
            return ""
        getter = getattr(data, "get_node_kind", None)
        if callable(getter):
            return str(getter())
        return ""

    def _get_node_path_part(self, data) -> str:
        getter = getattr(data, "get_node_path_part", None)
        if callable(getter):
            return str(getter())
        return ""

    def _load_folder_async(self, node, data) -> None:
        self.folder_load_calls.append(data.folder_type)

    def _load_columns_async(self, node, data) -> None:
        self.column_load_calls.append(data.name)

    def set_timer(self, delay, callback):
        callback()

    def call_after_refresh(self, callback):
        callback()

    def batch_update(self):
        return nullcontext()

    def notify(self, message, severity="info"):
        pass


def _find_folder(root: MockTreeNode, folder_type: str) -> MockTreeNode | None:
    stack = [root]
    while stack:
        node = stack.pop()
        data = getattr(node, "data", None)
        if isinstance(data, FolderNode) and data.folder_type == folder_type:
            return node
        stack.extend(reversed(node.children))
    return None


def test_refresh_restores_expanded_folder_loads_tables() -> None:
    host = MockHost()
    host._expanded_paths = {"conn:Local/folder:tables"}

    tree_builder.refresh_tree_incremental(host)

    assert host.folder_load_calls == ["tables"]


def test_refresh_restores_expanded_table_loads_columns() -> None:
    host = MockHost()

    tree_builder.refresh_tree_incremental(host)

    tables = _find_folder(host.object_tree.root, "tables")
    assert tables is not None

    host._expanded_paths = {
        "conn:Local/folder:tables",
        "conn:Local/folder:tables/table:public.users",
    }

    tree_loaders.on_folder_loaded(
        host,
        tables,
        None,
        "tables",
        [("table", "public", "users")],
    )

    assert host.column_load_calls == ["users"]
