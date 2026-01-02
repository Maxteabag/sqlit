"""Unit tests for transaction executor reset on connection switch.

This tests the fix for the bug where switching connections would leave a stale
TransactionExecutor pointing to the old server, causing queries to run on the
wrong database while the explorer showed the correct (new) schema.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint

# Patch target - TransactionExecutor is imported inside _get_transaction_executor
EXECUTOR_PATCH_TARGET = "sqlit.domains.query.app.transaction.TransactionExecutor"


class TestExecutorResetOnConfigChange:
    """Tests that _get_transaction_executor creates new executor when config changes."""

    def _make_config(self, name: str, host: str = "localhost", port: str = "5432") -> ConnectionConfig:
        """Create a test connection config."""
        return ConnectionConfig(
            name=name,
            db_type="postgresql",
            endpoint=TcpEndpoint(
                host=host,
                port=port,
                database="testdb",
                username="user",
                password="pass",
            ),
        )

    def _make_mixin_instance(self) -> MagicMock:
        """Create a mock object that has QueryExecutionMixin's executor methods."""
        from sqlit.domains.query.ui.mixins.query_execution import QueryExecutionMixin

        # Create instance with mixin's methods
        instance = MagicMock()
        instance._transaction_executor = None
        instance._transaction_executor_config = None

        # Bind the actual mixin methods
        instance._get_transaction_executor = lambda config, provider: QueryExecutionMixin._get_transaction_executor(
            instance, config, provider
        )
        instance._reset_transaction_executor = lambda: QueryExecutionMixin._reset_transaction_executor(instance)

        return instance

    @patch(EXECUTOR_PATCH_TARGET)
    def test_same_config_reuses_executor(self, mock_executor_class: MagicMock) -> None:
        """Same config should return the same executor instance."""
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        instance = self._make_mixin_instance()
        config = self._make_config("server-a", host="192.168.1.1")
        provider = MagicMock()

        # First call creates executor
        executor1 = instance._get_transaction_executor(config, provider)
        assert executor1 is mock_executor
        assert mock_executor_class.call_count == 1

        # Second call with same config reuses executor
        executor2 = instance._get_transaction_executor(config, provider)
        assert executor2 is mock_executor
        assert mock_executor_class.call_count == 1  # Not called again

    @patch(EXECUTOR_PATCH_TARGET)
    def test_different_config_creates_new_executor(self, mock_executor_class: MagicMock) -> None:
        """Different config should create a new executor."""
        executor_a = MagicMock()
        executor_b = MagicMock()
        mock_executor_class.side_effect = [executor_a, executor_b]

        instance = self._make_mixin_instance()
        config_a = self._make_config("server-a", host="192.168.1.1")
        config_b = self._make_config("server-b", host="192.168.1.2")
        provider = MagicMock()

        # Connect to server A
        result_a = instance._get_transaction_executor(config_a, provider)
        assert result_a is executor_a

        # Connect to server B - should get new executor
        result_b = instance._get_transaction_executor(config_b, provider)
        assert result_b is executor_b
        assert mock_executor_class.call_count == 2

        # Old executor should have been closed
        executor_a.close.assert_called_once()

    @patch(EXECUTOR_PATCH_TARGET)
    def test_reset_clears_executor(self, mock_executor_class: MagicMock) -> None:
        """_reset_transaction_executor should close and clear the executor."""
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        instance = self._make_mixin_instance()
        config = self._make_config("server-a")
        provider = MagicMock()

        # Create executor
        instance._get_transaction_executor(config, provider)
        assert instance._transaction_executor is mock_executor

        # Reset
        instance._reset_transaction_executor()

        # Executor should be closed and cleared
        mock_executor.close.assert_called_once()
        assert instance._transaction_executor is None
        assert instance._transaction_executor_config is None

    @patch(EXECUTOR_PATCH_TARGET)
    def test_reset_then_new_config_creates_fresh_executor(self, mock_executor_class: MagicMock) -> None:
        """After reset, connecting to a new server should create fresh executor."""
        executor_a = MagicMock()
        executor_b = MagicMock()
        mock_executor_class.side_effect = [executor_a, executor_b]

        instance = self._make_mixin_instance()
        config_a = self._make_config("server-a", host="192.168.1.1")
        config_b = self._make_config("server-b", host="192.168.1.2")
        provider = MagicMock()

        # Connect to server A
        instance._get_transaction_executor(config_a, provider)

        # Disconnect (reset)
        instance._reset_transaction_executor()

        # Connect to server B
        result = instance._get_transaction_executor(config_b, provider)

        # Should have created a new executor for server B
        assert result is executor_b
        assert mock_executor_class.call_count == 2


