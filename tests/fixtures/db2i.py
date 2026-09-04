"""IBM DB2 for i fixtures."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig

# Environment variables for DB2 for i connection
DB2I_HOST = os.environ.get("DB2I_HOST", "localhost")
DB2I_PORT = os.environ.get("DB2I_PORT", "")  # Optional port
DB2I_USER = os.environ.get("DB2I_USER", "QSECOFR")
DB2I_PASSWORD = os.environ.get("DB2I_PASSWORD", "password")
DB2I_LIBRARY = os.environ.get("DB2I_LIBRARY", "QGPL")  # Default library
DB2I_ODBC_DRIVER = os.environ.get("DB2I_ODBC_DRIVER", "IBM i Access ODBC Driver")


@pytest.fixture
def db2i_connection(cli_runner):
    """Create a DB2 for i connection configuration."""
    from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint

    config = ConnectionConfig(
        name="db2i_test",
        db_type="db2i",
        tcp_endpoint=TcpEndpoint(
            host=DB2I_HOST,
            port=DB2I_PORT if DB2I_PORT else None,
            database=DB2I_LIBRARY,
            username=DB2I_USER,
            password=DB2I_PASSWORD,
        ),
        extra_options={"odbc_driver": DB2I_ODBC_DRIVER} if DB2I_ODBC_DRIVER else {},
    )
    return config


@pytest.fixture
def db2i_db(db2i_connection):
    """Return the DB2 for i database/library name."""
    return DB2I_LIBRARY
