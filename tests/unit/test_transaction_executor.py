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
        self.configs: list[ConnectionConfig] = []

    def connect(self, config: ConnectionConfig) -> FakeConnection:
        self.configs.append(config)
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


class FakeTunnel:
    local_bind_port = 40123

    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def _ssh_config() -> ConnectionConfig:
    return ConnectionConfig.from_dict(
        {
            "name": "ssh",
            "db_type": "postgresql",
            "server": "db.internal.example",
            "port": "5432",
            "ssh_enabled": True,
            "ssh_host": "bastion",
            "ssh_username": "me",
        }
    )


def _endpoints(provider: FakeProvider) -> list[tuple[str, str]]:
    return [(c.tcp_endpoint.host, c.tcp_endpoint.port) for c in provider.connection_factory.configs]


def test_ssh_executor_reuses_session_tunnel_for_every_path() -> None:
    """Regression #337: transaction paths connected to the private DB host, bypassing the tunnel."""
    provider = FakeProvider()
    tunnel = FakeTunnel()
    executor = TransactionExecutor(_ssh_config(), provider, tunnel=tunnel)

    executor.execute("SELECT 1")
    executor.execute("BEGIN")
    executor.execute("SELECT 2")
    executor.execute("COMMIT")
    executor.atomic_execute("SET x = 1; SELECT 3")
    executor.close()

    assert _endpoints(provider) == [("127.0.0.1", "40123")] * 3
    assert tunnel.stopped is False  # the session owns it


def test_ssh_executor_without_session_tunnel_opens_and_stops_its_own(monkeypatch) -> None:
    created: list[FakeTunnel] = []

    def fake_create_ssh_tunnel(config: ConnectionConfig):
        tunnel = FakeTunnel()
        created.append(tunnel)
        return tunnel, "127.0.0.1", tunnel.local_bind_port

    monkeypatch.setattr("sqlit.domains.connections.app.tunnel.create_ssh_tunnel", fake_create_ssh_tunnel)
    provider = FakeProvider()
    executor = TransactionExecutor(_ssh_config(), provider)

    executor.execute("SELECT 1")
    executor.atomic_execute("SELECT 2")
    executor.close()

    assert _endpoints(provider) == [("127.0.0.1", "40123")] * 2
    assert len(created) == 1 and created[0].stopped


def test_executor_without_ssh_connects_to_configured_host() -> None:
    provider = FakeProvider()
    config = ConnectionConfig.from_dict({"name": "direct", "db_type": "postgresql", "server": "db", "port": "5432"})
    TransactionExecutor(config, provider).execute("SELECT 1")
    assert _endpoints(provider) == [("db", "5432")]