class TestDisconnectResetsExecutor:
    """Tests that _disconnect_silent resets the transaction executor via lifecycle hooks."""

    def test_disconnect_calls_on_disconnect_lifecycle_hook(self) -> None:
        """_disconnect_silent should call _on_disconnect lifecycle hook."""
        from sqlit.domains.connections.ui.mixins.connection import ConnectionMixin

        # Create a mock that tracks method calls
        instance = MagicMock()
        instance._session = MagicMock()
        instance.current_connection = MagicMock()
        instance.current_config = MagicMock()
        instance.current_provider = MagicMock()
        instance.current_ssh_tunnel = None
        instance._direct_connection_config = None
        instance._active_database = "testdb"
        instance._clear_query_target_database = MagicMock()
        instance._on_disconnect = MagicMock()
        instance._update_section_labels = MagicMock()

        # Mock the tree_builder.refresh_tree call
        with patch("sqlit.domains.connections.ui.mixins.connection.tree_builder"):
            ConnectionMixin._disconnect_silent(instance)

        # Verify _on_disconnect lifecycle hook was called
        instance._on_disconnect.assert_called_once()

    def test_query_execution_mixin_on_disconnect_calls_reset(self) -> None:
        """QueryExecutionMixin._on_disconnect should call _reset_transaction_executor.

        Note: We can't call _on_disconnect directly with a MagicMock because of super().
        Instead, we verify _on_disconnect's implementation calls _reset_transaction_executor
        by checking the source code structure, and test _reset_transaction_executor separately.
        """
        from sqlit.domains.query.ui.mixins.query_execution import QueryExecutionMixin
        import inspect

        # Verify _on_disconnect calls _reset_transaction_executor by checking the source
        source = inspect.getsource(QueryExecutionMixin._on_disconnect)
        assert "_reset_transaction_executor" in source, (
            "_on_disconnect should call _reset_transaction_executor"
        )


class TestConnectionSwitchScenario:
    """End-to-end test for the connection switch scenario."""

    @patch(EXECUTOR_PATCH_TARGET)
    def test_full_connection_switch_flow(self, mock_executor_class: MagicMock) -> None:
        """
        Simulate: connect(A) -> query -> disconnect -> connect(B) -> query

        The second query should use server B's executor, not server A's.

        Note: We call _reset_transaction_executor directly since _on_disconnect
        uses super() which doesn't work with MagicMock. Other tests verify the
        lifecycle hook chain.
        """
        from sqlit.domains.query.ui.mixins.query_execution import QueryExecutionMixin

        executor_a = MagicMock(name="executor_for_server_a")
        executor_b = MagicMock(name="executor_for_server_b")
        mock_executor_class.side_effect = [executor_a, executor_b]

        # Create composite instance simulating the real app
        instance = MagicMock()
        instance._transaction_executor = None
        instance._transaction_executor_config = None

        # Bind mixin methods (simulating the mixin chain)
        instance._get_transaction_executor = lambda config, provider: QueryExecutionMixin._get_transaction_executor(
            instance, config, provider
        )
        instance._reset_transaction_executor = lambda: QueryExecutionMixin._reset_transaction_executor(instance)

        provider = MagicMock()

        # Step 1: Connect to server A
        config_a = ConnectionConfig(
            name="server-a",
            db_type="postgresql",
            endpoint=TcpEndpoint(host="192.168.1.1", port="5432", database="db_a"),
        )

        # Step 2: Run query on server A
        exec_a = instance._get_transaction_executor(config_a, provider)
        assert exec_a is executor_a

        # Step 3: Disconnect (simulating what _on_disconnect does)
        instance._reset_transaction_executor()

        # Verify executor was closed
        executor_a.close.assert_called_once()
        assert instance._transaction_executor is None

        # Step 4: Connect to server B
        config_b = ConnectionConfig(
            name="server-b",
            db_type="postgresql",
            endpoint=TcpEndpoint(host="192.168.1.2", port="5432", database="db_b"),
        )

        # Step 5: Run query on server B
        exec_b = instance._get_transaction_executor(config_b, provider)

        # THIS IS THE BUG FIX: should get server B's executor, not server A's
        assert exec_b is executor_b
        assert exec_b is not executor_a
