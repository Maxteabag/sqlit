"""Unit tests for Oracle adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests.helpers import ConnectionConfig


class TestOracleAdapterRole:
    """Test Oracle adapter handles role/mode parameter correctly."""

    def test_connect_normal_role_no_mode(self):
        """Test that normal role doesn't pass mode parameter."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="testuser",
                password="testpass",
                options={"oracle_role": "normal"},
            )

            adapter.connect(config)

            # Verify connect was called without mode parameter
            mock_oracledb.connect.assert_called_once()
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            assert "mode" not in call_kwargs
            assert call_kwargs["user"] == "testuser"
            assert call_kwargs["password"] == "testpass"
            assert call_kwargs["dsn"] == "localhost:1521/ORCL"

    def test_connect_sysdba_role_passes_mode(self):
        """Test that sysdba role passes AUTH_MODE_SYSDBA."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="sys",
                password="syspass",
                options={"oracle_role": "sysdba"},
            )

            adapter.connect(config)

            # Verify connect was called with mode=AUTH_MODE_SYSDBA
            mock_oracledb.connect.assert_called_once()
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            assert call_kwargs["mode"] == 2  # AUTH_MODE_SYSDBA
            assert call_kwargs["user"] == "sys"
            assert call_kwargs["password"] == "syspass"

    def test_connect_sysoper_role_passes_mode(self):
        """Test that sysoper role passes AUTH_MODE_SYSOPER."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="sys",
                password="syspass",
                options={"oracle_role": "sysoper"},
            )

            adapter.connect(config)

            # Verify connect was called with mode=AUTH_MODE_SYSOPER
            mock_oracledb.connect.assert_called_once()
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            assert call_kwargs["mode"] == 4  # AUTH_MODE_SYSOPER

    def test_connect_default_role_when_not_set(self):
        """Test that missing oracle_role defaults to no mode parameter."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            # Create config without oracle_role (uses default "normal")
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="testuser",
                password="testpass",
            )

            adapter.connect(config)

            # Verify connect was called without mode parameter
            mock_oracledb.connect.assert_called_once()
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            assert "mode" not in call_kwargs


class TestOracleAdapterConnectionType:
    """Test Oracle adapter handles connection type (Service Name vs SID) correctly."""

    def test_connect_service_name_format(self):
        """Test that service_name connection type uses slash separator."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="XEPDB1",
                username="testuser",
                password="testpass",
                options={"oracle_connection_type": "service_name"},
            )

            adapter.connect(config)

            mock_oracledb.connect.assert_called_once()
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            # Service name uses slash separator: host:port/service_name
            assert call_kwargs["dsn"] == "localhost:1521/XEPDB1"

    def test_connect_sid_format(self):
        """Test that sid connection type uses colon separator with oracle_sid field."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                username="testuser",
                password="testpass",
                options={"oracle_connection_type": "sid", "oracle_sid": "ORCL"},
            )

            adapter.connect(config)

            mock_oracledb.connect.assert_called_once()
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            # SID uses colon separator: host:port:sid
            assert call_kwargs["dsn"] == "localhost:1521:ORCL"

    def test_connect_sid_backward_compat_uses_database_field(self):
        """Test that SID falls back to database field for backward compatibility."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            # Old config style: oracle_sid not set, database used instead
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="LEGACY_SID",
                username="testuser",
                password="testpass",
                options={"oracle_connection_type": "sid"},
            )

            adapter.connect(config)

            mock_oracledb.connect.assert_called_once()
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            # Should use database field as fallback
            assert call_kwargs["dsn"] == "localhost:1521:LEGACY_SID"

    def test_connect_default_connection_type_is_service_name(self):
        """Test that missing oracle_connection_type defaults to service_name format."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            # Create config without oracle_connection_type
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="testuser",
                password="testpass",
            )

            adapter.connect(config)

            mock_oracledb.connect.assert_called_once()
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            # Should default to service name format with slash
            assert call_kwargs["dsn"] == "localhost:1521/ORCL"

    def test_connect_sid_with_custom_port(self):
        """Test SID format works with non-default port."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="db.example.com",
                port="1522",
                username="testuser",
                password="testpass",
                options={"oracle_connection_type": "sid", "oracle_sid": "PROD"},
            )

            adapter.connect(config)

            mock_oracledb.connect.assert_called_once()
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            assert call_kwargs["dsn"] == "db.example.com:1522:PROD"
