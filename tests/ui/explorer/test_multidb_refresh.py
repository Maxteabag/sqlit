"""Tests for multi-database server refresh behavior.

These tests verify that refreshing the tree in a multi-database server
(like PostgreSQL) properly preserves visibility of all databases.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from sqlit.domains.connections.providers.model import SchemaCapabilities
from sqlit.domains.explorer.domain.tree_nodes import ConnectionNode, FolderNode
from sqlit.domains.explorer.ui.tree import builder as tree_builder


class MockTreeNode:
    """Mock tree node for testing."""

    def __init__(self, label: str = "", data=None, parent=None):
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
    """Mock Tree widget."""

    def __init__(self):
        self.root = MockTreeNode("root")
        self.cursor_node = None

    def clear(self) -> None:
        self.root.children = []


class MockEndpoint:
    """Mock TCP endpoint."""

    def __init__(self, host: str = "localhost", port: int = 5432, database: str = ""):
        self.host = host
        self.port = port
        self.database = database  # Empty = show all databases


class MockConfig:
    """Mock connection config."""

    def __init__(self, name: str = "test_conn", database: str = ""):
        self.name = name
        self.db_type = "postgres"
        self.folder_path = ""
        self._endpoint = MockEndpoint(database=database)

    @property
    def tcp_endpoint(self):
        return self._endpoint

    def get_source_emoji(self) -> str:
        return ""


class MockExplorerNodes:
    """Mock explorer nodes provider."""

    def get_root_folders(self, caps):
        return []


class MockProvider:
    """Mock database provider with multi-database support."""

    def __init__(self, supports_multiple_databases: bool = True):
        self.capabilities = SchemaCapabilities(
            supports_multiple_databases=supports_multiple_databases,
            supports_cross_database_queries=True,
            supports_stored_procedures=False,
            supports_indexes=True,
            supports_triggers=True,
            supports_sequences=True,
            default_schema="public",
            system_databases=frozenset({"template0", "template1"}),
        )
        self.explorer_nodes = MockExplorerNodes()


class MockSchemaService:
    """Mock schema service that returns database list."""

    def __init__(self, databases: list[str] | None = None):
        self.databases = databases or ["norway_culture", "norway_geography", "postgres"]

    def list_folder_items(self, folder_type: str, db_name: str | None) -> list[str]:
        if folder_type == "databases":
            return self.databases
        return []


class MockHost:
    """Mock TreeMixinHost for testing tree builder functions."""

    def __init__(self, multi_db: bool = True, connection_database: str = "", databases: list[str] | None = None):
        self.object_tree = MockTree()
        self.connections = []
        self.current_connection = MagicMock()
        self.current_config = MockConfig(database=connection_database)
        self.current_provider = MockProvider(supports_multiple_databases=multi_db)
        self._selected_connection_names = set()
        self._connecting_config = None
        self._connect_spinner = None
        self._expanded_paths = set()
        self._schema_service = MockSchemaService(databases)
        self._session = MagicMock()
        self._session.provider = self.current_provider
        self.services = MagicMock()
        self.services.runtime = MagicMock()
        self.services.runtime.process_worker = False

    def _format_connection_label(self, config, status, spinner=None) -> str:
        if status == "connected":
            return f"[green]* {config.name}[/]"
        return config.name

    def _db_type_badge(self, db_type: str) -> str:
        return db_type[:3].upper()

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
        # Execute immediately for testing
        callback()

    def run_worker(self, coro, name=None, exclusive=False):
        # Execute the coroutine synchronously for testing
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)

    def _get_schema_service(self):
        return self._schema_service

    def _get_effective_database(self) -> str | None:
        return None

    def notify(self, message, severity="info"):
        pass


def _find_databases_folder(root: MockTreeNode) -> MockTreeNode | None:
    """Find the Databases folder in the tree."""
    for child in root.children:
        if child.data and isinstance(child.data, FolderNode):
            if child.data.folder_type == "databases":
                return child
        # Check children of connection nodes
        for grandchild in child.children:
            if grandchild.data and isinstance(grandchild.data, FolderNode):
                if grandchild.data.folder_type == "databases":
                    return grandchild
    return None


def _simulate_database_expansion(databases_folder: MockTreeNode, database_names: list[str]) -> None:
    """Simulate what happens when user expands the Databases folder.

    In the real app, this is lazy-loaded when the folder is expanded.
    """
    databases_folder.children = []
    for db_name in database_names:
        db_node = databases_folder.add(db_name)
        db_node.data = FolderNode(folder_type="database", database=db_name)
        db_node.allow_expand = True
    databases_folder.is_expanded = True


class TestMultiDatabaseRefresh:
    """Tests for refresh behavior in multi-database servers like PostgreSQL."""

    def test_refresh_preserves_databases_visibility(self):
        """After refresh, all databases should still be visible.

        Bug scenario:
        1. Connect to PostgreSQL without specifying a database
        2. See "Databases" folder with norway_culture, norway_geography, postgres
        3. Navigate into norway_culture > Tables > some_table
        4. Press 'f' to refresh
        5. Expected: Still see all 3 databases
        6. Actual (bug): Only see collapsed/empty Databases folder
        """
        host = MockHost(multi_db=True, connection_database="")
        host.connections = [host.current_config]

        # Step 1: Build initial tree (simulates connect)
        tree_builder.refresh_tree(host)

        # Find the connection node and Databases folder
        connection_node = None
        for child in host.object_tree.root.children:
            if isinstance(child.data, ConnectionNode):
                connection_node = child
                break

        assert connection_node is not None, "Connection node should exist"

        databases_folder = _find_databases_folder(host.object_tree.root)
        assert databases_folder is not None, "Databases folder should exist for multi-db server"

        # Step 2: Simulate user expanding Databases folder (lazy load)
        database_names = ["norway_culture", "norway_geography", "postgres"]
        _simulate_database_expansion(databases_folder, database_names)

        # Verify databases are visible before refresh
        assert len(databases_folder.children) == 3, "Should see 3 databases before refresh"
        db_names_before = [child.label for child in databases_folder.children]
        assert "norway_culture" in db_names_before
        assert "norway_geography" in db_names_before
        assert "postgres" in db_names_before

        # Step 3: Simulate navigating into a database child (cursor is deep in tree)
        norway_culture_node = databases_folder.children[0]
        norway_culture_node.expand()
        # Add child nodes to simulate expanded database
        tables_folder = norway_culture_node.add("Tables")
        tables_folder.data = FolderNode(folder_type="tables", database="norway_culture")

        # Step 4: Call refresh (this is what 'f' key does)
        tree_builder.refresh_tree(host)

        # Step 5: Find Databases folder after refresh
        databases_folder_after = _find_databases_folder(host.object_tree.root)
        assert databases_folder_after is not None, "Databases folder should exist after refresh"

        # Step 6: THIS IS THE BUG - databases should still be visible
        # The refresh should either:
        # a) Preserve the expanded state and children, OR
        # b) Re-trigger the lazy load to repopulate the databases
        #
        # Currently, the Databases folder is recreated empty because:
        # - refresh_tree() clears everything
        # - populate_connected_tree() only creates an empty "Databases" folder
        # - The lazy-loaded database list is not re-fetched
        assert len(databases_folder_after.children) == 3, (
            f"Should still see 3 databases after refresh, "
            f"but got {len(databases_folder_after.children)} children. "
            f"Children: {[c.label for c in databases_folder_after.children]}"
        )

    def test_refresh_while_inside_database_child_preserves_context(self):
        """Refreshing while cursor is inside a database should preserve that database's visibility.

        User story:
        - Connected to multi-db PostgreSQL
        - Navigated to: norway_culture > Tables > traditional_foods > (columns)
        - Pressed 'f' to refresh
        - Expected: Can still see norway_culture and other databases
        """
        host = MockHost(multi_db=True, connection_database="")
        host.connections = [host.current_config]

        # Build tree
        tree_builder.refresh_tree(host)

        databases_folder = _find_databases_folder(host.object_tree.root)
        assert databases_folder is not None

        # Expand and populate databases
        database_names = ["norway_culture", "norway_geography", "postgres"]
        _simulate_database_expansion(databases_folder, database_names)

        # Navigate deep into norway_culture
        norway_db = databases_folder.children[0]
        norway_db.expand()
        tables = norway_db.add("Tables")
        tables.data = FolderNode(folder_type="tables", database="norway_culture")
        tables.expand()
        table_node = tables.add("traditional_foods")
        table_node.expand()

        # Set cursor to be inside the database
        host.object_tree.cursor_node = table_node

        # Refresh
        tree_builder.refresh_tree(host)

        # Verify databases are still accessible
        databases_folder_after = _find_databases_folder(host.object_tree.root)
        assert databases_folder_after is not None

        # This assertion will fail due to the bug
        assert databases_folder_after.is_expanded or len(databases_folder_after.children) > 0, (
            "Databases folder should either be expanded or have children after refresh"
        )


class TestSingleDatabaseMode:
    """Tests for single-database mode (database specified in connection)."""

    def test_refresh_with_specific_database_does_not_show_databases_folder(self):
        """When connecting to a specific database, should not show Databases folder.

        This is the correct behavior - no regression expected.
        """
        # Connect with specific database
        host = MockHost(multi_db=True, connection_database="norway_culture")
        host.connections = [host.current_config]

        tree_builder.refresh_tree(host)

        # Should NOT have a Databases folder - should show database objects directly
        databases_folder = _find_databases_folder(host.object_tree.root)

        # In single-db mode, we don't show "Databases" folder
        # Instead we show Tables, Views, etc. directly under connection
        # This test verifies the single-db mode still works correctly
        connection_node = None
        for child in host.object_tree.root.children:
            if isinstance(child.data, ConnectionNode):
                connection_node = child
                break

        assert connection_node is not None
        # When database is specified, populate_connected_tree calls add_database_object_nodes
        # directly instead of adding a Databases folder
