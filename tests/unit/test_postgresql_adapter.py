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


def test_postgresql_uses_custom_port_when_server_left_blank() -> None:
    """Regression test for issue #205.

    A user pointed sqlit at a docker Postgres on 127.0.0.1:5433. They left
    the Server field blank (its placeholder says 'localhost') and set the
    Port field to 5433. libpq then reported it couldn't reach
    /run/postgresql/.s.PGSQL.5432 — i.e. neither host nor port made it
    through.

    Expected: with a port set, the adapter must pass both port=5433 and
    a sensible host (localhost, matching the form placeholder) to
    psycopg2.connect so the connection actually reaches the docker
    container.
    """
    mock_psycopg2 = MagicMock()
    with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
        from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter

        adapter = PostgreSQLAdapter()
        config = ConnectionConfig(
            name="timescale",
            db_type="postgresql",
            server="",          # blank — UI placeholder says "localhost"
            port="5433",        # user explicitly chose 5433
            database="postgres",
            username="postgres",
            password="password",
        )

        adapter.connect(config)

        kwargs = mock_psycopg2.connect.call_args.kwargs
        assert kwargs.get("port") == 5433, (
            "port=5433 must reach psycopg2.connect, but the adapter "
            f"silently drops it when server is blank. kwargs={kwargs!r}"
        )
        assert kwargs.get("host") == "localhost", (
            "blank server must default to 'localhost' (matching the "
            f"connection form placeholder). kwargs={kwargs!r}"
        )
