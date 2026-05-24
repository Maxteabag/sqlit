"""Tests for the file-backed HistoryStore."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlit.domains.query.store.history import (
    HistoryStore,
    _connection_dir_name,
    _database_dir_name,
)


@pytest.fixture
def store(tmp_path: Path) -> HistoryStore:
    return HistoryStore(base_dir=tmp_path / "queries")


def _all_files_for(store: HistoryStore, connection: str) -> list[Path]:
    """List every .sql file for a connection across all db subdirs."""
    conn_dir = store.base_dir / _connection_dir_name(connection)
    if not conn_dir.is_dir():
        return []
    files = [p for p in conn_dir.glob("*.sql") if p.is_file()]
    for child in conn_dir.iterdir():
        if child.is_dir():
            files.extend(p for p in child.glob("*.sql") if p.is_file())
    return sorted(files)


def _read_file_text(store: HistoryStore, connection: str) -> list[str]:
    return [p.read_text(encoding="utf-8") for p in _all_files_for(store, connection)]


class TestRoundTrip:
    def test_save_and_load_one_query(self, store: HistoryStore) -> None:
        store.save_query("postgres-prod", "SELECT 1", database="myapp")
        entries = store.load_for_connection("postgres-prod")
        assert len(entries) == 1
        assert entries[0].query == "SELECT 1"
        assert entries[0].connection_name == "postgres-prod"
        assert entries[0].database == "myapp"
        assert entries[0].timestamp  # ISO string set by store

    def test_load_returns_most_recent_first(self, store: HistoryStore) -> None:
        store.save_query("c", "SELECT 1")
        store.save_query("c", "SELECT 2")
        store.save_query("c", "SELECT 3")
        entries = store.load_for_connection("c")
        assert [e.query for e in entries] == ["SELECT 3", "SELECT 2", "SELECT 1"]

    def test_load_all_spans_connections(self, store: HistoryStore) -> None:
        store.save_query("a", "SELECT 1")
        store.save_query("b", "SELECT 2")
        names = {e.connection_name for e in store.load_all()}
        assert names == {"a", "b"}

    def test_blank_query_is_ignored(self, store: HistoryStore) -> None:
        store.save_query("c", "   \n  \n")
        assert store.load_for_connection("c") == []

    def test_query_text_is_stripped(self, store: HistoryStore) -> None:
        store.save_query("c", "  SELECT 1  \n  ")
        entries = store.load_for_connection("c")
        assert entries[0].query == "SELECT 1"


class TestDedup:
    def test_same_query_updates_in_place(self, store: HistoryStore) -> None:
        store.save_query("c", "SELECT 1")
        first_ts = store.load_for_connection("c")[0].timestamp
        import time
        time.sleep(0.01)
        store.save_query("c", "SELECT 1")
        entries = store.load_for_connection("c")
        assert len(entries) == 1
        assert entries[0].timestamp != first_ts

    def test_same_query_only_one_file_on_disk(self, store: HistoryStore) -> None:
        store.save_query("c", "SELECT 1")
        store.save_query("c", "SELECT 1")
        store.save_query("c", "SELECT 1")
        assert len(_read_file_text(store, "c")) == 1

    def test_whitespace_variants_dedup(self, store: HistoryStore) -> None:
        store.save_query("c", "SELECT 1")
        store.save_query("c", "  SELECT 1  ")
        assert len(store.load_for_connection("c")) == 1

    def test_dedup_across_db_subdirs(self, store: HistoryStore) -> None:
        """Same query on different DBs of the same connection — last write wins."""
        store.save_query("c", "SELECT 1", database="db_a")
        store.save_query("c", "SELECT 1", database="db_b")
        # Single file total (the second save deletes the first).
        assert len(_all_files_for(store, "c")) == 1
        entries = store.load_for_connection("c")
        assert len(entries) == 1
        assert entries[0].database == "db_b"


class TestPathLayout:
    def test_database_becomes_subdir(self, store: HistoryStore) -> None:
        store.save_query("postgres-prod", "SELECT 1", database="myapp")
        conn_dir = store.base_dir / _connection_dir_name("postgres-prod")
        db_dir = conn_dir / _database_dir_name("myapp")
        assert db_dir.is_dir()
        assert any(db_dir.glob("*.sql"))
        # Nothing directly under the connection dir.
        assert not any(p.is_file() for p in conn_dir.glob("*.sql"))

    def test_no_database_keeps_files_flat(self, store: HistoryStore) -> None:
        store.save_query("local-sqlite", "SELECT 1")
        conn_dir = store.base_dir / _connection_dir_name("local-sqlite")
        assert any(conn_dir.glob("*.sql"))
        # No subdirs created when database is empty.
        assert not any(child.is_dir() for child in conn_dir.iterdir())


class TestHeaderFormat:
    def test_header_carries_only_marker_and_connection(self, store: HistoryStore) -> None:
        store.save_query("postgres-prod", "SELECT 1", database="myapp")
        text = _read_file_text(store, "postgres-prod")[0]
        assert "-- sqlit:history" in text
        assert "-- connection: postgres-prod" in text
        # database is now structural (in the path), not in the header.
        assert "-- database:" not in text
        # timestamp is in the filename, not the header.
        assert "-- ran:" not in text

    def test_query_body_preserved_verbatim(self, store: HistoryStore) -> None:
        body = "-- user's own comment\nSELECT 1\nFROM users"
        store.save_query("c", body)
        entries = store.load_for_connection("c")
        assert entries[0].query == body


class TestConnectionDirNaming:
    def test_slashes_are_sanitized(self) -> None:
        name = _connection_dir_name("server/database")
        assert "/" not in name
        assert name.startswith("server_database_")

    def test_two_similar_names_get_distinct_dirs(self) -> None:
        a = _connection_dir_name("a/b")
        b = _connection_dir_name("a_b")
        assert a != b

    def test_unicode_name_is_handled(self, store: HistoryStore) -> None:
        store.save_query("databäs-prøduktiøn", "SELECT 1")
        entries = store.load_for_connection("databäs-prøduktiøn")
        assert len(entries) == 1
        assert entries[0].connection_name == "databäs-prøduktiøn"


class TestFilenameOrdering:
    def test_filenames_sort_chronologically(self, store: HistoryStore) -> None:
        import time
        for i in range(5):
            store.save_query("c", f"SELECT {i}")
            time.sleep(0.005)
        names = sorted(p.name for p in _all_files_for(store, "c"))
        last_text = next(p for p in _all_files_for(store, "c") if p.name == names[-1]).read_text()
        assert "SELECT 4" in last_text


class TestDeleteAndClear:
    def test_delete_entry_by_timestamp(self, store: HistoryStore) -> None:
        store.save_query("c", "SELECT 1")
        ts = store.load_for_connection("c")[0].timestamp
        assert store.delete_entry("c", ts) is True
        assert store.load_for_connection("c") == []

    def test_delete_entry_missing_returns_false(self, store: HistoryStore) -> None:
        assert store.delete_entry("c", "2026-01-01T00:00:00") is False

    def test_clear_for_connection(self, store: HistoryStore) -> None:
        store.save_query("c", "SELECT 1")
        store.save_query("c", "SELECT 2", database="db_a")
        assert store.clear_for_connection("c") == 2
        assert store.load_for_connection("c") == []

    def test_clear_drops_empty_db_subdirs(self, store: HistoryStore) -> None:
        store.save_query("c", "SELECT 1", database="db_a")
        store.clear_for_connection("c")
        conn_dir = store.base_dir / _connection_dir_name("c")
        assert not conn_dir.exists()


class TestEviction:
    def test_max_entries_enforced_across_databases(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Eviction is per-connection, summing across all database subdirs."""
        monkeypatch.setattr(HistoryStore, "MAX_ENTRIES_PER_CONNECTION", 3)
        s = HistoryStore(base_dir=tmp_path / "queries")
        import time
        # Alternate databases — oldest two should still be the ones evicted.
        for i in range(5):
            s.save_query("c", f"SELECT {i}", database="db_a" if i % 2 else "db_b")
            time.sleep(0.005)
        entries = s.load_for_connection("c")
        assert len(entries) == 3
        assert {e.query for e in entries} == {"SELECT 2", "SELECT 3", "SELECT 4"}


