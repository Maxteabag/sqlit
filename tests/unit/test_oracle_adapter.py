"""Unit tests for Oracle adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sqlit.config import ConnectionConfig


class TestOracleAdapterRole:
    """Test Oracle adapter handles role/mode parameter correctly."""

    def test_connect_normal_role_no_mode(self):
        """Test that normal role doesn't pass mode parameter."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.db.adapters.oracle import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="testuser",
                password="testpass",
                oracle_role="normal",
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
            from sqlit.db.adapters.oracle import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="sys",
                password="syspass",
                oracle_role="sysdba",
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
            from sqlit.db.adapters.oracle import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="sys",
                password="syspass",
                oracle_role="sysoper",
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
            from sqlit.db.adapters.oracle import OracleAdapter

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
