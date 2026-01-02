"""Tests for tree schema grouping functionality."""

from __future__ import annotations

import pytest
from rich.markup import escape as escape_markup

from sqlit.domains.explorer.domain.tree_nodes import SchemaNode, TableNode, ViewNode
from sqlit.domains.explorer.ui.mixins.tree import TreeMixin


class MockSession:
    """Mock session for testing tree operations."""

    def __init__(self, adapter, connection=None):
        self.adapter = adapter
        self.connection = connection or object()


class MockAdapter:
    """Mock adapter with configurable schema support."""

    def __init__(self, tables: list[tuple[str, str]], default_schema: str = ""):
        self._tables = tables
        self._default_schema = default_schema

    @property
    def default_schema(self) -> str:
        return self._default_schema

    def get_tables(self, conn, database=None):
        return self._tables

    def format_table_name(self, schema: str, name: str) -> str:
        if not schema or schema == self._default_schema:
            return name
        return f"{schema}.{name}"


class MockTreeNode:
    """Mock tree node for testing."""

    def __init__(self, label: str = "", data: tuple = None):
        self.label = label
        self.data = data
        self.children: list[MockTreeNode] = []
        self.allow_expand = False

    def add(self, label: str) -> MockTreeNode:
        child = MockTreeNode(label)
        self.children.append(child)
        return child

    def add_leaf(self, label: str) -> MockTreeNode:
        return self.add(label)


