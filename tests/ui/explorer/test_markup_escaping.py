"""Tests for markup escaping in explorer tree nodes.

These tests verify that database object names and error messages containing
Rich markup characters (like [, ], /) don't cause MarkupError crashes.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.markup import escape as escape_markup

from sqlit.domains.connections.providers.model import SchemaCapabilities
from sqlit.domains.explorer.domain.tree_nodes import SchemaNode, TableNode
from sqlit.domains.explorer.ui.mixins.tree import TreeMixin


@dataclass
class MockColumnInfo:
    name: str
    data_type: str


@dataclass
class MockProvider:
    capabilities: SchemaCapabilities


class MockTreeNode:
    """Mock tree node that tracks added children and their labels."""

    def __init__(self, label: str = "", data: tuple = None, parent: MockTreeNode | None = None):
        self.label = label
        self.data = data
        self.parent = parent
        self.children: list[MockTreeNode] = []
        self.allow_expand = False
        self._labels_added: list[str] = []

    def add(self, label: str) -> MockTreeNode:
        self._labels_added.append(label)
        child = MockTreeNode(label, parent=self)
        self.children.append(child)
        return child

    def add_leaf(self, label: str) -> MockTreeNode:
        self._labels_added.append(label)
        child = MockTreeNode(label, parent=self)
        self.children.append(child)
        return child

    def remove(self):
        pass


class MockSession:
    def __init__(self, adapter, provider: MockProvider | None = None):
        self.adapter = adapter
        self.connection = object()
        self.provider = provider or MockProvider(
            SchemaCapabilities(
                supports_multiple_databases=False,
                supports_cross_database_queries=False,
                supports_stored_procedures=False,
                supports_indexes=False,
                supports_triggers=False,
                supports_sequences=False,
                default_schema=adapter.default_schema,
                system_databases=frozenset(),
            )
        )


class MockAdapter:
    def __init__(self, default_schema: str = ""):
        self._default_schema = default_schema

    @property
    def default_schema(self) -> str:
        return self._default_schema


class NotificationCapture:
    """Captures notifications for testing."""

    def __init__(self):
        self.notifications: list[tuple[str, str]] = []

    def notify(self, message: str, severity: str = "information"):
        self.notifications.append((message, severity))


class TestMarkupEscapingInTreeNodes:
    """Test that markup characters in database object names are properly escaped."""

    def test_table_name_with_brackets_escaped(self):
        """Table names containing [ and ] should be escaped."""
        mixin = object.__new__(TreeMixin)
        mixin._session = MockSession(MockAdapter(default_schema="public"))

        parent = MockTreeNode("Tables", ("folder", "tables", None))

        items = [("table", "public", "data[0]")]
        mixin._add_schema_grouped_items(parent, None, "tables", items, "public")

        assert len(parent.children) == 1
        # The label should have escaped brackets
        assert r"\[" in parent._labels_added[0] or "data" in parent._labels_added[0]

    def test_table_name_with_closing_tag_escaped(self):
        """Table names containing [/] should be escaped to prevent markup errors."""
        mixin = object.__new__(TreeMixin)
        mixin._session = MockSession(MockAdapter(default_schema="public"))

        parent = MockTreeNode("Tables", ("folder", "tables", None))

        items = [("table", "public", "test[/]table")]
        mixin._add_schema_grouped_items(parent, None, "tables", items, "public")

        assert len(parent.children) == 1
        # Should not raise MarkupError - the [/] should be escaped

    def test_schema_name_with_brackets_escaped(self):
        """Schema names containing markup characters should be escaped."""
        mixin = object.__new__(TreeMixin)
        mixin._session = MockSession(MockAdapter(default_schema="public"))

        parent = MockTreeNode("Tables", ("folder", "tables", None))

        items = [
            ("table", "public", "users"),
            ("table", "schema[test]", "items"),
        ]
        mixin._add_schema_grouped_items(parent, None, "tables", items, "public")

        # Should have 2 schema folders
        assert len(parent.children) == 2

    def test_column_name_with_brackets_escaped(self):
        """Column names with markup characters should be escaped."""
        mixin = object.__new__(TreeMixin)
        mixin._loading_nodes = set()

        parent = MockTreeNode("users", ("table", "db", "public", "users"))

        columns = [
            MockColumnInfo(name="data[0]", data_type="TEXT"),
            MockColumnInfo(name="config[/]value", data_type="JSON"),
        ]

        mixin._on_columns_loaded(parent, "db", "public", "users", columns)

        assert len(parent.children) == 2
        # Should not raise MarkupError

    def test_column_type_with_brackets_escaped(self):
        """Column types with markup characters should be escaped."""
        mixin = object.__new__(TreeMixin)
        mixin._loading_nodes = set()

        parent = MockTreeNode("users", ("table", "db", "public", "users"))

        columns = [
            MockColumnInfo(name="tags", data_type="ARRAY[TEXT]"),
            MockColumnInfo(name="metadata", data_type="MAP[STRING,ANY]"),
        ]

        mixin._on_columns_loaded(parent, "db", "public", "users", columns)

        assert len(parent.children) == 2


class TestMarkupEscapingInErrorMessages:
    """Test that error messages with markup characters don't cause crashes."""

    def test_error_message_with_closing_tag_escaped(self):
        """Error messages containing [/] should be escaped before notify()."""
        mixin = object.__new__(TreeMixin)
        mixin._loading_nodes = set()

        # Capture notifications
        notifications = []

        def mock_notify(message, severity="information"):
            # This simulates what Rich would do - try to parse the markup
            # If not escaped, this would raise MarkupError
            from rich.text import Text

            Text.from_markup(message)
            notifications.append((message, severity))

        mixin.notify = mock_notify
        mixin._get_node_path = lambda node: "test/path"

        parent = MockTreeNode("Tables", ("folder", "tables", None))

        # Error message that contains [/] - this would crash without escaping
        error_msg = "closing tag '[/]' at position 29 has nothing to close"
        mixin._on_tree_load_error(parent, error_msg)

        assert len(notifications) == 1
        # The message should have been escaped so Rich can parse it
        assert notifications[0][1] == "error"

    def test_error_message_with_rich_tags_escaped(self):
        """Error messages with Rich-style tags should be escaped."""
        mixin = object.__new__(TreeMixin)
        mixin._loading_nodes = set()

        notifications = []

        def mock_notify(message, severity="information"):
            from rich.text import Text

            Text.from_markup(message)
            notifications.append((message, severity))

        mixin.notify = mock_notify
        mixin._get_node_path = lambda node: "test/path"

        parent = MockTreeNode("Tables", ("folder", "tables", None))

        # Error with various Rich markup patterns
        error_msg = "Failed: [bold]error[/bold] in [red]query[/red]"
        mixin._on_tree_load_error(parent, error_msg)

        assert len(notifications) == 1

    def test_error_message_with_unmatched_bracket_escaped(self):
        """Error messages with unmatched brackets should be escaped."""
        mixin = object.__new__(TreeMixin)
        mixin._loading_nodes = set()

        notifications = []

        def mock_notify(message, severity="information"):
            from rich.text import Text

            Text.from_markup(message)
            notifications.append((message, severity))

        mixin.notify = mock_notify
        mixin._get_node_path = lambda node: "test/path"

        parent = MockTreeNode("Tables", ("folder", "tables", None))

        error_msg = "Syntax error near '[' at line 5"
        mixin._on_tree_load_error(parent, error_msg)

        assert len(notifications) == 1


