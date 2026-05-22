"""Tests for DuckDB direct querying of data files (CSV, Parquet, JSON, ...).

Pointing a DuckDB connection at a data file loads it into a real TABLE
inside a per-process sidecar `.duckdb`. The user can then run full CRUD
against that table; writing back to the source file is explicit via
`COPY <table> TO '<path>'`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.providers.duckdb.adapter import DuckDBAdapter
from sqlit.domains.connections.providers.duckdb.data_files import (
    get_read_function,
    is_data_file,
    sidecar_path_for,
    table_name_for,
)


class TestGetReadFunction:
    """Map file extension → DuckDB table function."""

    @pytest.mark.parametrize(
        "filename, expected",
        [
            ("sales.csv", "read_csv_auto"),
            ("sales.CSV", "read_csv_auto"),
            ("data.tsv", "read_csv_auto"),
            ("events.parquet", "read_parquet"),
            ("events.pq", "read_parquet"),
            ("users.json", "read_json_auto"),
            ("events.jsonl", "read_json_auto"),
            ("events.ndjson", "read_json_auto"),
            ("sales.csv.gz", "read_csv_auto"),
            ("events.json.gz", "read_json_auto"),
            ("data.csv.zst", "read_csv_auto"),
        ],
    )
    def test_recognized_extensions(self, filename: str, expected: str):
        assert get_read_function(Path(filename)) == expected

    @pytest.mark.parametrize(
        "filename",
        [
            "data.duckdb",
            "data.db",
            "data.sqlite",
            "data",
            "data.unknown",
            "archive.tar.gz",
        ],
    )
    def test_unrecognized_extensions(self, filename: str):
        assert get_read_function(Path(filename)) is None
        assert is_data_file(Path(filename)) is False


class TestTableNameFor:
    @pytest.mark.parametrize(
        "filename, expected",
        [
            ("sales.csv", "sales"),
            ("Sales.CSV", "sales"),
            ("sales-2024.csv", "sales_2024"),
            ("events.json.gz", "events"),
            ("123-data.parquet", "_123_data"),
            ("weird name!.csv", "weird_name"),
            ("/abs/path/to/orders.parquet", "orders"),
        ],
    )
    def test_table_name(self, filename: str, expected: str):
        assert table_name_for(Path(filename)) == expected

    def test_empty_or_pure_punctuation_falls_back(self):
        assert table_name_for(Path("---.csv")) == "data"


class TestSidecarPath:
    def test_path_is_under_per_process_dir(self, tmp_path):
        sc = sidecar_path_for(tmp_path / "sales.csv")
        assert sc.suffix == ".duckdb"
        # The PID is in the path so different processes don't collide.
        assert f"sqlit-{os.getpid()}" in sc.parts

    def test_different_sources_have_different_sidecars(self, tmp_path):
        a = sidecar_path_for(tmp_path / "a.csv")
        b = sidecar_path_for(tmp_path / "b.csv")
        assert a != b

    def test_same_source_is_stable_within_process(self, tmp_path):
        src = tmp_path / "sales.csv"
        src.write_text("a,b\n1,2\n")
        assert sidecar_path_for(src) == sidecar_path_for(src)


class TestAdapterWithDataFile:
    """End-to-end against a real DuckDB."""

    @pytest.fixture(autouse=True)
    def _require_duckdb(self):
        pytest.importorskip("duckdb")

    def _make_config(self, file_path: Path) -> ConnectionConfig:
        return ConnectionConfig.from_dict({
            "name": "test",
            "db_type": "duckdb",
            "file_path": str(file_path),
        })

    def _cleanup_sidecar(self, file_path: Path) -> None:
        sc = sidecar_path_for(file_path)
        if sc.exists():
            sc.unlink()

    def test_csv_file_loaded_as_queryable_table(self, tmp_path):
        csv_file = tmp_path / "sales.csv"
        csv_file.write_text("region,quantity\nnorth,3\nsouth,7\neast,2\n")
        self._cleanup_sidecar(csv_file)

        conn = DuckDBAdapter().connect(self._make_config(csv_file))
        rows = conn.execute("SELECT region, quantity FROM sales ORDER BY region").fetchall()
        assert rows == [("east", 2), ("north", 3), ("south", 7)]

    def test_table_appears_in_schema_listing(self, tmp_path):
        csv_file = tmp_path / "events.csv"
        csv_file.write_text("id,name\n1,alpha\n2,beta\n")
        self._cleanup_sidecar(csv_file)

        adapter = DuckDBAdapter()
        conn = adapter.connect(self._make_config(csv_file))
        tables = adapter.get_tables(conn)
        table_names = [name for _schema, name in tables]
        assert "events" in table_names

    def test_json_file_loaded_as_table(self, tmp_path):
        json_file = tmp_path / "users.json"
        json_file.write_text(json.dumps([
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]))
        self._cleanup_sidecar(json_file)

        conn = DuckDBAdapter().connect(self._make_config(json_file))
        rows = conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
        assert rows == [(1, "Alice"), (2, "Bob")]

    def test_filename_with_dashes_becomes_underscored_table(self, tmp_path):
        csv_file = tmp_path / "monthly-sales.csv"
        csv_file.write_text("month,total\n2024-01,100\n2024-02,200\n")
        self._cleanup_sidecar(csv_file)

        conn = DuckDBAdapter().connect(self._make_config(csv_file))
        rows = conn.execute("SELECT total FROM monthly_sales ORDER BY month").fetchall()
        assert rows == [(100,), (200,)]

    def test_duckdb_file_unchanged_behavior(self, tmp_path):
        """A `.duckdb` file path should still produce a normal DuckDB
        connection with no auto-loaded data-file table."""
        import duckdb

        db_file = tmp_path / "scratch.duckdb"
        duckdb.connect(str(db_file)).close()

        conn = DuckDBAdapter().connect(self._make_config(db_file))
        rows = conn.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name = 'scratch' AND table_type = 'BASE TABLE'"
        ).fetchall()
        assert rows == [(0,)]


class TestCRUDAgainstDataFile:
    """CRUD (UPDATE/INSERT/DELETE) must work against the loaded table, and
    edits must persist across consecutive connections in the same process."""

    @pytest.fixture(autouse=True)
    def _require_duckdb(self):
        pytest.importorskip("duckdb")

    def _make_config(self, file_path: Path) -> ConnectionConfig:
        return ConnectionConfig.from_dict({
            "name": "test",
            "db_type": "duckdb",
            "file_path": str(file_path),
        })

    def _cleanup_sidecar(self, file_path: Path) -> None:
        sc = sidecar_path_for(file_path)
        if sc.exists():
            sc.unlink()

    def test_updates_persist_across_reconnects_in_same_process(self, tmp_path):
        csv_file = tmp_path / "sales.csv"
        csv_file.write_text("region,amount\nnorth,100\nsouth,200\n")
        self._cleanup_sidecar(csv_file)

        adapter = DuckDBAdapter()
        cfg = self._make_config(csv_file)

        # First connect loads the file; we modify the table.
        conn1 = adapter.connect(cfg)
        conn1.execute("UPDATE sales SET amount = amount * 2 WHERE region = 'north'")
        conn1.execute("INSERT INTO sales VALUES ('west', 999)")
        conn1.close()

        # Second connect to the same source must see the modifications,
        # because the sidecar persists for this process's lifetime.
        conn2 = adapter.connect(cfg)
        rows = conn2.execute("SELECT region, amount FROM sales ORDER BY region").fetchall()
        assert rows == [("north", 200), ("south", 200), ("west", 999)]

    def test_fresh_sidecar_reloads_from_source(self, tmp_path):
        """Simulates a new sqlit process by deleting the sidecar — the
        adapter should re-read the source file and the user's previous
        edits should be gone."""
        csv_file = tmp_path / "sales.csv"
        csv_file.write_text("region,amount\nnorth,100\n")
        self._cleanup_sidecar(csv_file)

        adapter = DuckDBAdapter()
        cfg = self._make_config(csv_file)

        conn = adapter.connect(cfg)
        conn.execute("UPDATE sales SET amount = 9999")
        conn.close()

        # Simulate process restart.
        sidecar = sidecar_path_for(csv_file)
        sidecar.unlink()

        conn = adapter.connect(cfg)
        rows = conn.execute("SELECT region, amount FROM sales").fetchall()
        assert rows == [("north", 100)]

    def test_explicit_copy_writes_back_to_source(self, tmp_path):
        csv_file = tmp_path / "sales.csv"
        csv_file.write_text("region,amount\nnorth,100\nsouth,200\n")
        self._cleanup_sidecar(csv_file)

        conn = DuckDBAdapter().connect(self._make_config(csv_file))
        conn.execute("UPDATE sales SET amount = amount + 1")
        # Path is fine to interpolate here since it came from tmp_path.
        conn.execute(
            f"COPY sales TO '{csv_file}' (FORMAT CSV, HEADER)"
        )

        # Source file on disk now reflects the modification.
        contents = csv_file.read_text().strip().splitlines()
        assert contents[0] == "region,amount"
        assert sorted(contents[1:]) == ["north,101", "south,201"]
