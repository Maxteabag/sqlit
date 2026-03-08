"""Unit tests for TLS adapter options."""

from __future__ import annotations

import ssl
from unittest.mock import MagicMock, patch

from tests.helpers import ConnectionConfig


def test_postgresql_tls_args_include_files():
    mock_psycopg2 = MagicMock()
    with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
        from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter

        adapter = PostgreSQLAdapter()
        config = ConnectionConfig(
            name="pg",
            db_type="postgresql",
            server="db.example.com",
            port="5432",
            database="postgres",
            username="user",
            password="pass",
            options={
                "tls_mode": "verify-full",
                "tls_ca": "/ca.pem",
                "tls_cert": "/client.pem",
                "tls_key": "/client.key",
                "tls_key_password": "secret",
            },
        )

        adapter.connect(config)

        kwargs = mock_psycopg2.connect.call_args.kwargs
        assert kwargs["sslmode"] == "verify-full"
        assert kwargs["sslrootcert"] == "/ca.pem"
        assert kwargs["sslcert"] == "/client.pem"
        assert kwargs["sslkey"] == "/client.key"
        assert kwargs["sslpassword"] == "secret"


def test_cockroachdb_defaults_to_insecure_without_tls():
    mock_psycopg2 = MagicMock()
    with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
        from sqlit.domains.connections.providers.cockroachdb.adapter import CockroachDBAdapter

        adapter = CockroachDBAdapter()
        config = ConnectionConfig(
            name="crdb",
            db_type="cockroachdb",
            server="localhost",
            port="26257",
            database="defaultdb",
            username="root",
            password="",
        )

        adapter.connect(config)

        kwargs = mock_psycopg2.connect.call_args.kwargs
        assert kwargs["sslmode"] == "disable"


def test_mysql_tls_builds_ssl_dict():
    mock_pymysql = MagicMock()
    with patch.dict("sys.modules", {"pymysql": mock_pymysql}):
        from sqlit.domains.connections.providers.mysql.adapter import MySQLAdapter

        adapter = MySQLAdapter()
        config = ConnectionConfig(
            name="mysql",
            db_type="mysql",
            server="db.example.com",
            port="3306",
            database="app",
            username="user",
            password="pass",
            options={
                "tls_mode": "verify-full",
                "tls_ca": "/ca.pem",
                "tls_cert": "/client.pem",
                "tls_key": "/client.key",
            },
        )

        adapter.connect(config)

        kwargs = mock_pymysql.connect.call_args.kwargs
        assert kwargs["ssl"]["ca"] == "/ca.pem"
        assert kwargs["ssl"]["cert"] == "/client.pem"
        assert kwargs["ssl"]["key"] == "/client.key"
        assert kwargs["ssl"]["cert_reqs"] == ssl.CERT_REQUIRED
        assert kwargs["ssl"]["check_hostname"] is True


def test_mssql_tls_flags_in_connection_string():
    from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

    adapter = SQLServerAdapter()
    config = ConnectionConfig(
        name="mssql",
        db_type="mssql",
        server="localhost",
        port="1433",
        database="master",
        username="sa",
        password="secret",
        options={
            "auth_type": "sql",
            "tls_mode": "verify-full",
            "tls_trust_server_certificate": "no",
        },
    )

    conn_str = adapter.build_connection_string(config)
    assert "Encrypt=yes;" in conn_str
    assert "TrustServerCertificate=no;" in conn_str