class TestSchemaGrouping:
    """Test that tables are grouped by schema correctly."""

    def test_single_schema_no_grouping(self):
        """When there's only one schema, tables appear directly under folder."""
        # Single schema - all tables in default schema
        adapter = MockAdapter(
            tables=[("public", "users"), ("public", "posts"), ("public", "comments")],
            default_schema="public",
        )
        session = MockSession(adapter)

        # Create a mock tree mixin instance
        mixin = object.__new__(TreeMixin)
        mixin._session = session

        # Create parent node (Tables folder)
        parent = MockTreeNode("Tables", ("folder", "tables", None))

        # Simulate loading tables
        items = [("table", s, t) for s, t in adapter.get_tables(None)]
        mixin._add_schema_grouped_items(parent, None, "tables", items, "public")

        # Should have 3 direct children (no schema folders)
        assert len(parent.children) == 3
        assert all(isinstance(child.data, TableNode) for child in parent.children)

        # Check table names
        table_names = [child.data.name for child in parent.children]
        assert "users" in table_names
        assert "posts" in table_names
        assert "comments" in table_names

    def test_multiple_schemas_creates_folders(self):
        """When there are multiple schemas, each gets an expandable folder."""
        # Multiple schemas
        adapter = MockAdapter(
            tables=[
                ("public", "users"),
                ("public", "posts"),
                ("realtime", "messages"),
                ("realtime", "subscriptions"),
            ],
            default_schema="public",
        )
        session = MockSession(adapter)

        mixin = object.__new__(TreeMixin)
        mixin._session = session

        parent = MockTreeNode("Tables", ("folder", "tables", None))

        items = [("table", s, t) for s, t in adapter.get_tables(None)]
        mixin._add_schema_grouped_items(parent, None, "tables", items, "public")

        # Should have 2 schema folders
        assert len(parent.children) == 2

        # First should be public (default schema first)
        public_folder = parent.children[0]
        assert isinstance(public_folder.data, SchemaNode)
        assert public_folder.data.schema == "public"
        assert public_folder.allow_expand is True
        assert len(public_folder.children) == 2

        # Second should be realtime
        realtime_folder = parent.children[1]
        assert isinstance(realtime_folder.data, SchemaNode)
        assert realtime_folder.data.schema == "realtime"
        assert realtime_folder.allow_expand is True
        assert len(realtime_folder.children) == 2

        # Check tables in public
        public_tables = [child.data.name for child in public_folder.children]
        assert "users" in public_tables
        assert "posts" in public_tables

        # Check tables in realtime
        realtime_tables = [child.data.name for child in realtime_folder.children]
        assert "messages" in realtime_tables
        assert "subscriptions" in realtime_tables

    def test_default_schema_first_in_order(self):
        """Default schema should appear first, others alphabetically."""
        adapter = MockAdapter(
            tables=[
                ("zebra", "table_z"),
                ("public", "table_p"),
                ("alpha", "table_a"),
            ],
            default_schema="public",
        )
        session = MockSession(adapter)

        mixin = object.__new__(TreeMixin)
        mixin._session = session

        parent = MockTreeNode("Tables", ("folder", "tables", None))

        items = [("table", s, t) for s, t in adapter.get_tables(None)]
        mixin._add_schema_grouped_items(parent, None, "tables", items, "public")

        # Should have 3 schema folders
        assert len(parent.children) == 3

        # Order: public (default), alpha, zebra
        schemas = [child.data.schema for child in parent.children]
        assert schemas == ["public", "alpha", "zebra"]

    def test_empty_schema_uses_default(self):
        """Empty schema name should use default_schema for display."""
        adapter = MockAdapter(
            tables=[
                ("", "local_table"),
                ("other", "other_table"),
            ],
            default_schema="main",
        )
        session = MockSession(adapter)

        mixin = object.__new__(TreeMixin)
        mixin._session = session

        parent = MockTreeNode("Tables", ("folder", "tables", None))

        items = [("table", s, t) for s, t in adapter.get_tables(None)]
        mixin._add_schema_grouped_items(parent, None, "tables", items, "main")

        # Should have 2 schema folders
        assert len(parent.children) == 2

        # First folder should show "main" even though schema was empty
        first_folder = parent.children[0]
        assert first_folder.data.schema == "main"

    def test_views_also_grouped(self):
        """Views should also be grouped by schema."""
        adapter = MockAdapter(
            tables=[],  # Not used for this test
            default_schema="public",
        )
        session = MockSession(adapter)

        mixin = object.__new__(TreeMixin)
        mixin._session = session

        parent = MockTreeNode("Views", ("folder", "views", None))

        # Simulate view items
        items = [
            ("view", "public", "user_summary"),
            ("view", "analytics", "daily_stats"),
        ]
        mixin._add_schema_grouped_items(parent, None, "views", items, "public")

        # Should have 2 schema folders
        assert len(parent.children) == 2

        # Check view nodes have correct type
        for schema_folder in parent.children:
            for child in schema_folder.children:
                assert isinstance(child.data, ViewNode)

    def test_table_nodes_are_expandable(self):
        """Table nodes should be expandable (for columns)."""
        adapter = MockAdapter(
            tables=[("public", "users")],
            default_schema="public",
        )
        session = MockSession(adapter)

        mixin = object.__new__(TreeMixin)
        mixin._session = session

        parent = MockTreeNode("Tables", ("folder", "tables", None))

        items = [("table", "public", "users")]
        mixin._add_schema_grouped_items(parent, None, "tables", items, "public")

        # Single schema - table directly under parent
        table_node = parent.children[0]
        assert table_node.allow_expand is True

    def test_schema_node_data_structure(self):
        """Schema nodes should have correct data structure."""
        adapter = MockAdapter(
            tables=[
                ("public", "users"),
                ("realtime", "messages"),
            ],
            default_schema="public",
        )
        session = MockSession(adapter)

        mixin = object.__new__(TreeMixin)
        mixin._session = session

        parent = MockTreeNode("Tables", ("folder", "tables", "mydb"))

        items = [("table", s, t) for s, t in adapter.get_tables(None)]
        mixin._add_schema_grouped_items(parent, "mydb", "tables", items, "public")

        # Check schema node data
        realtime_folder = parent.children[1]
        assert isinstance(realtime_folder.data, SchemaNode)
        assert realtime_folder.data.database == "mydb"
        assert realtime_folder.data.schema == "realtime"
        assert realtime_folder.data.folder_type == "tables"

    def test_table_node_data_structure(self):
        """Table nodes should have correct data structure."""
        adapter = MockAdapter(
            tables=[("realtime", "messages")],
            default_schema="public",
        )
        session = MockSession(adapter)

        mixin = object.__new__(TreeMixin)
        mixin._session = session

        parent = MockTreeNode("Tables", ("folder", "tables", "mydb"))

        items = [("table", "realtime", "messages")]
        mixin._add_schema_grouped_items(parent, "mydb", "tables", items, "public")

        # Single non-default schema still gets a folder
        schema_folder = parent.children[0]
        table_node = schema_folder.children[0]

        # Check table node data
        assert isinstance(table_node.data, TableNode)
        assert table_node.data.database == "mydb"
        assert table_node.data.schema == "realtime"
        assert table_node.data.name == "messages"

    def test_special_characters_in_schema_name(self):
        """Schema names with special characters should be escaped properly."""
        adapter = MockAdapter(
            tables=[
                ("test[brackets]", "table1"),
                ("normal", "table2"),
            ],
            default_schema="public",
        )
        session = MockSession(adapter)

        mixin = object.__new__(TreeMixin)
        mixin._session = session

        parent = MockTreeNode("Tables", ("folder", "tables", None))

        items = [("table", s, t) for s, t in adapter.get_tables(None)]
        # This should not raise an error
        mixin._add_schema_grouped_items(parent, None, "tables", items, "public")

        assert len(parent.children) == 2

    def test_special_characters_in_table_name(self):
        """Table names with special characters should be escaped properly."""
        adapter = MockAdapter(
            tables=[
                ("public", "table[with]brackets"),
                ("public", "table/with/slashes"),
            ],
            default_schema="public",
        )
        session = MockSession(adapter)

        mixin = object.__new__(TreeMixin)
        mixin._session = session

        parent = MockTreeNode("Tables", ("folder", "tables", None))

        items = [("table", s, t) for s, t in adapter.get_tables(None)]
        mixin._add_schema_grouped_items(parent, None, "tables", items, "public")

        # Single schema - tables directly under parent
        assert len(parent.children) == 2

    def test_rich_markup_in_names(self):
        """Names that look like Rich markup should be escaped."""
        adapter = MockAdapter(
            tables=[
                ("[bold]schema", "table1"),
                ("normal", "[red]table[/]"),
            ],
            default_schema="public",
        )
        session = MockSession(adapter)

        mixin = object.__new__(TreeMixin)
        mixin._session = session

        parent = MockTreeNode("Tables", ("folder", "tables", None))

        items = [("table", s, t) for s, t in adapter.get_tables(None)]
        # Should handle without errors
        mixin._add_schema_grouped_items(parent, None, "tables", items, "public")


