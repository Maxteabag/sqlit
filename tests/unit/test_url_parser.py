"""Unit tests for connection URL parsing."""

from __future__ import annotations

import pytest

from sqlit.domains.connections.app.url_parser import parse_connection_url


def test_postgres_url_allows_empty_host() -> None:
    config = parse_connection_url("postgresql:///mydb", name="LocalPG")
    endpoint = config.tcp_endpoint

    assert endpoint is not None
    assert endpoint.host == ""
    assert endpoint.database == "mydb"


def test_mysql_url_requires_host() -> None:
    with pytest.raises(ValueError, match="No host specified"):
        parse_connection_url("mysql:///mydb", name="LocalMySQL")
