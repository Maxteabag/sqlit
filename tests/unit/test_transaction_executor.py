"""Tests for TransactionExecutor connection handling."""

from __future__ import annotations

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.query.app.transaction import TransactionExecutor


class FakeConnection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeConnectionFactory:
    def __init__(self) -> None:
        self.created: list[FakeConnection] = []

    def connect(self, config: ConnectionConfig) -> FakeConnection:
        conn = FakeConnection(f"conn-{len(self.created)}")
        self.created.append(conn)
        return conn


class FakeQueryExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, FakeConnection, str]] = []

    def execute_query(self, conn: FakeConnection, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        self.calls.append(("query", conn, query))
        return [], [], False

    def execute_non_query(self, conn: FakeConnection, query: str) -> int:
        self.calls.append(("non_query", conn, query))
        return 0


class FakeProvider:
    def __init__(self) -> None:
        self.connection_factory = FakeConnectionFactory()
        self.query_executor = FakeQueryExecutor()
        self.post_connect = lambda conn, config: None


def _make_executor() -> tuple[TransactionExecutor, FakeProvider]:
    config = ConnectionConfig(name="Test", db_type="sqlite")
    provider = FakeProvider()
    return TransactionExecutor(config, provider), provider


def test_execute_begin_mid_batch_persists_connection() -> None:
    executor, provider = _make_executor()

    executor.execute("INSERT INTO test VALUES (1); BEGIN")

    assert executor.in_transaction is True
    assert len(provider.connection_factory.created) == 1
    assert executor._transaction_connection is provider.connection_factory.created[0]
    assert provider.connection_factory.created[0].closed is False

    executor.execute("INSERT INTO test VALUES (2)")

    assert len(provider.connection_factory.created) == 1
    assert provider.query_executor.calls[-1][1] is provider.connection_factory.created[0]


def test_execute_begin_commit_closes_connection() -> None:
    executor, provider = _make_executor()

    executor.execute("BEGIN; INSERT INTO test VALUES (1); COMMIT")

    assert executor.in_transaction is False
    assert executor._transaction_connection is None
    assert len(provider.connection_factory.created) == 1
    assert provider.connection_factory.created[0].closed is True