class TestRichMarkupRendering:
    """Test that Rich markup in names doesn't break rendering."""

    def test_escape_markup_handles_closing_tag(self):
        """escape_markup should handle names with [/] in them."""
        name = "test[/]name"
        escaped = escape_markup(name)
        # Should escape the brackets
        assert "[/]" not in escaped or "\\[" in escaped

    def test_escape_markup_handles_opening_tags(self):
        """escape_markup should handle names that look like opening tags."""
        name = "[bold]test"
        escaped = escape_markup(name)
        # Rich should be able to render this without error
        from io import StringIO

        from rich.console import Console

        console = Console(file=StringIO(), force_terminal=True)
        # This should not raise an error
        console.print(f"[dim]{escaped}[/dim]")

    def test_escape_markup_handles_complex_names(self):
        """Test escaping complex schema/table names from real databases."""
        # These are examples of problematic names that could appear in Supabase
        problematic_names = [
            "auth",
            "realtime",
            "storage",
            "_realtime",
            "supabase_functions",
            "test[brackets]",
            "name[with]multiple[brackets]",
            "[/]broken",
            "has[bold]tag",
            "schema.with.dots",
            "name with spaces",
            "name/with/slashes",
        ]

        from io import StringIO

        from rich.console import Console

        for name in problematic_names:
            escaped = escape_markup(name)
            console = Console(file=StringIO(), force_terminal=True)
            # Build the same format string used in tree.py for schema labels
            # The opening bracket is escaped with backslash, closing bracket is literal
            label = f"[dim]\\[{escaped}][/]"
            # This should not raise MarkupError
            try:
                console.print(label)
            except Exception as e:
                pytest.fail(f"Failed to render label for '{name}': {e}")
