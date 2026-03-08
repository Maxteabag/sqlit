"""Unit tests for transaction state tracking.

These tests define the expected behavior for transaction state management.
Written as TDD - tests first, implementation after.
"""

from __future__ import annotations

import pytest


class TestTransactionStatementDetection:
    """Tests for detecting transaction control statements."""

    def test_detects_begin_statement(self):
        """BEGIN should be detected as starting a transaction."""
        from sqlit.domains.query.app.transaction import is_transaction_start

        assert is_transaction_start("BEGIN") is True
        assert is_transaction_start("begin") is True
        assert is_transaction_start("BEGIN;") is True
        assert is_transaction_start("  BEGIN  ") is True
        assert is_transaction_start("BEGIN TRANSACTION") is True
        assert is_transaction_start("BEGIN WORK") is True

    def test_detects_start_transaction_statement(self):
        """START TRANSACTION should be detected as starting a transaction."""
        from sqlit.domains.query.app.transaction import is_transaction_start

        assert is_transaction_start("START TRANSACTION") is True
        assert is_transaction_start("start transaction") is True

    def test_non_begin_statements_not_detected_as_start(self):
        """Non-BEGIN statements should not be detected as transaction start."""
        from sqlit.domains.query.app.transaction import is_transaction_start

        assert is_transaction_start("SELECT * FROM test") is False
        assert is_transaction_start("INSERT INTO test VALUES (1)") is False
        assert is_transaction_start("BEGINNING") is False  # Not a keyword
        assert is_transaction_start("") is False

    def test_detects_commit_statement(self):
        """COMMIT should be detected as ending a transaction."""
        from sqlit.domains.query.app.transaction import is_transaction_end

        assert is_transaction_end("COMMIT") is True
        assert is_transaction_end("commit") is True
        assert is_transaction_end("COMMIT;") is True
        assert is_transaction_end("  COMMIT  ") is True
        assert is_transaction_end("COMMIT WORK") is True
        assert is_transaction_end("COMMIT TRANSACTION") is True

    def test_detects_rollback_statement(self):
        """ROLLBACK should be detected as ending a transaction."""
        from sqlit.domains.query.app.transaction import is_transaction_end

        assert is_transaction_end("ROLLBACK") is True
        assert is_transaction_end("rollback") is True
        assert is_transaction_end("ROLLBACK;") is True
        assert is_transaction_end("  ROLLBACK  ") is True
        assert is_transaction_end("ROLLBACK WORK") is True
        assert is_transaction_end("ROLLBACK TRANSACTION") is True

    def test_non_end_statements_not_detected_as_end(self):
        """Non-COMMIT/ROLLBACK statements should not be detected as transaction end."""
        from sqlit.domains.query.app.transaction import is_transaction_end

        assert is_transaction_end("SELECT * FROM test") is False
        assert is_transaction_end("BEGIN") is False
        assert is_transaction_end("COMMITTED") is False  # Not a keyword
        assert is_transaction_end("") is False