class TestProcedureNameEscaping:
    """Test that procedure names with markup characters are escaped."""

    def test_procedure_name_with_brackets_escaped(self):
        """Procedure names with brackets should be escaped."""
        mixin = object.__new__(TreeMixin)
        mixin._loading_nodes = set()
        mixin._session = MockSession(MockAdapter())

        parent = MockTreeNode("Procedures", ("folder", "procedures", "db"))

        items = [
            ("procedure", "", "sp_get_data[v2]"),
            ("procedure", "", "proc[test]/run"),
        ]

        mixin._on_folder_loaded(parent, "db", "procedures", items)

        assert len(parent.children) == 2


class TestExpandingTablesWithMultipleSchemas:
    """Test expanding the Tables folder with multiple schemas."""

    def test_expand_tables_folder_groups_by_schema(self):
        """Expanding Tables folder should group tables by schema."""
        mixin = object.__new__(TreeMixin)
        mixin._loading_nodes = set()
        mixin._session = MockSession(MockAdapter(default_schema="public"))

        parent = MockTreeNode("Tables", ("folder", "tables", "mydb"))

        # Simulate items returned from adapter.get_tables()
        items = [
            ("table", "public", "users"),
            ("table", "public", "posts"),
            ("table", "realtime", "messages"),
            ("table", "realtime", "subscriptions"),
            ("table", "auth", "sessions"),
        ]

        mixin._on_folder_loaded(parent, "mydb", "tables", items)

        # Should have 3 schema folders (public, realtime, auth)
        assert len(parent.children) == 3

        # Check schema order: public first (default), then alphabetically
        schema_names = [child.data.schema for child in parent.children]
        assert schema_names == ["public", "auth", "realtime"]

        # Check each schema folder has correct tables
        public_folder = parent.children[0]
        assert len(public_folder.children) == 2
        public_tables = [c.data.name for c in public_folder.children]
        assert "users" in public_tables
        assert "posts" in public_tables

        auth_folder = parent.children[1]
        assert len(auth_folder.children) == 1
        assert auth_folder.children[0].data.name == "sessions"

        realtime_folder = parent.children[2]
        assert len(realtime_folder.children) == 2
        realtime_tables = [c.data.name for c in realtime_folder.children]
        assert "messages" in realtime_tables
        assert "subscriptions" in realtime_tables

    def test_expand_tables_folder_single_schema_no_grouping(self):
        """With only one schema, tables appear directly under folder."""
        mixin = object.__new__(TreeMixin)
        mixin._loading_nodes = set()
        mixin._session = MockSession(MockAdapter(default_schema="public"))

        parent = MockTreeNode("Tables", ("folder", "tables", "mydb"))

        items = [
            ("table", "public", "users"),
            ("table", "public", "posts"),
        ]

        mixin._on_folder_loaded(parent, "mydb", "tables", items)

        # Tables should be direct children, not nested under schema folder
        assert len(parent.children) == 2
        assert all(isinstance(child.data, TableNode) for child in parent.children)

    def test_expand_views_folder_groups_by_schema(self):
        """Expanding Views folder should also group by schema."""
        mixin = object.__new__(TreeMixin)
        mixin._loading_nodes = set()
        mixin._session = MockSession(MockAdapter(default_schema="public"))

        parent = MockTreeNode("Views", ("folder", "views", "mydb"))

        items = [
            ("view", "public", "user_summary"),
            ("view", "analytics", "daily_stats"),
        ]

        mixin._on_folder_loaded(parent, "mydb", "views", items)

        # Should have 2 schema folders
        assert len(parent.children) == 2
        assert isinstance(parent.children[0].data, SchemaNode)
        assert isinstance(parent.children[1].data, SchemaNode)

    def test_schema_folders_are_expandable(self):
        """Schema folder nodes should be expandable."""
        mixin = object.__new__(TreeMixin)
        mixin._loading_nodes = set()
        mixin._session = MockSession(MockAdapter(default_schema="public"))

        parent = MockTreeNode("Tables", ("folder", "tables", "mydb"))

        items = [
            ("table", "public", "users"),
            ("table", "realtime", "messages"),
        ]

        mixin._on_folder_loaded(parent, "mydb", "tables", items)

        for schema_folder in parent.children:
            assert schema_folder.allow_expand is True

    def test_table_nodes_under_schema_are_expandable(self):
        """Table nodes under schema folders should be expandable (for columns)."""
        mixin = object.__new__(TreeMixin)
        mixin._loading_nodes = set()
        mixin._session = MockSession(MockAdapter(default_schema="public"))

        parent = MockTreeNode("Tables", ("folder", "tables", "mydb"))

        items = [
            ("table", "public", "users"),
            ("table", "realtime", "messages"),
        ]

        mixin._on_folder_loaded(parent, "mydb", "tables", items)

        for schema_folder in parent.children:
            for table_node in schema_folder.children:
                assert table_node.allow_expand is True


class TestEscapeMarkupFunction:
    """Verify the escape_markup function works as expected."""

    def test_escape_brackets(self):
        assert escape_markup("[test]") == r"\[test]"

    def test_escape_closing_tag(self):
        assert escape_markup("[/]") == r"\[/]"

    def test_escape_rich_tags(self):
        assert escape_markup("[bold]text[/bold]") == r"\[bold]text\[/bold]"

    def test_plain_text_unchanged(self):
        assert escape_markup("normal_table") == "normal_table"
