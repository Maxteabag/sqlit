"""Test auto-reconnect after driver installation restart."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from sqlit.domains.connections.domain.config import ConnectionConfig


class TestAutoReconnectAfterDriverInstall:
    """Test that app auto-connects after driver install restart."""

    def test_pending_connection_cache_written_on_missing_driver(self):
        """
        When user tries to connect but driver is missing,
        the connection name should be cached for auto-reconnect after restart.
        """
        from sqlit.domains.connections.ui.restart_cache import (
            get_restart_cache_path,
            write_pending_connection_cache,
        )

        config = ConnectionConfig(name="my-mssql-server", db_type="mssql")

        # Write the pending connection cache
        write_pending_connection_cache(config.name)

        # Verify cache was written
        cache_path = get_restart_cache_path()
        assert cache_path.exists()

        payload = json.loads(cache_path.read_text())
        assert payload["version"] == 2
        assert payload["type"] == "pending_connection"
        assert payload["connection_name"] == "my-mssql-server"

        # Cleanup
        cache_path.unlink(missing_ok=True)

    def test_startup_reads_pending_connection_and_connects(self):
        """
        On startup, if pending_connection cache exists,
        app should auto-connect to that connection.
        """
        from sqlit.domains.connections.ui.restart_cache import (
            get_restart_cache_path,
            write_pending_connection_cache,
        )
        from sqlit.domains.shell.app.startup_flow import maybe_auto_connect_pending

        # Setup: Write pending connection cache
        write_pending_connection_cache("my-mssql-server")

        # Mock app with the saved connection
        mock_app = MagicMock()
        saved_config = ConnectionConfig(name="my-mssql-server", db_type="mssql")
        mock_app.connections = [saved_config]
        mock_app.connect_to_server = MagicMock()
        mock_app.call_after_refresh = MagicMock()

        # Call the startup function
        result = maybe_auto_connect_pending(mock_app)

        # Should have scheduled a connection via call_after_refresh
        assert result is True
        mock_app.call_after_refresh.assert_called_once()

        # Execute the callback to verify it calls connect_to_server
        callback = mock_app.call_after_refresh.call_args[0][0]
        callback()
        mock_app.connect_to_server.assert_called_once_with(saved_config)

        # Cache should be cleared
        assert not get_restart_cache_path().exists()

    def test_startup_ignores_missing_connection(self):
        """
        If the cached connection no longer exists, don't crash.
        """
        from sqlit.domains.connections.ui.restart_cache import (
            get_restart_cache_path,
            write_pending_connection_cache,
        )
        from sqlit.domains.shell.app.startup_flow import maybe_auto_connect_pending

        write_pending_connection_cache("deleted-connection")

        mock_app = MagicMock()
        mock_app.connections = []  # No connections
        mock_app.connect_to_server = MagicMock()

        result = maybe_auto_connect_pending(mock_app)

        # Should return False (no connection made)
        assert result is False
        mock_app.connect_to_server.assert_not_called()

        # Cache should still be cleared
        assert not get_restart_cache_path().exists()
