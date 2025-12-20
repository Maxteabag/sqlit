"""Base test class for parameterized database integration tests.

This module provides a base class with common test cases that can be
parameterized across different database types, reducing test duplication.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class DatabaseTestConfig:
    """Configuration for a database test suite."""

    db_type: str  # e.g., "sqlite", "postgresql"
    display_name: str  # e.g., "SQLite", "PostgreSQL"
    connection_fixture: str  # Name of the connection fixture
    db_fixture: str  # Name of the database fixture
    # Connection creation args (as fixture function)
    create_connection_args: Callable[..., list[str]]
    # Whether this DB uses LIMIT syntax (False for MSSQL TOP, Oracle FETCH FIRST)
    uses_limit: bool = True


class BaseDatabaseTests(ABC):
    """Base class for database integration tests.

    Subclasses must define the `config` class attribute with a DatabaseTestConfig.
    """

    @property
    @abstractmethod
    def config(self) -> DatabaseTestConfig:
        """Return the database test configuration."""
        pass

    def test_list_connections_shows_db(self, request, cli_runner):
        """Test that connection list shows connections correctly."""
        connection = request.getfixturevalue(self.config.connection_fixture)
        result = cli_runner("connection", "list")
        assert result.returncode == 0
        assert connection in result.stdout
        assert self.config.display_name in result.stdout

    def test_query_select(self, request, cli_runner):
        """Test executing SELECT query."""
        connection = request.getfixturevalue(self.config.connection_fixture)
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT * FROM test_users ORDER BY id",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "Bob" in result.stdout
        assert "Charlie" in result.stdout
        assert "3 row(s) returned" in result.stdout

    def test_query_with_where(self, request, cli_runner):
        """Test executing SELECT with WHERE clause."""
        connection = request.getfixturevalue(self.config.connection_fixture)
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT name, email FROM test_users WHERE id = 1",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "alice@example.com" in result.stdout
        assert "1 row(s) returned" in result.stdout

    def test_query_json_format(self, request, cli_runner):
        """Test query output in JSON format."""
        connection = request.getfixturevalue(self.config.connection_fixture)
        # Use --limit for databases that don't support LIMIT syntax
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT id, name FROM test_users ORDER BY id",
            "--format",
            "json",
            "--limit",
            "2",
        )
        assert result.returncode == 0

        # Parse JSON output (row count message goes to stderr, not stdout)
        data = json.loads(result.stdout)

        assert len(data) == 2
        # Oracle returns uppercase column names
        first_name = data[0].get("name") or data[0].get("NAME")
        second_name = data[1].get("name") or data[1].get("NAME")
        assert first_name == "Alice"
        assert second_name == "Bob"

    def test_query_csv_format(self, request, cli_runner):
        """Test query output in CSV format."""
        connection = request.getfixturevalue(self.config.connection_fixture)
        # Use --limit for databases that don't support LIMIT syntax
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT id, name FROM test_users ORDER BY id",
            "--format",
            "csv",
            "--limit",
            "2",
        )
        assert result.returncode == 0
        # Oracle may return uppercase column names
        assert "id,name" in result.stdout.lower()
        assert "Alice" in result.stdout
        assert "Bob" in result.stdout

    def test_query_view(self, request, cli_runner):
        """Test querying a view."""
        connection = request.getfixturevalue(self.config.connection_fixture)
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT * FROM test_user_emails ORDER BY id",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "3 row(s) returned" in result.stdout

    def test_query_aggregate(self, request, cli_runner):
        """Test aggregate query."""
        connection = request.getfixturevalue(self.config.connection_fixture)
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT COUNT(*) as user_count FROM test_users",
        )
        assert result.returncode == 0
        assert "3" in result.stdout

    def test_query_insert(self, request, cli_runner):
        """Test INSERT statement."""
        connection = request.getfixturevalue(self.config.connection_fixture)
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "INSERT INTO test_users (id, name, email) VALUES (4, 'David', 'david@example.com')",
        )
        assert result.returncode == 0

        # Verify the insert
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT * FROM test_users WHERE id = 4",
        )
        assert "David" in result.stdout

    def test_cancellable_query_select(self, request):
        """Test CancellableQuery execution (used by TUI).

        This tests the async query path that the TUI uses, which is different
        from the CLI path tested by other tests.
        """
        from sqlit.config import load_connections
        from sqlit.db.adapters import get_adapter
        from sqlit.services.cancellable import CancellableQuery
        from sqlit.services.query import QueryResult

        # Get the connection fixture name and load the config
        connection_name = request.getfixturevalue(self.config.connection_fixture)
        connections = load_connections()
        config = next((c for c in connections if c.name == connection_name), None)
        assert config is not None, f"Connection {connection_name} not found"

        adapter = get_adapter(self.config.db_type)

        # Test SELECT query through CancellableQuery
        query = CancellableQuery(
            sql="SELECT * FROM test_users ORDER BY id",
            config=config,
            adapter=adapter,
        )
        result = query.execute(max_rows=100)

        assert isinstance(result, QueryResult)
        assert len(result.columns) >= 2  # At least id and name
        assert len(result.rows) == 3
        # Check that Alice is in the first row
        row_values = [str(v) for v in result.rows[0]]
        assert "Alice" in row_values

    def test_cancellable_query_insert(self, request):
        """Test CancellableQuery non-SELECT execution (used by TUI)."""
        from sqlit.config import load_connections
        from sqlit.db.adapters import get_adapter
        from sqlit.services.cancellable import CancellableQuery
        from sqlit.services.query import NonQueryResult

        connection_name = request.getfixturevalue(self.config.connection_fixture)
        connections = load_connections()
        config = next((c for c in connections if c.name == connection_name), None)
        assert config is not None

        adapter = get_adapter(self.config.db_type)

        # Test INSERT through CancellableQuery
        query = CancellableQuery(
            sql="INSERT INTO test_users (id, name, email) VALUES (99, 'CancellableTest', 'cancel@test.com')",
            config=config,
            adapter=adapter,
        )
        result = query.execute()

        assert isinstance(result, NonQueryResult)
        # Some DBs return 1, others return -1 (unknown), both are acceptable
        assert result.rows_affected >= -1

    def test_streaming_csv_output(self, request, cli_runner):
        """Test CSV output works for all adapters including those without cursor support.

        This tests the streaming path in commands.py which needs special handling
        for adapters that don't support cursor-based access.
        """
        connection = request.getfixturevalue(self.config.connection_fixture)
        # No --max-rows to trigger the streaming path for cursor-based adapters
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT id, name FROM test_users ORDER BY id",
            "--format",
            "csv",
        )
        assert result.returncode == 0
        # Oracle may return uppercase column names
        assert "id,name" in result.stdout.lower()
        assert "Alice" in result.stdout

    def test_streaming_json_output(self, request, cli_runner):
        """Test JSON output works for all adapters including those without cursor support."""
        connection = request.getfixturevalue(self.config.connection_fixture)
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT id, name FROM test_users ORDER BY id",
            "--format",
            "json",
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data) == 3
        # Oracle returns uppercase column names
        first_name = data[0].get("name") or data[0].get("NAME")
        assert first_name == "Alice"

    def test_adapter_interface_compliance(self, request):
        """Verify adapter implements required interface without relying on cursor.

        This ensures all database operations go through the adapter abstraction
        rather than directly accessing the connection object.
        """
        from sqlit.db.adapters import get_adapter

        adapter = get_adapter(self.config.db_type)

        # Required methods that should work without cursor
        required_methods = [
            "connect",
            "execute_query",
            "execute_non_query",
            "get_tables",
            "get_views",
            "get_columns",
            "get_databases",
            "get_procedures",
            "quote_identifier",
            "build_select_query",
        ]

        for method_name in required_methods:
            method = getattr(adapter, method_name, None)
            assert method is not None, f"Adapter missing required method: {method_name}"
            assert callable(method), f"Adapter method {method_name} is not callable"

        # Required properties
        required_properties = [
            "name",
            "supports_multiple_databases",
            "supports_stored_procedures",
        ]

        for prop_name in required_properties:
            assert hasattr(adapter, prop_name), f"Adapter missing required property: {prop_name}"

    def test_query_service_execution(self, request):
        """Test QueryService execution path (used by CLI with row limits).

        This tests the standard query execution path through QueryService
        which should use adapter methods.
        """
        from sqlit.config import load_connections
        from sqlit.db.adapters import get_adapter
        from sqlit.services.query import QueryResult, QueryService
        from sqlit.services.session import ConnectionSession

        connection_name = request.getfixturevalue(self.config.connection_fixture)
        connections = load_connections()
        config = next((c for c in connections if c.name == connection_name), None)
        assert config is not None

        service = QueryService()

        # Create a session and execute through QueryService
        with ConnectionSession.create(config, get_adapter) as session:
            result = service.execute(
                connection=session.connection,
                adapter=session.adapter,
                query="SELECT * FROM test_users ORDER BY id",
                config=config,
                max_rows=100,
                save_to_history=False,
            )

            assert isinstance(result, QueryResult)
            assert len(result.rows) == 3
            row_values = [str(v) for v in result.rows[0]]
            assert "Alice" in row_values

    def test_primary_key_detection(self, request):
        """Test that adapter correctly detects primary key columns.

        This tests that get_columns returns ColumnInfo with is_primary_key=True
        for primary key columns. The test_users table has 'id' as PRIMARY KEY.
        """
        from sqlit.config import load_connections
        from sqlit.db.adapters import get_adapter
        from sqlit.services.session import ConnectionSession

        connection_name = request.getfixturevalue(self.config.connection_fixture)
        connections = load_connections()
        config = next((c for c in connections if c.name == connection_name), None)
        assert config is not None, f"Connection {connection_name} not found"

        with ConnectionSession.create(config, get_adapter) as session:
            # Get columns for test_users table (has 'id' as PRIMARY KEY)
            columns = session.adapter.get_columns(
                session.connection,
                "test_users",
                database=config.database if session.adapter.supports_multiple_databases else None,
            )

            assert len(columns) >= 3, f"Expected at least 3 columns, got {len(columns)}"

            # Find the 'id' column (case-insensitive for Oracle which uppercases)
            id_column = next(
                (col for col in columns if col.name.lower() == "id"),
                None,
            )
            assert id_column is not None, f"Column 'id' not found. Columns: {[c.name for c in columns]}"
            assert id_column.is_primary_key, f"Column 'id' should be marked as primary key"

            # Non-PK columns should not be marked as primary key
            non_pk_columns = [col for col in columns if col.name.lower() != "id"]
            for col in non_pk_columns:
                assert not col.is_primary_key, f"Column '{col.name}' should NOT be marked as primary key"

    def test_get_indexes(self, request):
        """Test that adapter correctly retrieves indexes.

        This tests that get_indexes returns IndexInfo objects for indexes
        created on the test tables. The test fixture should create an index
        named 'idx_test_users_email' on the test_users table.
        """
        from sqlit.config import load_connections
        from sqlit.db.adapters import get_adapter
        from sqlit.db.adapters.base import IndexInfo
        from sqlit.services.session import ConnectionSession

        connection_name = request.getfixturevalue(self.config.connection_fixture)
        connections = load_connections()
        config = next((c for c in connections if c.name == connection_name), None)
        assert config is not None, f"Connection {connection_name} not found"

        with ConnectionSession.create(config, get_adapter) as session:
            if not session.adapter.supports_indexes:
                pytest.skip(f"{self.config.display_name} does not support indexes")

            indexes = session.adapter.get_indexes(
                session.connection,
                database=config.database if session.adapter.supports_multiple_databases else None,
            )

            assert isinstance(indexes, list), "get_indexes should return a list"
            # All items should be IndexInfo
            for idx in indexes:
                assert isinstance(idx, IndexInfo), f"Expected IndexInfo, got {type(idx)}"

            # Find our test index (case-insensitive for Oracle)
            test_index = next(
                (idx for idx in indexes if "test_users_email" in idx.name.lower()),
                None,
            )
            assert test_index is not None, (
                f"Index 'idx_test_users_email' not found. "
                f"Found indexes: {[idx.name for idx in indexes]}"
            )
            assert "test_users" in test_index.table_name.lower(), (
                f"Index should be on test_users table, got {test_index.table_name}"
            )

    def test_get_triggers(self, request):
        """Test that adapter correctly retrieves triggers.

        This tests that get_triggers returns TriggerInfo objects for triggers
        created on the test tables. The test fixture should create a trigger
        named 'trg_test_users_audit' on the test_users table.
        """
        from sqlit.config import load_connections
        from sqlit.db.adapters import get_adapter
        from sqlit.db.adapters.base import TriggerInfo
        from sqlit.services.session import ConnectionSession

        connection_name = request.getfixturevalue(self.config.connection_fixture)
        connections = load_connections()
        config = next((c for c in connections if c.name == connection_name), None)
        assert config is not None, f"Connection {connection_name} not found"

        with ConnectionSession.create(config, get_adapter) as session:
            if not session.adapter.supports_triggers:
                pytest.skip(f"{self.config.display_name} does not support triggers")

            triggers = session.adapter.get_triggers(
                session.connection,
                database=config.database if session.adapter.supports_multiple_databases else None,
            )

            assert isinstance(triggers, list), "get_triggers should return a list"
            # All items should be TriggerInfo
            for trg in triggers:
                assert isinstance(trg, TriggerInfo), f"Expected TriggerInfo, got {type(trg)}"

            # Find our test trigger (case-insensitive for Oracle)
            test_trigger = next(
                (trg for trg in triggers if "test_users_audit" in trg.name.lower()),
                None,
            )
            assert test_trigger is not None, (
                f"Trigger 'trg_test_users_audit' not found. "
                f"Found triggers: {[trg.name for trg in triggers]}"
            )
            assert "test_users" in test_trigger.table_name.lower(), (
                f"Trigger should be on test_users table, got {test_trigger.table_name}"
            )

    def test_get_sequences(self, request):
        """Test that adapter correctly retrieves sequences.

        This tests that get_sequences returns SequenceInfo objects for sequences
        created in the database. The test fixture should create a sequence
        named 'test_sequence' (for databases that support sequences).
        """
        from sqlit.config import load_connections
        from sqlit.db.adapters import get_adapter
        from sqlit.db.adapters.base import SequenceInfo
        from sqlit.services.session import ConnectionSession

        connection_name = request.getfixturevalue(self.config.connection_fixture)
        connections = load_connections()
        config = next((c for c in connections if c.name == connection_name), None)
        assert config is not None, f"Connection {connection_name} not found"

        with ConnectionSession.create(config, get_adapter) as session:
            if not session.adapter.supports_sequences:
                pytest.skip(f"{self.config.display_name} does not support sequences")

            sequences = session.adapter.get_sequences(
                session.connection,
                database=config.database if session.adapter.supports_multiple_databases else None,
            )

            assert isinstance(sequences, list), "get_sequences should return a list"
            # All items should be SequenceInfo
            for seq in sequences:
                assert isinstance(seq, SequenceInfo), f"Expected SequenceInfo, got {type(seq)}"

            # Find our test sequence (case-insensitive for Oracle)
            test_sequence = next(
                (seq for seq in sequences if "test_sequence" in seq.name.lower()),
                None,
            )
            assert test_sequence is not None, (
                f"Sequence 'test_sequence' not found. "
                f"Found sequences: {[seq.name for seq in sequences]}"
            )


class BaseDatabaseTestsWithLimit(BaseDatabaseTests):
    """Base tests for databases that support LIMIT syntax."""

    def test_query_limit(self, request, cli_runner):
        """Test query with LIMIT clause."""
        connection = request.getfixturevalue(self.config.connection_fixture)
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT * FROM test_users ORDER BY id LIMIT 2",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "Bob" in result.stdout
        assert "2 row(s) returned" in result.stdout
