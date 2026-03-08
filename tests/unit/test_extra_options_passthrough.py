"""Unit tests for extra_options pass-through to drivers.

This verifies the fix for GitHub issue #108 where users couldn't pass
custom properties to underlying database drivers.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestExtraOptionsPassthrough:
    """Test that extra_options are passed through to drivers."""

    def test_snowflake_passes_extra_options(self):
        """Test Snowflake adapter passes extra_options to driver."""
        from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint
        from sqlit.domains.connections.providers.snowflake.adapter import SnowflakeAdapter

        mock_sf = MagicMock()
        mock_conn = MagicMock()
        mock_sf.connect.return_value = mock_conn

        with patch.dict("sys.modules", {"snowflake.connector": mock_sf}):
            adapter = SnowflakeAdapter()
            config = ConnectionConfig(
                name="test_sf",
                db_type="snowflake",
                endpoint=TcpEndpoint(
                    host="account.snowflakecomputing.com",
                    username="user",
                    password="pass",
                    database="db",
                ),
                extra_options={
                    "authenticator": "externalbrowser",
                    "custom_option": "custom_value",
                },
            )

            adapter.connect(config)

            # Verify extra_options were passed to connect
            call_kwargs = mock_sf.connect.call_args[1]
            assert call_kwargs.get("authenticator") == "externalbrowser"
            assert call_kwargs.get("custom_option") == "custom_value"

    def test_snowflake_jwt_auth_options(self):
        """Test Snowflake JWT authentication options are passed."""
        from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint
        from sqlit.domains.connections.providers.snowflake.adapter import SnowflakeAdapter

        mock_sf = MagicMock()
        mock_conn = MagicMock()
        mock_sf.connect.return_value = mock_conn

        with patch.dict("sys.modules", {"snowflake.connector": mock_sf}):
            adapter = SnowflakeAdapter()
            config = ConnectionConfig(
                name="test_sf_jwt",
                db_type="snowflake",
                endpoint=TcpEndpoint(
                    host="account.snowflakecomputing.com",
                    username="user",
                    database="db",
                ),
                options={
                    "authenticator": "snowflake_jwt",
                    "private_key_file": "/path/to/key.p8",
                    "private_key_file_pwd": "secret",
                },
            )

            adapter.connect(config)

            call_kwargs = mock_sf.connect.call_args[1]
            assert call_kwargs.get("authenticator") == "snowflake_jwt"
            assert call_kwargs.get("private_key_file") == "/path/to/key.p8"
            assert call_kwargs.get("private_key_file_pwd") == "secret"

    def test_postgresql_passes_extra_options(self):
        """Test PostgreSQL adapter passes extra_options to driver."""
        from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint
        from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter

        mock_psycopg2 = MagicMock()
        mock_conn = MagicMock()
        mock_conn.autocommit = False
        mock_psycopg2.connect.return_value = mock_conn

        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
            adapter = PostgreSQLAdapter()
            config = ConnectionConfig(
                name="test_pg",
                db_type="postgresql",
                endpoint=TcpEndpoint(
                    host="localhost",
                    port="5432",
                    username="user",
                    password="pass",
                    database="db",
                ),
                extra_options={
                    "application_name": "my_app",
                    "connect_timeout": "30",
                },
            )

            adapter.connect(config)

            call_kwargs = mock_psycopg2.connect.call_args[1]
            assert call_kwargs.get("application_name") == "my_app"
            assert call_kwargs.get("connect_timeout") == "30"

    def test_mysql_passes_extra_options(self):
        """Test MySQL adapter passes extra_options to driver."""
        from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint
        from sqlit.domains.connections.providers.mysql.adapter import MySQLAdapter

        mock_pymysql = MagicMock()
        mock_conn = MagicMock()
        mock_pymysql.connect.return_value = mock_conn

        with patch.dict("sys.modules", {"pymysql": mock_pymysql}):
            adapter = MySQLAdapter()
            config = ConnectionConfig(
                name="test_mysql",
                db_type="mysql",
                endpoint=TcpEndpoint(
                    host="localhost",
                    port="3306",
                    username="user",
                    password="pass",
                    database="db",
                ),
                extra_options={
                    "charset": "utf8mb4",
                    "init_command": "SET NAMES utf8mb4",
                },
            )

            adapter.connect(config)

            call_kwargs = mock_pymysql.connect.call_args[1]
            assert call_kwargs.get("charset") == "utf8mb4"
            assert call_kwargs.get("init_command") == "SET NAMES utf8mb4"


class TestSnowflakeAuthSchema:
    """Test Snowflake authentication schema options."""

    def test_snowflake_schema_has_auth_dropdown(self):
        """Test Snowflake schema includes authentication dropdown."""
        from sqlit.domains.connections.providers.snowflake.schema import SCHEMA

        auth_field = None
        for field in SCHEMA.fields:
            if field.name == "authenticator":
                auth_field = field
                break

        assert auth_field is not None, "Snowflake schema should have authenticator field"
        assert len(auth_field.options) == 4
        auth_values = [opt.value for opt in auth_field.options]
        assert "default" in auth_values
        assert "externalbrowser" in auth_values
        assert "snowflake_jwt" in auth_values
        assert "oauth" in auth_values

    def test_snowflake_schema_has_private_key_fields(self):
        """Test Snowflake schema includes private key fields for JWT auth."""
        from sqlit.domains.connections.providers.snowflake.schema import SCHEMA

        field_names = [f.name for f in SCHEMA.fields]
        assert "private_key_file" in field_names
        assert "private_key_file_pwd" in field_names
