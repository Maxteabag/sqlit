"""Performance tests for rendering large datasets in the DataTable.

These tests measure how the UI performs with varying row counts.
Run with: pytest tests/performance/ -v --benchmark-only
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import pytest

try:
    from faker import Faker
except ImportError:
    Faker = None  # type: ignore

from sqlit.app import SSMSTUI
from sqlit.config import ConnectionConfig

from ..ui.mocks import MockConnectionStore, MockSettingsStore, create_test_connection


# Skip all tests if Faker not installed
pytestmark = pytest.mark.skipif(Faker is None, reason="Faker not installed (pip install Faker)")


class FakeDataGenerator:
    """Generates realistic fake data for testing."""

    def __init__(self, seed: int = 42):
        self.fake = Faker()
        Faker.seed(seed)  # Reproducible data

    def generate_user_rows(self, count: int) -> tuple[list[str], list[tuple]]:
        """Generate fake user data rows.

        Returns:
            Tuple of (columns, rows)
        """
        columns = ["id", "name", "email", "phone", "address", "created_at"]
        rows = []
        for i in range(count):
            rows.append((
                i + 1,
                self.fake.name(),
                self.fake.email(),
                self.fake.phone_number(),
                self.fake.address().replace("\n", ", "),
                self.fake.date_time().isoformat(),
            ))
        return columns, rows

    def generate_product_rows(self, count: int) -> tuple[list[str], list[tuple]]:
        """Generate fake product data rows."""
        columns = ["id", "sku", "name", "description", "price", "stock", "category"]
        rows = []
        for i in range(count):
            rows.append((
                i + 1,
                self.fake.bothify(text="???-####"),
                self.fake.catch_phrase(),
                self.fake.text(max_nb_chars=100),
                round(self.fake.pyfloat(min_value=1, max_value=9999, right_digits=2), 2),
                self.fake.random_int(min=0, max=1000),
                self.fake.word(),
            ))
        return columns, rows

    def generate_transaction_rows(self, count: int) -> tuple[list[str], list[tuple]]:
        """Generate fake transaction/log data rows."""
        columns = ["id", "timestamp", "user_id", "action", "ip_address", "user_agent", "status"]
        statuses = ["success", "failure", "pending", "cancelled"]
        actions = ["login", "logout", "purchase", "view", "update", "delete", "create"]
        rows = []
        for i in range(count):
            rows.append((
                i + 1,
                self.fake.date_time().isoformat(),
                self.fake.random_int(min=1, max=10000),
                self.fake.random_element(actions),
                self.fake.ipv4(),
                self.fake.user_agent()[:80],  # Truncate long user agents
                self.fake.random_element(statuses),
            ))
        return columns, rows


@pytest.fixture
def fake_data():
    """Fixture providing fake data generator."""
    return FakeDataGenerator(seed=42)


@pytest.fixture
def mock_app_context():
    """Context manager for mocked app environment."""
    connections = [create_test_connection("perf-test", "sqlite")]
    mock_connections = MockConnectionStore(connections)
    mock_settings = MockSettingsStore({"theme": "tokyo-night"})

    return patch.multiple(
        "sqlit.config",
        load_connections=mock_connections.load_all,
        load_settings=mock_settings.load_all,
        save_settings=mock_settings.save_all,
    )


class TestDataTableRenderingPerformance:
    """Tests measuring DataTable rendering performance with large datasets."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("row_count", [100, 1000, 5000, 10000])
    async def test_render_rows_timing(self, fake_data: FakeDataGenerator, row_count: int, mock_app_context):
        """Measure time to render varying numbers of rows."""
        columns, rows = fake_data.generate_user_rows(row_count)

        with mock_app_context:
            app = SSMSTUI()

            async with app.run_test(size=(120, 50)) as pilot:
                await pilot.pause()

                # Measure rendering time
                start_time = time.perf_counter()

                # Directly call the display method (bypassing actual query execution)
                app._display_query_results(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    truncated=False,
                    elapsed_ms=0,
                )

                await pilot.pause()
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                # Verify rows were added
                assert app.results_table.row_count == row_count

                # Log performance (visible in pytest output with -v)
                print(f"\n  Rendered {row_count} rows in {elapsed_ms:.2f}ms")

                # Performance assertions (adjust thresholds as needed)
                if row_count <= 1000:
                    assert elapsed_ms < 5000, f"Rendering {row_count} rows took too long: {elapsed_ms:.2f}ms"
                elif row_count <= 5000:
                    assert elapsed_ms < 15000, f"Rendering {row_count} rows took too long: {elapsed_ms:.2f}ms"
                else:
                    # 10k rows - just log, don't fail (we're testing limits)
                    pass

    @pytest.mark.asyncio
    async def test_render_wide_rows(self, fake_data: FakeDataGenerator, mock_app_context):
        """Test rendering rows with many columns (wide tables)."""
        # Generate transaction data which has more/wider columns
        columns, rows = fake_data.generate_transaction_rows(5000)

        with mock_app_context:
            app = SSMSTUI()

            async with app.run_test(size=(200, 50)) as pilot:
                await pilot.pause()

                start_time = time.perf_counter()
                app._display_query_results(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    truncated=False,
                    elapsed_ms=0,
                )
                await pilot.pause()
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                print(f"\n  Rendered 5000 wide rows ({len(columns)} columns) in {elapsed_ms:.2f}ms")
                assert app.results_table.row_count == 5000

    @pytest.mark.asyncio
    async def test_render_with_special_characters(self, mock_app_context):
        """Test rendering data with markup-sensitive characters."""
        # Data that could break Rich markup if not escaped
        columns = ["id", "content"]
        rows = [
            (i, f"<script>alert({i})</script> [bold]test[/bold] {{curly}} `backtick`")
            for i in range(1000)
        ]

        with mock_app_context:
            app = SSMSTUI()

            async with app.run_test(size=(120, 50)) as pilot:
                await pilot.pause()

                # Should not raise any markup errors
                app._display_query_results(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    truncated=False,
                    elapsed_ms=0,
                )
                await pilot.pause()

                assert app.results_table.row_count == 1000

    @pytest.mark.asyncio
    async def test_render_with_null_values(self, mock_app_context):
        """Test rendering data with NULL values."""
        columns = ["id", "nullable_col", "another_null"]
        rows = [
            (i, None if i % 2 == 0 else f"value_{i}", None if i % 3 == 0 else i * 10)
            for i in range(1000)
        ]

        with mock_app_context:
            app = SSMSTUI()

            async with app.run_test(size=(120, 50)) as pilot:
                await pilot.pause()

                app._display_query_results(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    truncated=False,
                    elapsed_ms=0,
                )
                await pilot.pause()

                assert app.results_table.row_count == 1000


