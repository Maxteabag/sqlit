"""Regression coverage for non-text result values with PyArrow 24+."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from textual.coordinate import Coordinate

from sqlit.domains.shell.app.main import SSMSTUI
from sqlit.shared.ui.widgets_tables import SqlitDataTable

from .mocks import (
    MockConnectionStore,
    MockSettingsStore,
    build_test_services,
    create_test_connection,
)

_INVALID_UTF8_UUID = UUID("a0000000-0000-0000-0000-000000000000")

_INVALID_UTF8_BINARY = b"\x00\x00\x00\x00\x00\x00\x81\xff"
_BINARY_TEXT = "0x00000000000081ff"
_UTF8_JSON_BINARY = b'{"a": 1, "b": [1, 2, 3]}'
_UTF8_JSON_TEXT = '{"a": 1, "b": [1, 2, 3]}'


@pytest.mark.parametrize(
    "value",
    [
        _INVALID_UTF8_BINARY,
        bytearray(_INVALID_UTF8_BINARY),
        memoryview(_INVALID_UTF8_BINARY),
    ],
    ids=["bytes", "bytearray", "memoryview"],
)
def test_binary_column_is_stringified_before_arrow_measurement(value: object) -> None:
    table = SqlitDataTable(
        data={"binary": [value]},
        column_labels=["binary"],
    )

    assert table.backend is not None
    assert table.backend.column_content_widths == [len(_BINARY_TEXT)]
    assert table.get_cell_at(Coordinate(0, 0)) == _BINARY_TEXT


@pytest.mark.parametrize(
    "value",
    [
        _UTF8_JSON_BINARY,
        bytearray(_UTF8_JSON_BINARY),
        memoryview(_UTF8_JSON_BINARY),
    ],
    ids=["bytes", "bytearray", "memoryview"],
)
def test_utf8_binary_column_is_decoded_as_text(value: object) -> None:
    table = SqlitDataTable(
        data={"binary": [value]},
        column_labels=["binary"],
    )

    assert table.backend is not None
    assert table.backend.column_content_widths == [len(_UTF8_JSON_TEXT)]
    assert table.get_cell_at(Coordinate(0, 0)) == _UTF8_JSON_TEXT


def test_incrementally_added_utf8_binary_is_decoded_as_text() -> None:
    table = SqlitDataTable(data={"binary": ["initial"]}, column_labels=["binary"])

    table.add_rows([(_UTF8_JSON_BINARY,)])

    assert table.backend is not None
    assert table.get_cell_at(Coordinate(1, 0)) == _UTF8_JSON_TEXT


def test_incrementally_added_binary_is_stringified() -> None:
    table = SqlitDataTable(data={"binary": ["initial"]}, column_labels=["binary"])

    table.add_rows([(_INVALID_UTF8_BINARY,)])

    assert table.backend is not None
    assert table.backend.column_content_widths == [len(_BINARY_TEXT)]
    assert table.get_cell_at(Coordinate(1, 0)) == _BINARY_TEXT


def test_uuid_column_is_stringified_before_arrow_measurement() -> None:
    table = SqlitDataTable(
        data={"Id": [_INVALID_UTF8_UUID]},
        column_labels=["Id"],
    )

    assert table.backend is not None
    assert table.backend.column_content_widths == [36]
    assert table.get_cell_at(Coordinate(0, 0)) == str(_INVALID_UTF8_UUID)


def test_incrementally_added_uuid_is_stringified() -> None:
    table = SqlitDataTable(data={"Id": ["initial"]}, column_labels=["Id"])

    table.add_rows([(_INVALID_UTF8_UUID,)])

    assert table.backend is not None
    assert table.backend.column_content_widths == [36]
    assert table.get_cell_at(Coordinate(1, 0)) == str(_INVALID_UTF8_UUID)


@pytest.mark.asyncio
async def test_decimal_incremental_backend_stringifies_uuid_column() -> None:
    connection = create_test_connection("test-db", "sqlite")
    services = build_test_services(
        connection_store=MockConnectionStore([connection]),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    app = SSMSTUI(services=services)
    rows = [
        (index, Decimal(f"{index}.25"), _INVALID_UTF8_UUID)
        for index in range(1, 202)
    ]

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await app._display_query_results(
            columns=["id", "amount", "guid"],
            rows=rows,
            row_count=len(rows),
            truncated=False,
            elapsed_ms=0,
        )
        for _ in range(3):
            await pilot.pause(0.05)

        assert app.results_table.row_count == len(rows)
        assert app.results_table.backend is not None
        assert app.results_table.backend.column_content_widths[2] == 36
        assert app.results_table.get_cell_at(Coordinate(0, 2)) == str(
            _INVALID_UTF8_UUID
        )


@pytest.mark.asyncio
async def test_decimal_incremental_backend_stringifies_binary_column() -> None:
    connection = create_test_connection("test-db", "sqlite")
    services = build_test_services(
        connection_store=MockConnectionStore([connection]),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    app = SSMSTUI(services=services)
    rows = [
        (index, Decimal(f"{index}.25"), _INVALID_UTF8_BINARY)
        for index in range(1, 202)
    ]

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await app._display_query_results(
            columns=["id", "amount", "binary"],
            rows=rows,
            row_count=len(rows),
            truncated=False,
            elapsed_ms=0,
        )
        for _ in range(3):
            await pilot.pause(0.05)

        assert app.results_table.row_count == len(rows)
        assert app.results_table.backend is not None
        assert app.results_table.backend.column_content_widths[2] == len(
            _BINARY_TEXT
        )
        assert app.results_table.get_cell_at(Coordinate(0, 2)) == _BINARY_TEXT


@pytest.mark.asyncio
async def test_view_cell_tooltip_does_not_parse_markup() -> None:
    from rich.text import Text

    payload = b'{"path": "[/api/v1]", "tags": ["a", "b"]}'
    connection = create_test_connection("test-db", "sqlite")
    services = build_test_services(
        connection_store=MockConnectionStore([connection]),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    app = SSMSTUI(services=services)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await app._display_query_results(
            columns=["payload"],
            rows=[(payload,)],
            row_count=1,
            truncated=False,
            elapsed_ms=0,
        )
        await pilot.pause(0.05)
        app.results_table.cursor_coordinate = Coordinate(0, 0)
        app.action_view_cell()
        await pilot.pause(0.05)

        tooltip = app.results_table.tooltip
        assert isinstance(tooltip, Text)
        assert tooltip.plain == payload.decode("utf-8")
