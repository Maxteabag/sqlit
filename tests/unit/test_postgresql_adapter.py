"""Unit tests for PostgreSQL adapter behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests.helpers import ConnectionConfig


def test_postgresql_peer_auth_omits_empty_tcp_args() -> None:
    mock_psycopg2 = MagicMock()
    with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
        from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter

        adapter = PostgreSQLAdapter()
        config = ConnectionConfig(
            name="pg",
            db_type="postgresql",
            server="",
            port="",
            database="mydb",
            username="",
            password=None,
        )

        adapter.connect(config)

        kwargs = mock_psycopg2.connect.call_args.kwargs

        assert kwargs["database"] == "mydb"
        assert "host" not in kwargs
        assert "port" not in kwargs
        assert "user" not in kwargs
        assert "password" not in kwargs
