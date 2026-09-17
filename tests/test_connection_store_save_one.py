"""Tests for per-connection persistence (save_one) in ConnectionStore.

These tests verify that editing, adding, or deleting a single connection only
touches that connection's credentials in the keyring, rather than rewriting the
credentials for every saved connection (the old ``save_all`` behavior).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from sqlit.domains.connections.app.credentials import (
    CredentialsPersistError,
    CredentialsStoreError,
    PlaintextCredentialsService,
    reset_credentials_service,
    set_credentials_service,
)
from tests.helpers import ConnectionConfig

if TYPE_CHECKING:
    from sqlit.domains.connections.store.connections import ConnectionStore


class SpyCredentialsService(PlaintextCredentialsService):
    """Credentials service that records per-name set/delete calls."""

    def __init__(self) -> None:
        super().__init__()
        self.set_db: list[str] = []
        self.set_ssh: list[str] = []
        self.delete_db: list[str] = []
        self.delete_ssh: list[str] = []
        self.fail_set_for: set[str] = set()
        self.fail_set_ssh_for: set[str] = set()
        self.fail_set_ssh_raw_for: set[str] = set()
        self.fail_migration_read_for: set[str] = set()

    def set_password(self, connection_name: str, password: str) -> None:
        self.set_db.append(connection_name)
        if connection_name in self.fail_set_for:
            raise CredentialsStoreError(
                connection_name=connection_name,
                kind="db",
                action="store",
                reason=RuntimeError("boom"),
            )
        super().set_password(connection_name, password)

    def set_ssh_password(self, connection_name: str, password: str) -> None:
        self.set_ssh.append(connection_name)
        if connection_name in self.fail_set_ssh_raw_for:
            self.fail_set_ssh_raw_for.remove(connection_name)
            raise OSError("disk unavailable")
        if connection_name in self.fail_set_ssh_for:
            raise CredentialsStoreError(
                connection_name=connection_name,
                kind="ssh",
                action="store",
                reason=RuntimeError("boom"),
            )
        super().set_ssh_password(connection_name, password)

    def get_password_for_migration(self, connection_name: str) -> str | None:
        if connection_name in self.fail_migration_read_for:
            raise CredentialsStoreError(
                connection_name=connection_name,
                kind="db",
                action="read",
                reason=RuntimeError("boom"),
            )
        return super().get_password_for_migration(connection_name)

    def delete_password(self, connection_name: str) -> None:
        self.delete_db.append(connection_name)
        super().delete_password(connection_name)

    def delete_ssh_password(self, connection_name: str) -> None:
        self.delete_ssh.append(connection_name)
        super().delete_ssh_password(connection_name)

    def touched(self, name: str) -> bool:
        return name in (self.set_db + self.set_ssh + self.delete_db + self.delete_ssh)

    def reset_calls(self) -> None:
        self.set_db.clear()
        self.set_ssh.clear()
        self.delete_db.clear()
        self.delete_ssh.clear()


class TestSaveOne:
    """Unit tests for ConnectionStore.save_one and related paths."""

    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.creds = SpyCredentialsService()
        set_credentials_service(self.creds)

    def teardown_method(self) -> None:
        reset_credentials_service()
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_store(self) -> ConnectionStore:
        from sqlit.domains.connections.store.connections import ConnectionStore
        from sqlit.shared.core.store import JSONFileStore

        class TempConnectionStore(ConnectionStore):
            def __init__(self, tmpdir: str, creds) -> None:
                JSONFileStore.__init__(self, Path(tmpdir) / "connections.json")
                self._credentials_service = creds

        return TempConnectionStore(self.tmpdir, self.creds)

    def _json(self) -> list[dict]:
        path = Path(self.tmpdir) / "connections.json"
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get("connections", [])
        return data

    def _make(self, name: str, password: str | None = "pw", ssh: bool = False):
        kwargs = {
            "name": name,
            "db_type": "postgresql",
            "server": "localhost",
            "username": "user",
            "password": password,
        }
        if ssh:
            kwargs.update(
                ssh_enabled=True,
                ssh_host="bastion",
                ssh_username="ssh_user",
                ssh_password="ssh_secret",
            )
        return ConnectionConfig(**kwargs)

    # --- core behavior -----------------------------------------------------

    def test_save_one_only_touches_target_credentials(self) -> None:
        store = self._create_store()
        store.save_all([self._make("a"), self._make("b"), self._make("c")])
        self.creds.reset_calls()

        store.save_one(self._make("b", password="new"))

        # Only "b" credentials were written; a and c untouched.
        assert self.creds.set_db == ["b"]
        assert not self.creds.touched("a")
        assert not self.creds.touched("c")
        assert self.creds.get_password("b") == "new"

    def test_save_one_persists_all_in_index(self) -> None:
        store = self._create_store()
        store.save_all([self._make("a"), self._make("b")])

        store.save_one(self._make("b", password="new"))

        names = {c["name"] for c in self._json()}
        assert names == {"a", "b"}

    def test_save_one_strips_passwords_from_json(self) -> None:
        store = self._create_store()
        store.save_one(self._make("a", ssh=True))

        entry = self._json()[0]
        assert entry["endpoint"]["password"] is None
        assert entry["tunnel"]["password"] is None
        assert self.creds.get_password("a") == "pw"
        assert self.creds.get_ssh_password("a") == "ssh_secret"

    def test_save_one_appends_new_connection(self) -> None:
        store = self._create_store()
        store.save_one(self._make("a"))
        store.save_one(self._make("b"))

        assert {c["name"] for c in self._json()} == {"a", "b"}

    def test_save_one_replaces_existing_without_duplicate(self) -> None:
        store = self._create_store()
        store.save_one(self._make("a", password="one"))
        store.save_one(self._make("a", password="two"))

        entries = [c for c in self._json() if c["name"] == "a"]
        assert len(entries) == 1
        assert self.creds.get_password("a") == "two"

    def test_save_one_empty_password_is_stored(self) -> None:
        store = self._create_store()
        store.save_one(self._make("a", password=""))

        assert self.creds.get_password("a") == ""
        loaded = store.load_all()
        assert loaded[0].tcp_endpoint.password == ""

    def test_save_one_none_password_filled_from_keyring(self) -> None:
        """Editing metadata with password=None keeps the stored password."""
        store = self._create_store()
        store.save_one(self._make("a", password="kept"))
        self.creds.reset_calls()

        # Re-save with password None (e.g. loaded without credentials).
        store.save_one(self._make("a", password=None))

        assert self.creds.get_password("a") == "kept"

    def test_save_one_password_command_removes_stored_password(self) -> None:
        store = self._create_store()
        store.save_one(self._make("a", password="stale"))
        dynamic = self._make("a", password=None)
        assert dynamic.tcp_endpoint is not None
        dynamic.tcp_endpoint.password_command = "dynamic-token"

        store.save_one(dynamic)

        assert self.creds.get_password("a") is None
        assert "a" in self.creds.delete_db
        endpoint = self._json()[0]["endpoint"]
        assert endpoint["password_command"] == "dynamic-token"

    # --- rename ------------------------------------------------------------

    def test_save_one_rename_moves_credentials(self) -> None:
        store = self._create_store()
        store.save_one(self._make("old", password="secret", ssh=True))
        self.creds.reset_calls()

        renamed = self._make("new", password="secret", ssh=True)
        store.save_one(renamed, previous_name="old")

        # Old entries deleted, new entries written.
        assert "old" in self.creds.delete_db
        assert "old" in self.creds.delete_ssh
        assert self.creds.get_password("old") is None
        assert self.creds.get_ssh_password("old") is None
        assert self.creds.get_password("new") == "secret"
        assert self.creds.get_ssh_password("new") == "ssh_secret"
        assert {c["name"] for c in self._json()} == {"new"}

    def test_save_one_rename_preserves_omitted_credentials(self) -> None:
        store = self._create_store()
        store.save_one(self._make("old", password="secret", ssh=True))
        self.creds.reset_calls()

        renamed = self._make("new", password=None, ssh=True)
        assert renamed.tunnel is not None
        renamed.tunnel.password = None
        store.save_one(renamed, previous_name="old")

        assert self.creds.get_password("old") is None
        assert self.creds.get_ssh_password("old") is None
        assert self.creds.get_password("new") == "secret"
        assert self.creds.get_ssh_password("new") == "ssh_secret"

    def test_save_one_rename_to_password_command_drops_old_password(self) -> None:
        store = self._create_store()
        store.save_one(self._make("old", password="stale"))
        renamed = self._make("new", password=None)
        assert renamed.tcp_endpoint is not None
        renamed.tcp_endpoint.password_command = "dynamic-token"

        store.save_one(renamed, previous_name="old")

        assert self.creds.get_password("old") is None
        assert self.creds.get_password("new") is None
        assert {item["name"] for item in self._json()} == {"new"}

    def test_save_one_failed_rename_keeps_original_usable(self) -> None:
        store = self._create_store()
        store.save_one(self._make("old", password="secret", ssh=True))
        self.creds.reset_calls()
        self.creds.fail_set_for = {"new"}

        renamed = self._make("new", password=None, ssh=True)
        assert renamed.tunnel is not None
        renamed.tunnel.password = None
        with pytest.raises(CredentialsPersistError):
            store.save_one(renamed, previous_name="old")

        assert self.creds.get_password("old") == "secret"
        assert self.creds.get_ssh_password("old") == "ssh_secret"
        assert "old" not in self.creds.delete_db
        assert "old" not in self.creds.delete_ssh
        assert {c["name"] for c in self._json()} == {"old"}

    def test_save_one_rename_aborts_when_source_credentials_cannot_be_read(self) -> None:
        store = self._create_store()
        store.save_one(self._make("old", password="secret", ssh=True))
        self.creds.reset_calls()
        self.creds.fail_migration_read_for = {"old"}

        renamed = self._make("new", password=None, ssh=True)
        with pytest.raises(CredentialsPersistError):
            store.save_one(renamed, previous_name="old")

        self.creds.fail_migration_read_for.clear()
        assert self.creds.get_password("old") == "secret"
        assert self.creds.get_password("new") is None
        assert {c["name"] for c in self._json()} == {"old"}

    def test_save_one_partial_rename_write_restores_destination_credentials(self) -> None:
        store = self._create_store()
        old = self._make("old", password="source-db", ssh=True)
        destination = self._make("new", password="destination-db", ssh=True)
        assert destination.tunnel is not None
        destination.tunnel.password = "destination-ssh"
        store.save_all([old, destination])
        self.creds.reset_calls()
        self.creds.fail_set_ssh_for = {"new"}

        renamed = self._make("new", password=None, ssh=True)
        assert renamed.tunnel is not None
        renamed.tunnel.password = None
        with pytest.raises(CredentialsPersistError):
            store.save_one(renamed, previous_name="old")

        self.creds.fail_set_ssh_for.clear()
        assert self.creds.get_password("old") == "source-db"
        assert self.creds.get_ssh_password("old") == "ssh_secret"
        assert self.creds.get_password("new") == "destination-db"
        assert self.creds.get_ssh_password("new") == "destination-ssh"
        assert {c["name"] for c in self._json()} == {"old", "new"}

    def test_save_one_raw_backend_failure_restores_destination_credentials(self) -> None:
        store = self._create_store()
        old = self._make("old", password="source-db", ssh=True)
        destination = self._make("new", password="destination-db", ssh=True)
        assert destination.tunnel is not None
        destination.tunnel.password = "destination-ssh"
        store.save_all([old, destination])
        self.creds.reset_calls()
        self.creds.fail_set_ssh_raw_for = {"new"}

        renamed = self._make("new", password=None, ssh=True)
        assert renamed.tunnel is not None
        renamed.tunnel.password = None
        with pytest.raises(OSError):
            store.save_one(renamed, previous_name="old")

        self.creds.fail_set_ssh_raw_for.clear()
        assert self.creds.get_password("old") == "source-db"
        assert self.creds.get_password("new") == "destination-db"
        assert self.creds.get_ssh_password("new") == "destination-ssh"
        assert {c["name"] for c in self._json()} == {"old", "new"}

    def test_save_one_rename_does_not_delete_when_name_unchanged(self) -> None:
        store = self._create_store()
        store.save_one(self._make("a", password="secret"))
        self.creds.reset_calls()

        store.save_one(self._make("a", password="secret"), previous_name="a")

        assert self.creds.delete_db == []

    # --- error handling ----------------------------------------------------

    def test_save_one_raises_persist_error_on_failure(self) -> None:
        store = self._create_store()
        self.creds.fail_set_for = {"a"}

        with pytest.raises(CredentialsPersistError):
            store.save_one(self._make("a", password="secret"))

        # Index is still written even though credential write failed.
        assert {c["name"] for c in self._json()} == {"a"}

    # --- add / update / delete integration --------------------------------

    def test_update_only_touches_target(self) -> None:
        store = self._create_store()
        store.save_all([self._make("a"), self._make("b")])
        self.creds.reset_calls()

        store.update(self._make("a", password="changed"))

        assert self.creds.set_db == ["a"]
        assert not self.creds.touched("b")
        assert self.creds.get_password("a") == "changed"

    def test_update_missing_raises(self) -> None:
        store = self._create_store()
        with pytest.raises(ValueError, match="not found"):
            store.update(self._make("ghost"))

    def test_add_only_touches_target(self) -> None:
        store = self._create_store()
        store.save_all([self._make("a")])
        self.creds.reset_calls()

        store.add(self._make("b", password="secret"))

        assert self.creds.set_db == ["b"]
        assert not self.creds.touched("a")

    def test_add_duplicate_raises(self) -> None:
        store = self._create_store()
        store.save_one(self._make("a"))
        with pytest.raises(ValueError, match="already exists"):
            store.add(self._make("a"))

    def test_delete_only_removes_target_credentials(self) -> None:
        store = self._create_store()
        store.save_all([self._make("a"), self._make("b")])
        self.creds.reset_calls()

        assert store.delete("a") is True

        # a's credentials deleted, b's credentials never rewritten.
        assert self.creds.get_password("a") is None
        assert self.creds.set_db == []
        assert {c["name"] for c in self._json()} == {"b"}
        assert self.creds.get_password("b") == "pw"

    def test_delete_missing_returns_false(self) -> None:
        store = self._create_store()
        store.save_one(self._make("a"))
        assert store.delete("ghost") is False


class TestInMemorySaveOne:
    """save_one on the in-memory store used in mock mode."""

    def _store(self):
        from sqlit.domains.connections.store.memory import InMemoryConnectionStore

        return InMemoryConnectionStore()

    def test_add_and_replace(self) -> None:
        store = self._store()
        store.save_one(ConnectionConfig(name="a", db_type="postgresql"))
        store.save_one(ConnectionConfig(name="b", db_type="postgresql"))
        store.save_one(ConnectionConfig(name="a", db_type="mysql"))

        loaded = store.load_all()
        assert {c.name for c in loaded} == {"a", "b"}
        a = next(c for c in loaded if c.name == "a")
        assert a.db_type == "mysql"

    def test_rename(self) -> None:
        store = self._store()
        store.save_one(ConnectionConfig(name="old", db_type="postgresql"))
        store.save_one(ConnectionConfig(name="new", db_type="postgresql"), previous_name="old")

        assert {c.name for c in store.load_all()} == {"new"}


class TestSaveConnectionHelper:
    """The save_connection app helper should persist via save_one."""

    def test_save_connection_uses_save_one(self) -> None:
        from sqlit.domains.connections.app.save_connection import save_connection

        class RecordingStore:
            is_persistent = True

            def __init__(self) -> None:
                self.save_one_calls: list[str] = []

            def save_one(self, connection, previous_name=None) -> None:
                self.save_one_calls.append(connection.name)

        store = RecordingStore()
        connections: list = []
        config = ConnectionConfig(name="a", db_type="postgresql")

        result = save_connection(connections, store, config)

        assert result.saved is True
        assert store.save_one_calls == ["a"]
        assert [c.name for c in connections] == ["a"]

    def test_save_connection_reports_credentials_error(self) -> None:
        from sqlit.domains.connections.app.save_connection import save_connection

        class FailingStore:
            is_persistent = True

            def save_one(self, connection, previous_name=None) -> None:
                raise CredentialsPersistError(
                    [
                        CredentialsStoreError(
                            connection_name=connection.name,
                            kind="db",
                            action="store",
                            reason=RuntimeError("boom"),
                        )
                    ]
                )

        result = save_connection([], FailingStore(), ConnectionConfig(name="a", db_type="postgresql"))

        assert result.saved is True
        assert result.warning_severity == "error"
        assert result.warning
