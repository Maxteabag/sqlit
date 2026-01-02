"""Tests for explorer tree refresh functionality.

These tests verify that action_refresh_tree properly clears caches
and reloads schema data including autocomplete.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sqlit.domains.connections.providers.model import SchemaCapabilities
from sqlit.domains.explorer.ui.mixins.tree import TreeMixin


class MockTreeNode:
    """Mock tree node for testing."""

    def __init__(self, label: str = "", data=None, parent=None):
        self.label = label
        self.data = data
        self.parent = parent
        self.children: list[MockTreeNode] = []
        self.allow_expand = False
        self.is_expanded = False

    def add(self, label: str):
        child = MockTreeNode(label, parent=self)
        self.children.append(child)
        return child

    def expand(self):
        self.is_expanded = True

    def collapse(self):
        self.is_expanded = False


class MockTree:
    """Mock Tree widget."""

    def __init__(self):
        self.root = MockTreeNode("root")
        self._clear_called = False

    def clear(self):
        self._clear_called = True
        self.root.children = []


class MockSession:
    """Mock connection session."""

    def __init__(self):
        self.provider = MagicMock(
            capabilities=SchemaCapabilities(
                supports_multiple_databases=False,
                supports_cross_database_queries=False,
                supports_stored_procedures=False,
                supports_indexes=False,
                supports_triggers=False,
                supports_sequences=False,
                default_schema="public",
                system_databases=frozenset(),
            )
        )
        self.connection = MagicMock()


class TestRefreshTree:
    """Tests for action_refresh_tree method.

    These tests verify that action_refresh_tree clears all relevant caches.
    We mock refresh_tree to avoid needing full UI setup.
    """

    def _create_tree_mixin(self):
        """Create a TreeMixin instance with mocked dependencies."""
        mixin = object.__new__(TreeMixin)

        # Core state
        mixin.object_tree = MockTree()
        mixin._session = MockSession()
        mixin._loading_nodes = {"some/path"}  # Pre-populate to verify clearing
        mixin._expanded_paths = set()
        mixin._db_object_cache = {"db1": {"tables": [("public", "old_table")]}}
        mixin._schema_cache = {
            "tables": ["old_table"],
            "views": [],
            "columns": {"old_table": ["id", "name"]},
            "procedures": [],
        }
        mixin._schema_service = MagicMock()  # Pre-existing service

        # Connection state
        mixin.current_connection = MagicMock()
        mixin.current_provider = mixin._session.provider
        mixin.current_config = MagicMock()
        mixin.current_config.name = "test_conn"
        mixin.connections = []

        # Mock methods to avoid needing full UI
        mixin.notify = MagicMock()
        mixin.call_later = lambda fn: fn()
        mixin._update_status_bar = MagicMock()
        mixin._update_database_labels = MagicMock()
        # Mock refresh_tree to avoid UI dependencies
        mixin.refresh_tree = MagicMock()

        return mixin

    def test_refresh_clears_object_cache(self):
        """action_refresh_tree should clear the object cache."""
        mixin = self._create_tree_mixin()
        assert len(mixin._db_object_cache) > 0  # Pre-condition

        mixin.action_refresh_tree()

        assert len(mixin._db_object_cache) == 0

    def test_refresh_clears_columns_cache(self):
        """action_refresh_tree should clear the columns cache."""
        mixin = self._create_tree_mixin()
        assert "columns" in mixin._schema_cache
        assert len(mixin._schema_cache["columns"]) > 0  # Pre-condition

        mixin.action_refresh_tree()

        assert mixin._schema_cache["columns"] == {}

    def test_refresh_clears_loading_nodes(self):
        """action_refresh_tree should clear the loading nodes set."""
        mixin = self._create_tree_mixin()
        assert len(mixin._loading_nodes) > 0  # Pre-condition

        mixin.action_refresh_tree()

        assert len(mixin._loading_nodes) == 0

    def test_refresh_resets_schema_service(self):
        """action_refresh_tree should reset schema service to None."""
        mixin = self._create_tree_mixin()
        assert mixin._schema_service is not None  # Pre-condition

        mixin.action_refresh_tree()

        assert mixin._schema_service is None

    def test_refresh_calls_load_schema_cache(self):
        """action_refresh_tree should call _load_schema_cache if available.

        This tests the fix where refresh wasn't updating autocomplete.
        """
        mixin = self._create_tree_mixin()
        mixin._load_schema_cache = MagicMock()

        mixin.action_refresh_tree()

        mixin._load_schema_cache.assert_called_once()

    def test_refresh_without_load_schema_cache_does_not_fail(self):
        """action_refresh_tree should work even if _load_schema_cache is not available."""
        mixin = self._create_tree_mixin()
        # Don't add _load_schema_cache attribute

        # Should not raise
        mixin.action_refresh_tree()

        # Should still complete and notify
        mixin.notify.assert_called_with("Refreshed")

    def test_refresh_calls_refresh_tree(self):
        """action_refresh_tree should call refresh_tree to rebuild the UI."""
        mixin = self._create_tree_mixin()

        mixin.action_refresh_tree()

        mixin.refresh_tree.assert_called_once()

    def test_refresh_notifies_user(self):
        """action_refresh_tree should notify user of refresh."""
        mixin = self._create_tree_mixin()
        mixin._load_schema_cache = MagicMock()

        mixin.action_refresh_tree()

        mixin.notify.assert_called_with("Refreshed")


class TestRefreshTreeIntegrationWithAutocomplete:
    """Integration tests for refresh with autocomplete schema cache."""

    def test_new_tables_appear_in_autocomplete_after_refresh(self):
        """After refresh, newly created tables should appear in autocomplete.

        This was the bug: refresh would update the explorer tree but not
        the autocomplete schema cache, so new tables wouldn't show in autocomplete.
        """
        mixin = object.__new__(TreeMixin)

        # Setup initial state
        mixin.object_tree = MockTree()
        mixin._session = MockSession()
        mixin._loading_nodes = set()
        mixin._expanded_paths = set()
        mixin._db_object_cache = {}
        mixin._schema_cache = {
            "tables": ["existing_table"],
            "views": [],
            "columns": {},
            "procedures": [],
        }
        mixin._schema_service = MagicMock()
        mixin.current_connection = MagicMock()
        mixin.current_provider = mixin._session.provider
        mixin.current_config = MagicMock()
        mixin.current_config.name = "test_conn"
        mixin.connections = []
        mixin.notify = MagicMock()
        mixin.call_later = lambda fn: fn()
        mixin._update_status_bar = MagicMock()
        mixin._update_database_labels = MagicMock()
        # Mock refresh_tree to avoid UI dependencies
        mixin.refresh_tree = MagicMock()

        # Track if _load_schema_cache was called
        load_schema_called = False

        def mock_load_schema_cache():
            nonlocal load_schema_called
            load_schema_called = True
            # Simulate loading new tables (as would happen in real code)
            mixin._schema_cache["tables"] = ["existing_table", "new_table_from_db"]

        mixin._load_schema_cache = mock_load_schema_cache

        # Verify initial state
        assert "new_table_from_db" not in mixin._schema_cache["tables"]

        # Trigger refresh
        mixin.action_refresh_tree()

        # Verify _load_schema_cache was called
        assert load_schema_called, "_load_schema_cache should be called on refresh"

        # Verify new table is now in autocomplete cache
        assert "new_table_from_db" in mixin._schema_cache["tables"]