class TestTransactionStateManager:
    """Tests for TransactionStateManager class."""

    def test_initial_state_is_not_in_transaction(self):
        """Manager should start with in_transaction=False."""
        from sqlit.domains.query.app.transaction import TransactionStateManager

        manager = TransactionStateManager()
        assert manager.in_transaction is False

    def test_begin_sets_in_transaction(self):
        """Executing BEGIN should set in_transaction=True."""
        from sqlit.domains.query.app.transaction import TransactionStateManager

        manager = TransactionStateManager()
        manager.on_query_executed("BEGIN")
        assert manager.in_transaction is True

    def test_commit_clears_in_transaction(self):
        """Executing COMMIT should set in_transaction=False."""
        from sqlit.domains.query.app.transaction import TransactionStateManager

        manager = TransactionStateManager()
        manager.on_query_executed("BEGIN")
        assert manager.in_transaction is True
        manager.on_query_executed("COMMIT")
        assert manager.in_transaction is False

    def test_rollback_clears_in_transaction(self):
        """Executing ROLLBACK should set in_transaction=False."""
        from sqlit.domains.query.app.transaction import TransactionStateManager

        manager = TransactionStateManager()
        manager.on_query_executed("BEGIN")
        assert manager.in_transaction is True
        manager.on_query_executed("ROLLBACK")
        assert manager.in_transaction is False

    def test_regular_queries_dont_change_state(self):
        """Regular queries should not change transaction state."""
        from sqlit.domains.query.app.transaction import TransactionStateManager

        manager = TransactionStateManager()

        # Not in transaction - stays not in transaction
        manager.on_query_executed("SELECT * FROM test")
        assert manager.in_transaction is False

        # In transaction - stays in transaction
        manager.on_query_executed("BEGIN")
        manager.on_query_executed("INSERT INTO test VALUES (1)")
        assert manager.in_transaction is True
        manager.on_query_executed("SELECT * FROM test")
        assert manager.in_transaction is True

    def test_commit_without_begin_is_safe(self):
        """COMMIT without BEGIN should not cause error."""
        from sqlit.domains.query.app.transaction import TransactionStateManager

        manager = TransactionStateManager()
        manager.on_query_executed("COMMIT")  # Should not raise
        assert manager.in_transaction is False

    def test_reset_clears_transaction_state(self):
        """reset() should clear transaction state."""
        from sqlit.domains.query.app.transaction import TransactionStateManager

        manager = TransactionStateManager()
        manager.on_query_executed("BEGIN")
        assert manager.in_transaction is True
        manager.reset()
        assert manager.in_transaction is False

    def test_multi_statement_with_begin_sets_transaction(self):
        """Multi-statement query starting with BEGIN should set transaction state."""
        from sqlit.domains.query.app.transaction import TransactionStateManager

        manager = TransactionStateManager()
        manager.on_query_executed("BEGIN; INSERT INTO test VALUES (1);")
        assert manager.in_transaction is True

    def test_multi_statement_ending_with_commit_clears_transaction(self):
        """Multi-statement query ending with COMMIT should clear transaction state."""
        from sqlit.domains.query.app.transaction import TransactionStateManager

        manager = TransactionStateManager()
        manager.on_query_executed("BEGIN")
        manager.on_query_executed("INSERT INTO test VALUES (1); COMMIT;")
        assert manager.in_transaction is False


class TestAtomicBatchExecution:
    """Tests for atomic batch execution (Alt+Enter style)."""

    def test_wrap_in_transaction_adds_begin_commit(self):
        """wrap_in_transaction should add BEGIN and COMMIT."""
        from sqlit.domains.query.app.transaction import wrap_in_transaction

        query = "INSERT INTO test VALUES (1)"
        wrapped = wrap_in_transaction(query)

        assert wrapped.startswith("BEGIN;")
        assert "INSERT INTO test VALUES (1)" in wrapped
        assert wrapped.endswith("COMMIT;") or wrapped.rstrip().endswith("COMMIT;")

    def test_wrap_in_transaction_handles_multiple_statements(self):
        """wrap_in_transaction should handle multiple statements."""
        from sqlit.domains.query.app.transaction import wrap_in_transaction

        query = "INSERT INTO a VALUES (1); INSERT INTO b VALUES (2)"
        wrapped = wrap_in_transaction(query)

        assert "BEGIN" in wrapped
        assert "INSERT INTO a VALUES (1)" in wrapped
        assert "INSERT INTO b VALUES (2)" in wrapped
        assert "COMMIT" in wrapped

    def test_wrap_in_transaction_doesnt_double_wrap(self):
        """wrap_in_transaction should not add BEGIN if already present."""
        from sqlit.domains.query.app.transaction import wrap_in_transaction

        query = "BEGIN; INSERT INTO test VALUES (1); COMMIT;"
        wrapped = wrap_in_transaction(query)

        # Should not have double BEGIN
        assert wrapped.upper().count("BEGIN") == 1
