"""Tests for restoring explorer cursor after refresh."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import nullcontext
from unittest.mock import MagicMock

from sqlit.domains.connections.providers.explorer_nodes import DefaultExplorerNodeProvider
from sqlit.domains.connections.providers.model import SchemaCapabilities
from sqlit.domains.explorer.domain.tree_nodes import ColumnNode, ConnectionNode, FolderNode, TableNode
from sqlit.domains.explorer.ui.tree import builder as tree_builder
from sqlit.domains.explorer.ui.tree import expansion_state, loaders as tree_loaders


@dataclass
class MockEndpoint:
    host: str = "localhost"
    port: int = 5432
    database: str = ""


class MockConfig:
    def __init__(self, name: str = "Test", db_type: str = "mock") -> None:
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
    def __init__(
        self,
        label: str = "",
        data=None,
        parent: "MockTreeNode | None" = None,
        tree: "MockTree | None" = None,
    ) -> None:
        self.label = label
        self.data = data
        self.parent = parent
        self.children: list[MockTreeNode] = []
        self.allow_expand = False
        self.is_expanded = False
        self._tree = tree

    def add(self, label: str) -> "MockTreeNode":
        child = MockTreeNode(label, parent=self, tree=self._tree)
        self.children.append(child)
        return child

    def add_leaf(self, label: str) -> "MockTreeNode":
        return self.add(label)

    def set_label(self, label: str) -> None:
        self.label = label

    def remove(self) -> None:
        if self.parent is None:
            return
        if self._tree:
            self._tree._on_subtree_removed(self)
        self.parent.children.remove(self)
        self.parent = None

    def remove_children(self) -> None:
        for child in list(self.children):
            child.remove()
        self.children = []

    def expand(self) -> None:
        self.is_expanded = True

    def collapse(self) -> None:
        self.is_expanded = False


class MockTree:
    def __init__(self) -> None:
        self.root = MockTreeNode("root", tree=self)
        self.cursor_node: MockTreeNode | None = None

    def _visible_nodes(self) -> list[MockTreeNode]:
        nodes: list[MockTreeNode] = []

        def walk(node: MockTreeNode) -> None:
            for child in node.children:
                nodes.append(child)
                if child.is_expanded:
                    walk(child)

        walk(self.root)
        return nodes

    def move_cursor(self, node: MockTreeNode) -> None:
        self.cursor_node = node

    def _on_subtree_removed(self, node: MockTreeNode) -> None:
        if self.cursor_node is None:
            return
        visible_before = self._visible_nodes()
        try:
            cursor_index = visible_before.index(self.cursor_node)
        except ValueError:
            return
        current = self.cursor_node
        while current:
            if current is node:
                break
            current = current.parent
        else:
            return
        # Keep cursor on the same line index after removal (Textual-like behavior).
        subtree = set()
        stack = [node]
        while stack:
            current = stack.pop()
            subtree.add(current)
            stack.extend(current.children)
        visible_after = [n for n in visible_before if n not in subtree]
        if not visible_after:
            self.cursor_node = None
            return
        if cursor_index >= len(visible_after):
            cursor_index = len(visible_after) - 1
        self.cursor_node = visible_after[cursor_index]


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

    def set_timer(self, delay, callback):
        callback()

    def call_after_refresh(self, callback):
        callback()

    def batch_update(self):
        return nullcontext()

    def notify(self, message, severity="info"):
        pass

    def _load_folder_async(self, node, data):
        """No-op for testing - folder loading is simulated manually."""
        pass

    def _load_columns_async(self, node, data):
        """No-op for testing - column loading is simulated manually."""
        pass


@dataclass
class MockColumn:
    name: str
    data_type: str = "text"


def _find_node(root: MockTreeNode, predicate) -> MockTreeNode | None:
    stack = [root]
    while stack:
        node = stack.pop()
        if predicate(node):
            return node
        stack.extend(reversed(node.children))
    return None


def _find_folder(root: MockTreeNode, folder_type: str) -> MockTreeNode | None:
    return _find_node(
        root,
        lambda node: isinstance(getattr(node, "data", None), FolderNode)
        and node.data.folder_type == folder_type,
    )


def _find_table(root: MockTreeNode, name: str) -> MockTreeNode | None:
    return _find_node(
        root,
        lambda node: isinstance(getattr(node, "data", None), TableNode) and node.data.name == name,
    )


def _find_column(root: MockTreeNode, name: str) -> MockTreeNode | None:
    return _find_node(
        root,
        lambda node: isinstance(getattr(node, "data", None), ColumnNode) and node.data.name == name,
    )


def _prime_expanded_paths(host: MockHost, nodes: list[MockTreeNode]) -> None:
    host._expanded_paths = {expansion_state.get_node_path(host, node) for node in nodes if node}


def test_refresh_restores_cursor_to_table_after_reload() -> None:
    host = MockHost()
    tree_builder.refresh_tree_incremental(host)

    connection = _find_node(host.object_tree.root, lambda node: isinstance(node.data, ConnectionNode))
    assert connection is not None
    connection.expand()

    tables = _find_folder(host.object_tree.root, "tables")
    assert tables is not None
    tables.expand()
    tree_loaders.on_folder_loaded(
        host,
        tables,
        None,
        "tables",
        [("table", "public", "users")],
    )

    users = _find_table(host.object_tree.root, "users")
    assert users is not None
    host.object_tree.move_cursor(users)
    assert host.object_tree.cursor_node is users

    _prime_expanded_paths(host, [tables])

    tree_builder.refresh_tree_incremental(host)

    tables_after = _find_folder(host.object_tree.root, "tables")
    assert tables_after is not None
    tables_after.expand()
    tree_loaders.on_folder_loaded(
        host,
        tables_after,
        None,
        "tables",
        [("table", "public", "users")],
    )

    users_after = _find_table(host.object_tree.root, "users")
    assert users_after is not None
    assert host.object_tree.cursor_node is users_after


def test_refresh_restores_cursor_to_column_after_reload() -> None:
    host = MockHost()
    tree_builder.refresh_tree_incremental(host)

    connection = _find_node(host.object_tree.root, lambda node: isinstance(node.data, ConnectionNode))
    assert connection is not None
    connection.expand()

    tables = _find_folder(host.object_tree.root, "tables")
    assert tables is not None
    tables.expand()
    tree_loaders.on_folder_loaded(
        host,
        tables,
        None,
        "tables",
        [("table", "public", "users")],
    )

    users = _find_table(host.object_tree.root, "users")
    assert users is not None
    users.expand()
    tree_loaders.on_columns_loaded(
        host,
        users,
        None,
        "public",
        "users",
        [MockColumn("id"), MockColumn("name")],
    )

    column = _find_column(host.object_tree.root, "id")
    assert column is not None
    host.object_tree.move_cursor(column)
    assert host.object_tree.cursor_node is column

    _prime_expanded_paths(host, [tables, users])

    tree_builder.refresh_tree_incremental(host)

    tables_after = _find_folder(host.object_tree.root, "tables")
    assert tables_after is not None
    tables_after.expand()
    tree_loaders.on_folder_loaded(
        host,
        tables_after,
        None,
        "tables",
        [("table", "public", "users")],
    )

    users_after = _find_table(host.object_tree.root, "users")
    assert users_after is not None
    users_after.expand()
    tree_loaders.on_columns_loaded(
        host,
        users_after,
        None,
        "public",
        "users",
        [MockColumn("id"), MockColumn("name")],
    )

    column_after = _find_column(host.object_tree.root, "id")
    assert column_after is not None
    assert host.object_tree.cursor_node is column_after
