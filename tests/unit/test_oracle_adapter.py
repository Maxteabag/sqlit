"""Unit tests for Oracle adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

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

    def test_connect_tcps_with_easy_connect_parameters(self):
        """Issue #261: protocol and parameters must be included in the DSN."""
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
                database="service-name.com",
                username="testuser",
                password="testpass",
                options={
                    "oracle_connection_type": "service_name",
                    "oracle_protocol": "tcps",
                    "oracle_easy_connect_parameters": (
                        "ssl_server_dn_match=no&retry_count=3"
                    ),
                },
            )

            adapter.connect(config)

            call_kwargs = mock_oracledb.connect.call_args.kwargs
            assert call_kwargs["dsn"] == (
                "tcps://localhost:1521/service-name.com"
                "?ssl_server_dn_match=no&retry_count=3"
            )

    def test_connect_easy_connect_parameters_accept_leading_question_mark(self):
        """Users may paste Easy Connect parameters with their separator."""
        mock_oracledb = MagicMock()

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="XEPDB1",
                username="testuser",
                password="testpass",
                options={"oracle_easy_connect_parameters": "?expire_time=2"},
            )

            OracleAdapter().connect(config)

            assert mock_oracledb.connect.call_args.kwargs["dsn"] == (
                "localhost:1521/XEPDB1?expire_time=2"
            )

    def test_connect_rejects_unknown_oracle_protocol(self):
        """Configs outside the schema must not silently discard bad protocols."""
        mock_oracledb = MagicMock()

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="XEPDB1",
                username="testuser",
                password="testpass",
                options={"oracle_protocol": "udp"},
            )

            with pytest.raises(ValueError, match="Default, TCP, or TCPS"):
                OracleAdapter().connect(config)

            mock_oracledb.connect.assert_not_called()

    def test_connect_sid_ignores_easy_connect_options(self):
        """Easy Connect protocol and parameters do not apply to SID descriptors."""
        mock_oracledb = MagicMock()

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                username="testuser",
                password="testpass",
                options={
                    "oracle_connection_type": "sid",
                    "oracle_sid": "ORCL",
                    "oracle_protocol": "tcps",
                    "oracle_easy_connect_parameters": "ssl_server_dn_match=no",
                },
            )

            OracleAdapter().connect(config)

            mock_oracledb.makedsn.assert_called_once_with("localhost", 1521, sid="ORCL")
            assert mock_oracledb.connect.call_args.kwargs["dsn"] is (
                mock_oracledb.makedsn.return_value
            )

    def test_tcps_easy_connect_dsn_parses_in_real_driver(self):
        """The issue #261 DSN must be accepted by python-oracledb itself."""
        oracledb = pytest.importorskip("oracledb")
        params = oracledb.ConnectParams()

        params.parse_connect_string(
            "tcps://localhost:1521/service-name.com?ssl_server_dn_match=no"
        )

        assert params.protocol == "tcps"
        assert params.host == "localhost"
        assert params.port == 1521
        assert params.service_name == "service-name.com"
        assert params.ssl_server_dn_match is False

    def test_connect_sid_format(self):
        """SID connection type must go through oracledb.makedsn — see issue #106.

        The legacy host:port:SID Easy-Connect form is rejected by thin-mode with
        DPY-4027, so the adapter must use makedsn to emit a TNS descriptor.
        """
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

            mock_oracledb.makedsn.assert_called_once_with("localhost", 1521, sid="ORCL")
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            assert call_kwargs["dsn"] is mock_oracledb.makedsn.return_value

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

            mock_oracledb.makedsn.assert_called_once_with("localhost", 1521, sid="LEGACY_SID")

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

            mock_oracledb.makedsn.assert_called_once_with("db.example.com", 1522, sid="PROD")

    def test_sid_dsn_parses_in_real_driver(self):
        """Issue #106 regression: adapter must produce a DSN that thin-mode accepts.

        Calls the adapter against a port that is guaranteed closed so the driver
        is forced to parse the DSN but cannot complete a network connection.
        If parsing fails (DPY-4027), we've regressed.
        """
        oracledb = pytest.importorskip("oracledb")

        from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

        adapter = OracleAdapter()
        config = ConnectionConfig(
            name="test",
            db_type="oracle",
            server="127.0.0.1",
            port="1",  # reserved port — guaranteed no Oracle listener
            username="x",
            password="x",
            options={"oracle_connection_type": "sid", "oracle_sid": "FREE"},
        )

        with pytest.raises(oracledb.DatabaseError) as exc_info:
            adapter.connect(config)

        message = str(exc_info.value)
        assert "DPY-4027" not in message, (
            f"issue #106 regression: SID DSN rejected at parse step: {message}"
        )
