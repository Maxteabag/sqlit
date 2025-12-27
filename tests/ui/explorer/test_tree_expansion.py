"""Tests for tree node expansion with schema grouping."""

from __future__ import annotations

from unittest.mock import MagicMock

from sqlit.ui.mixins.tree import TreeMixin
from sqlit.ui.tree_nodes import FolderNode, LoadingNode, SchemaNode, TableNode


class MockTreeNode:
    """Mock tree node for testing expansion."""

    def __init__(self, label: str = "", data: tuple = None, parent: MockTreeNode | None = None):
        self.label = label
        self.data = data
        self.parent = parent
        self.children: list[MockTreeNode] = []
        self.allow_expand = False
        self.is_expanded = False

    def add(self, label: str) -> MockTreeNode:
        child = MockTreeNode(label, parent=self)
        self.children.append(child)
        return child

    def add_leaf(self, label: str) -> MockTreeNode:
        return self.add(label)

    def remove(self):
        if self.parent:
            self.parent.children.remove(self)

    def expand(self):
        self.is_expanded = True

    def collapse(self):
        self.is_expanded = False


class MockTree:
    """Mock Tree widget."""

    def __init__(self):
        self.root = MockTreeNode("root")


class MockAdapter:
    """Mock adapter that returns tables with multiple schemas."""

    def __init__(self, tables: list[tuple[str, str]], default_schema: str = "public"):
        self._tables = tables
        self._default_schema = default_schema
        self.supports_cross_database_queries = True  # Default to True for tests

    @property
    def default_schema(self) -> str:
        return self._default_schema

    def get_tables(self, conn, database=None) -> list[tuple[str, str]]:
        return self._tables

    def get_views(self, conn, database=None) -> list[tuple[str, str]]:
        return []


class MockConfig:
    """Mock connection config."""

    def __init__(self, database: str | None = None, name: str = "test_connection"):
        self.database = database
        self.name = name


class MockSession:
    def __init__(self, adapter):
        self.adapter = adapter
        self.connection = MagicMock()


class MockNodeExpandedEvent:
    """Mock event for tree node expansion."""

    def __init__(self, node: MockTreeNode):
        self.node = node


class TestTreeExpansion:
    """Test tree node expansion behavior."""

    def _create_mixin_with_adapter(self, tables: list[tuple[str, str]], default_schema: str = "public"):
        """Create a TreeMixin instance with mocked dependencies."""
        mixin = object.__new__(TreeMixin)
        adapter = MockAdapter(tables, default_schema)
        mixin._session = MockSession(adapter)
        mixin._loading_nodes = set()
        mixin._expanded_paths = set()
        mixin._active_database = "mydb"
        mixin.current_connection = MagicMock()
        mixin.current_adapter = adapter
        mixin.current_config = MockConfig(database="mydb")
        mixin.object_tree = MockTree()
        mixin.call_later = lambda fn: None
        # Mock methods called by set_default_database
        mixin.notify = MagicMock()
        mixin._update_status_bar = MagicMock()
        mixin._update_database_labels = MagicMock()
        mixin._load_schema_cache = MagicMock()
        return mixin, adapter

    def test_expand_folder_triggers_async_load(self):
        """Expanding a folder should add loading placeholder and start async load."""
        tables = [("public", "users"), ("realtime", "messages")]
        mixin, adapter = self._create_mixin_with_adapter(tables)

        tables_folder = MockTreeNode("Tables", FolderNode(folder_type="tables", database="mydb"))

        load_called = False

        def mock_load(node, data):
            nonlocal load_called
            load_called = True

        mixin._load_folder_async = mock_load

        event = MockNodeExpandedEvent(tables_folder)
        mixin.on_tree_node_expanded(event)

        assert len(tables_folder.children) == 1
        assert isinstance(tables_folder.children[0].data, LoadingNode)
        assert load_called

    def test_expand_creates_schema_folders(self):
        """Expanding Tables folder groups tables by schema."""
        tables = [
            ("public", "users"),
            ("public", "posts"),
            ("realtime", "messages"),
        ]
        mixin, adapter = self._create_mixin_with_adapter(tables)

        tables_folder = MockTreeNode("Tables", FolderNode(folder_type="tables", database="mydb"))

        def mock_load_folder_async(node, data):
            items = [("table", s, t) for s, t in tables]
            mixin._on_folder_loaded(node, data.database, data.folder_type, items)

        mixin._load_folder_async = mock_load_folder_async

        event = MockNodeExpandedEvent(tables_folder)
        mixin.on_tree_node_expanded(event)

        # Should have 2 schema folders (public, realtime)
        assert len(tables_folder.children) == 2

        schema_names = [child.data.schema for child in tables_folder.children]
        assert "public" in schema_names
        assert "realtime" in schema_names

    def test_already_loaded_folder_does_not_reload(self):
        """Expanding a folder with existing children should not reload."""
        mixin, adapter = self._create_mixin_with_adapter([("public", "users")])

        tables_folder = MockTreeNode("Tables", FolderNode(folder_type="tables", database="mydb"))
        existing = tables_folder.add("users")
        existing.data = TableNode(database="mydb", schema="public", name="users")

        load_called = False

        def mock_load(node, data):
            nonlocal load_called
            load_called = True

        mixin._load_folder_async = mock_load

        event = MockNodeExpandedEvent(tables_folder)
        mixin.on_tree_node_expanded(event)

        assert not load_called

    def test_expand_table_loads_columns(self):
        """Expanding a table node should trigger column loading."""
        mixin, adapter = self._create_mixin_with_adapter([])

        table_node = MockTreeNode("users", TableNode(database="mydb", schema="public", name="users"))

        load_columns_called = False

        def mock_load_columns(node, data):
            nonlocal load_columns_called
            load_columns_called = True

        mixin._load_columns_async = mock_load_columns

        event = MockNodeExpandedEvent(table_node)
        mixin.on_tree_node_expanded(event)

        assert load_columns_called
        assert isinstance(table_node.children[0].data, LoadingNode)

    def test_expand_without_connection_is_noop(self):
        """Expanding when not connected should do nothing."""
        mixin = object.__new__(TreeMixin)
        mixin._loading_nodes = set()
        mixin._expanded_paths = set()
        mixin.current_connection = None
        mixin.current_adapter = None
        mixin.object_tree = MockTree()
        mixin.call_later = lambda fn: None

        tables_folder = MockTreeNode("Tables", FolderNode(folder_type="tables", database="mydb"))

        load_called = False

        def mock_load(node, data):
            nonlocal load_called
            load_called = True

        mixin._load_folder_async = mock_load

        event = MockNodeExpandedEvent(tables_folder)
        mixin.on_tree_node_expanded(event)

        assert not load_called
        assert len(tables_folder.children) == 0

    def test_schema_folder_tables_are_expandable(self):
        """Tables under schema folders should be expandable for columns."""
        mixin = object.__new__(TreeMixin)
        mixin._loading_nodes = set()
        mixin._session = MockSession(MockAdapter([], "public"))

        tables_folder = MockTreeNode("Tables", FolderNode(folder_type="tables", database="mydb"))

        items = [
            ("table", "public", "users"),
            ("table", "realtime", "messages"),
        ]

        mixin._on_folder_loaded(tables_folder, "mydb", "tables", items)

        for schema_folder in tables_folder.children:
            assert isinstance(schema_folder.data, SchemaNode)
            for table_node in schema_folder.children:
                assert isinstance(table_node.data, TableNode)
                assert table_node.allow_expand is True
