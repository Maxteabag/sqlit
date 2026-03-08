"""Unit tests for MSSQL autocommit behavior.

Regression test for GitHub issue #107:
CREATE DATABASE was failing with "CREATE DATABASE statement not allowed within
multi-statement transaction" because the MSSQL adapter didn't set autocommit=True.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestMSSQLAutocommitBehavior:
    """Test that MSSQL adapter sets autocommit correctly."""

    @pytest.fixture
    def mock_mssql_python(self):
        """Create a mock mssql_python module."""
        mock_module = MagicMock()
        mock_conn = MagicMock()
        mock_conn.autocommit = False  # Default behavior
        mock_module.connect.return_value = mock_conn
        with patch.dict("sys.modules", {"mssql_python": mock_module}):
            yield mock_module, mock_conn

    def test_mssql_adapter_sets_autocommit(self, mock_mssql_python):
        """Regression test: MSSQL adapter must set autocommit=True.

        This prevents 'CREATE DATABASE statement not allowed within
        multi-statement transaction' errors (GitHub issue #107).
        """
        from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

        _, mock_conn = mock_mssql_python

        adapter = SQLServerAdapter()
        config = ConnectionConfig(
            name="test_mssql",
            db_type="mssql",
            endpoint=TcpEndpoint(
                host="localhost",
                port="1433",
                database="master",
                username="sa",
                password="password",
            ),
            options={"auth_type": "sql"},
        )

        adapter.connect(config)

        assert mock_conn.autocommit is True, (
            "MSSQL adapter must set autocommit=True after connecting "
            "to allow DDL statements like CREATE DATABASE"
        )
