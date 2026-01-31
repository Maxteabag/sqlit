"""Test that tree refresh reloads connections from disk."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestTreeRefresh:
    """Test that pressing 'f' in explorer reloads saved connections."""

    def test_action_refresh_tree_reloads_connections(self):
        """
        Bug: action_refresh_tree didn't reload saved connections from store.
        Fix: Now it calls connection_store.load_all() and updates self.connections.
        """
        from sqlit.domains.connections.domain.config import ConnectionConfig

        # Create a mock host with required attributes
        mock_host = MagicMock()

        # Set up initial state
        initial_conn = ConnectionConfig(name="existing", db_type="sqlite")
        mock_host.connections = [initial_conn]

        # Mock the services and store
        mock_store = MagicMock()
        new_conn = ConnectionConfig(name="new-cli-conn", db_type="postgresql")
        mock_store.load_all.return_value = [initial_conn, new_conn]

        mock_services = MagicMock()
        mock_services.connection_store = mock_store
        mock_host.services = mock_services

        # Mock other methods
        mock_host._get_object_cache.return_value = MagicMock()
        mock_host._schema_cache = {"columns": {}}
        mock_host._loading_nodes = set()
        mock_host._schema_service = None
        mock_host.refresh_tree = MagicMock()

        # Import and call the mixin method directly
        from sqlit.domains.explorer.ui.mixins.tree import TreeMixin

        # Before: 1 connection
        assert len(mock_host.connections) == 1

        # Call refresh using the mixin method bound to our mock
        TreeMixin.action_refresh_tree(mock_host)

        # Verify store.load_all was called
        mock_store.load_all.assert_called_once_with(load_credentials=False)

        # After: 2 connections (reloaded from store)
        assert len(mock_host.connections) == 2
        assert mock_host.connections[1].name == "new-cli-conn"

        # Verify tree was rebuilt
        mock_host.refresh_tree.assert_called_once()

    def test_action_refresh_tree_handles_store_error(self):
        """Test that refresh handles store errors gracefully."""
        from sqlit.domains.connections.domain.config import ConnectionConfig

        mock_host = MagicMock()
        mock_host.connections = [ConnectionConfig(name="existing", db_type="sqlite")]

        mock_store = MagicMock()
        mock_store.load_all.side_effect = Exception("File not found")

        mock_services = MagicMock()
        mock_services.connection_store = mock_store
        mock_host.services = mock_services

        mock_host._get_object_cache.return_value = MagicMock()
        mock_host._schema_cache = {"columns": {}}
        mock_host._loading_nodes = set()
        mock_host._schema_service = None
        mock_host.refresh_tree = MagicMock()

        from sqlit.domains.explorer.ui.mixins.tree import TreeMixin

        # Should not raise, should keep existing connections
        TreeMixin.action_refresh_tree(mock_host)

        # Connections should be unchanged
        assert len(mock_host.connections) == 1
        assert mock_host.connections[0].name == "existing"

        # Tree should still be refreshed
        mock_host.refresh_tree.assert_called_once()

    def test_action_refresh_tree_handles_missing_services(self):
        """Test that refresh handles missing services gracefully."""
        from sqlit.domains.connections.domain.config import ConnectionConfig

        mock_host = MagicMock()
        mock_host.connections = [ConnectionConfig(name="existing", db_type="sqlite")]

        # No services attribute
        del mock_host.services

        mock_host._get_object_cache.return_value = MagicMock()
        mock_host._schema_cache = {"columns": {}}
        mock_host._loading_nodes = set()
        mock_host._schema_service = None
        mock_host.refresh_tree = MagicMock()

        from sqlit.domains.explorer.ui.mixins.tree import TreeMixin

        # Should not raise
        TreeMixin.action_refresh_tree(mock_host)

        # Connections should be unchanged
        assert len(mock_host.connections) == 1

        # Tree should still be refreshed
        mock_host.refresh_tree.assert_called_once()