class TestLegacyMigration:
    def test_migrates_json_on_first_use(self, tmp_path: Path) -> None:
        config = tmp_path / "config"
        config.mkdir()
        legacy = config / "query_history.json"
        legacy.write_text(
            json.dumps(
                [
                    {
                        "query": "SELECT 1",
                        "timestamp": "2026-01-01T00:00:00",
                        "connection_name": "old",
                    },
                    {
                        "query": "SELECT 2",
                        "timestamp": "2026-01-02T00:00:00",
                        "connection_name": "old",
                        "database": "myapp",
                    },
                ]
            )
        )

        store = HistoryStore(base_dir=config / "queries")
        entries = store.load_for_connection("old")
        assert [e.query for e in entries] == ["SELECT 2", "SELECT 1"]
        assert entries[0].database == "myapp"
        # Database-bearing entry now lives in a db subdir.
        old_dir = config / "queries" / _connection_dir_name("old")
        myapp_dir = old_dir / _database_dir_name("myapp")
        assert any(myapp_dir.glob("*.sql"))
        # No-database entry stays flat.
        assert any(p.is_file() for p in old_dir.glob("*.sql"))

        assert not legacy.exists()
        assert (config / "query_history.json.migrated").exists()

    def test_migration_handles_missing_file(self, tmp_path: Path) -> None:
        store = HistoryStore(base_dir=tmp_path / "queries")
        assert store.load_all() == []

    def test_migration_handles_malformed_file(self, tmp_path: Path) -> None:
        config = tmp_path / "config"
        config.mkdir()
        (config / "query_history.json").write_text("not valid json")
        store = HistoryStore(base_dir=config / "queries")
        assert store.load_all() == []
        assert (config / "query_history.json").exists()


class TestFallbackParsing:
    def test_file_without_header_uses_filename_timestamp(
        self, store: HistoryStore
    ) -> None:
        conn_dir = store.base_dir / _connection_dir_name("c")
        conn_dir.mkdir(parents=True)
        (conn_dir / "2026-05-23T14-30-15_deadbeef.sql").write_text(
            "SELECT raw_user_file\n", encoding="utf-8"
        )
        entries = store.load_for_connection("c")
        assert len(entries) == 1
        assert entries[0].query == "SELECT raw_user_file"
        assert entries[0].timestamp == "2026-05-23T14:30:15"
        assert entries[0].connection_name == "c"