class TestMemoryUsage:
    """Tests for memory behavior with large datasets."""

    @pytest.mark.asyncio
    async def test_result_storage(self, fake_data: FakeDataGenerator, mock_app_context):
        """Verify that _last_result_rows stores all fetched rows."""
        columns, rows = fake_data.generate_user_rows(10000)

        with mock_app_context:
            app = SSMSTUI()

            async with app.run_test(size=(120, 50)) as pilot:
                await pilot.pause()

                app._display_query_results(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    truncated=False,
                    elapsed_ms=0,
                )
                await pilot.pause()

                # All rows should be stored for copy operations
                assert len(app._last_result_rows) == 10000
                assert app._last_result_row_count == 10000

    @pytest.mark.asyncio
    async def test_clear_and_re_render(self, fake_data: FakeDataGenerator, mock_app_context):
        """Test clearing and re-rendering doesn't leak memory."""
        columns, rows = fake_data.generate_user_rows(5000)

        with mock_app_context:
            app = SSMSTUI()

            async with app.run_test(size=(120, 50)) as pilot:
                await pilot.pause()

                # Render multiple times
                for i in range(3):
                    app._display_query_results(
                        columns=columns,
                        rows=rows,
                        row_count=len(rows),
                        truncated=False,
                        elapsed_ms=0,
                    )
                    await pilot.pause()

                # Final state should be clean
                assert app.results_table.row_count == 5000


class TestBenchmarks:
    """Benchmark tests using pytest-benchmark.

    Run with: pytest tests/performance/ --benchmark-only
    """

    def test_data_generation_benchmark(self, fake_data: FakeDataGenerator, benchmark):
        """Benchmark fake data generation speed."""
        benchmark(fake_data.generate_user_rows, 10000)

    def test_markup_escape_benchmark(self, fake_data: FakeDataGenerator, benchmark):
        """Benchmark the markup escaping overhead."""
        from rich.markup import escape as escape_markup

        _, rows = fake_data.generate_user_rows(1000)

        def escape_all():
            for row in rows:
                tuple(escape_markup(str(v)) if v is not None else "NULL" for v in row)

        benchmark(escape_all)
