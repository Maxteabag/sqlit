"""Regression coverage for PostgreSQL temporal values outside Python's range."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timezone
from typing import Any

import pytest

from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter
from tests.fixtures.postgres import (
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)
from tests.helpers import ConnectionConfig

pytestmark = [pytest.mark.integration, pytest.mark.postgresql]


@pytest.fixture
def postgres_adapter_connection(
    postgres_db: str,
) -> Generator[tuple[PostgreSQLAdapter, Any], None, None]:
    """Connect through sqlit's PostgreSQL adapter so its type handling is exercised."""
    adapter = PostgreSQLAdapter()
    config = ConnectionConfig(
        name="issue-263",
        db_type="postgresql",
        server=POSTGRES_HOST,
        port=str(POSTGRES_PORT),
        database=postgres_db,
        username=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )
    connection = adapter.connect(config)
    try:
        yield adapter, connection
    finally:
        adapter.disconnect(connection)


def test_postgresql_column_named_year_is_queryable(
    postgres_adapter_connection: tuple[PostgreSQLAdapter, Any],
) -> None:
    """Prove the identifier reported in issue #263 is not itself the failure."""
    adapter, connection = postgres_adapter_connection

    columns, rows, truncated = adapter.execute_query(connection, "SELECT -1 AS year")

    assert columns == ["year"]
    assert rows == [(-1,)]
    assert truncated is False


def test_postgresql_supported_temporal_values_remain_typed(
    postgres_adapter_connection: tuple[PostgreSQLAdapter, Any],
) -> None:
    """A BC-date fallback must not stringify dates Python can represent."""
    adapter, connection = postgres_adapter_connection

    columns, rows, truncated = adapter.execute_query(
        connection,
        """
        SELECT
            DATE '2024-02-03' AS supported_date,
            TIMESTAMP '2024-02-03 04:05:06' AS supported_timestamp,
            TIMESTAMPTZ '2024-02-03 04:05:06+00' AS supported_timestamptz
        """,
    )

    assert columns == ["supported_date", "supported_timestamp", "supported_timestamptz"]
    assert rows == [
        (
            date(2024, 2, 3),
            datetime(2024, 2, 3, 4, 5, 6),
            datetime(2024, 2, 3, 4, 5, 6, tzinfo=timezone.utc),
        )
    ]
    assert truncated is False


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("DATE '0001-01-01 BC'", "0001-01-01 BC"),
        ("TIMESTAMP '0001-01-01 00:00:00 BC'", "0001-01-01 00:00:00 BC"),
        (
            "TIMESTAMPTZ '0001-01-01 00:00:00+00 BC'",
            "0001-01-01 00:00:00+00 BC",
        ),
        (
            "ARRAY[DATE '2024-02-03', DATE '0001-01-01 BC']",
            [date(2024, 2, 3), "0001-01-01 BC"],
        ),
        (
            "ARRAY["
            "TIMESTAMP '2024-02-03 04:05:06', "
            "TIMESTAMP '0001-01-01 00:00:00 BC'"
            "]",
            [datetime(2024, 2, 3, 4, 5, 6), "0001-01-01 00:00:00 BC"],
        ),
        (
            "ARRAY["
            "TIMESTAMPTZ '2024-02-03 04:05:06+00', "
            "TIMESTAMPTZ '0001-01-01 00:00:00+00 BC'"
            "]",
            [
                datetime(2024, 2, 3, 4, 5, 6, tzinfo=timezone.utc),
                "0001-01-01 00:00:00+00 BC",
            ],
        ),
    ],
)
def test_postgresql_bc_temporal_values_fall_back_to_text(
    postgres_adapter_connection: tuple[PostgreSQLAdapter, Any],
    expression: str,
    expected: object,
) -> None:
    """PostgreSQL values Python cannot represent should still be displayable."""
    adapter, connection = postgres_adapter_connection

    columns, rows, truncated = adapter.execute_query(
        connection,
        f"SELECT {expression} AS year",
    )

    assert columns == ["year"]
    assert rows == [(expected,)]
    assert truncated is False
