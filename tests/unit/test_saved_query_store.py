"""Regression coverage for user-managed saved query files."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlit.domains.query.store.saved_queries import (
    SavedQueryConflictError,
    SavedQueryNameError,
    SavedQueryStore,
)


@pytest.fixture
def store(tmp_path: Path) -> SavedQueryStore:
    return SavedQueryStore(tmp_path / "saved-queries")


def test_directory_is_created_only_on_first_save(store: SavedQueryStore) -> None:
    directory = store.connection_dir("production")
    assert not directory.exists()
    assert store.list_for_connection("production") == []
    assert not directory.exists()

    store.save("production", "daily-report", "SELECT 1")

    assert directory.is_dir()


def test_save_adds_sql_suffix_and_supports_nested_folders(
    store: SavedQueryStore,
) -> None:
    entry = store.save(
        "production",
        "reports/daily-sales",
        "SELECT * FROM sales",
    )

    assert entry.relative_path == "reports/daily-sales.sql"
    assert entry.path.read_text(encoding="utf-8") == "SELECT * FROM sales"


def test_save_preserves_uppercase_sql_suffix(store: SavedQueryStore) -> None:
    entry = store.save("production", "REPORT.SQL", "SELECT 1")

    assert entry.relative_path == "REPORT.SQL"
    assert [item.relative_path for item in store.list_for_connection("production")] == ["REPORT.SQL"]


def test_list_discovers_external_uppercase_sql_file(store: SavedQueryStore) -> None:
    directory = store.connection_dir("production")
    directory.mkdir(parents=True)
    (directory / "external.SQL").write_text("SELECT 1", encoding="utf-8")

    assert [item.relative_path for item in store.list_for_connection("production")] == ["external.SQL"]
    assert store.load("production", "external.SQL").query == "SELECT 1"


def test_list_is_recursive_sorted_and_ignores_hidden_files(
    store: SavedQueryStore,
) -> None:
    store.save("production", "z-last", "SELECT 3")
    store.save("production", "reports/a-first", "SELECT 1")
    hidden = store.connection_dir("production") / ".hidden.sql"
    hidden.write_text("SELECT 0", encoding="utf-8")

    entries = store.list_for_connection("production")

    assert [entry.relative_path for entry in entries] == [
        "reports/a-first.sql",
        "z-last.sql",
    ]


def test_list_tolerates_directory_traversal_failure(store: SavedQueryStore, monkeypatch: pytest.MonkeyPatch) -> None:
    store.save("production", "report", "SELECT 1")

    def fail_traversal(_self: Path, _pattern: str):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "rglob", fail_traversal)

    assert store.list_for_connection("production") == []


def test_existing_file_requires_explicit_overwrite(store: SavedQueryStore) -> None:
    store.save("production", "report", "SELECT 1")

    with pytest.raises(FileExistsError):
        store.save("production", "report", "SELECT 2")

    entry = store.save("production", "report", "SELECT 2", overwrite=True)
    assert entry.query == "SELECT 2"


def test_expected_fingerprint_detects_external_change(store: SavedQueryStore) -> None:
    loaded = store.save("production", "report", "SELECT 1")
    loaded.path.write_text("SELECT 2", encoding="utf-8")

    with pytest.raises(SavedQueryConflictError):
        store.save(
            "production",
            "report",
            "SELECT 3",
            expected=loaded.fingerprint,
        )


def test_save_with_matching_fingerprint_updates_atomically(store: SavedQueryStore) -> None:
    loaded = store.save("production", "report", "SELECT 1")

    updated = store.save(
        "production",
        "report",
        "SELECT 2",
        expected=loaded.fingerprint,
    )

    assert updated.query == "SELECT 2"
    assert updated.fingerprint != loaded.fingerprint
    assert not list(updated.path.parent.glob(".sqlit-save-*"))


def test_oversized_save_does_not_replace_existing_file(
    store: SavedQueryStore,
) -> None:
    existing = store.save("production", "report", "SELECT original")

    with pytest.raises(OSError, match="larger than 2 MiB"):
        store.save(
            "production",
            "report",
            "x" * (2 * 1024 * 1024 + 1),
            expected=existing.fingerprint,
        )

    assert existing.path.read_text(encoding="utf-8") == "SELECT original"


def test_fingerprint_bounds_externally_replaced_oversized_file(
    store: SavedQueryStore,
) -> None:
    existing = store.save("production", "report", "SELECT original")
    existing.path.write_bytes(b"x" * (2 * 1024 * 1024 + 1))

    assert store.current_fingerprint("production", "report.sql") is None


def test_save_revalidates_fingerprint_immediately_before_replace(store: SavedQueryStore, monkeypatch: pytest.MonkeyPatch) -> None:
    existing = store.save("production", "report", "SELECT original")
    changed = type(existing.fingerprint)(
        digest="changed",
        size=1,
        mtime_ns=existing.fingerprint.mtime_ns + 1,
    )
    fingerprints = iter((existing.fingerprint, changed))
    monkeypatch.setattr(store, "_fingerprint_at", lambda *_args: next(fingerprints))

    with pytest.raises(SavedQueryConflictError):
        store.save(
            "production",
            "report",
            "SELECT sqlit",
            expected=existing.fingerprint,
        )

    assert existing.path.read_text(encoding="utf-8") == "SELECT original"
    assert not list(existing.path.parent.glob(".sqlit-save-*"))


def test_fallback_save_does_not_replace_concurrently_created_file(store: SavedQueryStore, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "_secure_dir_fd_available", lambda: False)
    path, _ = store._path_for_name("production", "report")
    checks = 0
    original_reject = store._reject_nested_symlink

    def create_during_write(root: Path, destination: Path) -> None:
        nonlocal checks
        checks += 1
        if checks == 2:
            destination.write_text("SELECT concurrent", encoding="utf-8")
        original_reject(root, destination)

    monkeypatch.setattr(store, "_reject_nested_symlink", create_during_write)

    with pytest.raises(SavedQueryConflictError):
        store.save("production", "report", "SELECT sqlit")

    assert path.read_text(encoding="utf-8") == "SELECT concurrent"


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        ".hidden",
        ".private/report",
        "../outside",
        "/tmp/outside",
        "reports/../outside",
    ],
)
def test_names_cannot_escape_library(store: SavedQueryStore, name: str) -> None:
    with pytest.raises(SavedQueryNameError):
        store.save("production", name, "SELECT 1")


def test_utf8_bom_is_read_without_becoming_editor_content(store: SavedQueryStore) -> None:
    directory = store.connection_dir("production")
    directory.mkdir(parents=True)
    path = directory / "bom.sql"
    path.write_bytes(bytes((0xEF, 0xBB, 0xBF)) + "SELECT 'ø'".encode())

    entry = store.list_for_connection("production")[0]

    assert entry.query == "SELECT 'ø'"


def test_root_directory_symlink_supports_shared_git_library(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "team-query-repo"
    shared.mkdir()
    (shared / "health.sql").write_text("SELECT 1", encoding="utf-8")
    store = SavedQueryStore(tmp_path / "saved-queries")
    root = store.connection_dir("production")
    root.parent.mkdir()
    root.symlink_to(shared, target_is_directory=True)

    entries = store.list_for_connection("production")

    assert [entry.relative_path for entry in entries] == ["health.sql"]


def test_individual_symlink_is_rejected_to_prevent_external_overwrite(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "shared.sql"
    shared.write_text("SELECT 1", encoding="utf-8")
    store = SavedQueryStore(tmp_path / "saved-queries")
    root = store.connection_dir("production")
    root.mkdir(parents=True)
    linked = root / "shared.sql"
    linked.symlink_to(shared)
    with pytest.raises(SavedQueryNameError):
        store.load("production", "shared.sql")

    assert linked.is_symlink()
    assert shared.read_text(encoding="utf-8") == "SELECT 1"


def test_nested_directory_symlink_is_rejected(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "report.sql").write_text("SELECT 1", encoding="utf-8")
    store = SavedQueryStore(tmp_path / "saved-queries")
    root = store.connection_dir("production")
    root.mkdir(parents=True)
    (root / "linked-folder").symlink_to(shared, target_is_directory=True)

    with pytest.raises(SavedQueryNameError):
        store.load("production", "linked-folder/report.sql")


def test_connection_rename_moves_existing_library(store: SavedQueryStore) -> None:
    store.save("old name", "report", "SELECT 1")

    assert store.rename_connection("old name", "new name") is True

    assert store.list_for_connection("old name") == []
    assert store.list_for_connection("new name")[0].query == "SELECT 1"


def test_connection_rename_refuses_to_merge_two_libraries(
    store: SavedQueryStore,
) -> None:
    store.save("old", "old-report", "SELECT 1")
    store.save("new", "new-report", "SELECT 2")

    assert store.rename_connection("old", "new") is False
    assert store.list_for_connection("old")[0].query == "SELECT 1"


def test_connection_rename_reports_filesystem_failure(store: SavedQueryStore, monkeypatch: pytest.MonkeyPatch) -> None:
    store.save("old", "report", "SELECT 1")

    def fail_rename(_self: Path, _target: Path) -> None:
        raise OSError("read only")

    monkeypatch.setattr(Path, "rename", fail_rename)

    assert store.rename_connection("old", "new") is False
    assert store.list_for_connection("old")[0].query == "SELECT 1"


def test_rename_file_moves_query_and_removes_empty_folder(
    store: SavedQueryStore,
) -> None:
    original = store.save("production", "old/report", "SELECT 1")

    renamed = store.rename_file(
        "production",
        original.relative_path,
        "new/daily",
        expected=original.fingerprint,
    )

    assert renamed.relative_path == "new/daily.sql"
    assert renamed.query == "SELECT 1"
    assert not (store.connection_dir("production") / "old").exists()


def test_rename_file_refuses_collision_and_external_change(
    store: SavedQueryStore,
) -> None:
    original = store.save("production", "first", "SELECT 1")
    store.save("production", "second", "SELECT 2")

    with pytest.raises(FileExistsError):
        store.rename_file("production", "first.sql", "second.sql")

    original.path.write_text("SELECT changed", encoding="utf-8")
    with pytest.raises(SavedQueryConflictError):
        store.rename_file(
            "production",
            "first.sql",
            "renamed.sql",
            expected=original.fingerprint,
        )


def test_delete_file_checks_fingerprint_and_removes_empty_parents(
    store: SavedQueryStore,
) -> None:
    entry = store.save("production", "reports/daily", "SELECT 1")
    entry.path.write_text("SELECT changed", encoding="utf-8")

    with pytest.raises(SavedQueryConflictError):
        store.delete_file("production", entry.relative_path, expected=entry.fingerprint)

    current = store.load("production", entry.relative_path)
    store.delete_file("production", current.relative_path, expected=current.fingerprint)
    assert store.list_for_connection("production") == []
    assert not (store.connection_dir("production") / "reports").exists()


def test_rename_and_delete_folder_update_all_nested_queries(
    store: SavedQueryStore,
) -> None:
    store.save("production", "reports/daily", "SELECT 1")
    store.save("production", "reports/monthly/summary", "SELECT 2")

    new_path = store.rename_folder("production", "reports", "analytics")

    assert new_path == "analytics"
    assert [entry.relative_path for entry in store.list_for_connection("production")] == ["analytics/daily.sql", "analytics/monthly/summary.sql"]
    assert store.delete_folder("production", "analytics") == 2
    assert store.list_for_connection("production") == []


def test_delete_folder_preserves_unrelated_files(store: SavedQueryStore) -> None:
    store.save("production", "reports/daily", "SELECT 1")
    notes = store.connection_dir("production") / "reports" / "README.md"
    notes.write_text("keep me", encoding="utf-8")

    assert store.delete_folder("production", "reports") == 1

    assert notes.read_text(encoding="utf-8") == "keep me"


@pytest.mark.parametrize("name", ["", ".", "..", "../outside", ".hidden"])
def test_folder_operations_reject_unsafe_names(store: SavedQueryStore, name: str) -> None:
    store.save("production", "reports/daily", "SELECT 1")
    with pytest.raises(SavedQueryNameError):
        store.rename_folder("production", "reports", name)
    with pytest.raises(SavedQueryNameError):
        store.delete_folder("production", name)
