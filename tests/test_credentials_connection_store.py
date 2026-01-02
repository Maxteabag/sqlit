"""Tests for ConnectionStore integration with credentials service."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from sqlit.domains.connections.app.credentials import (
    PlaintextCredentialsService,
    reset_credentials_service,
    set_credentials_service,
)
from tests.helpers import ConnectionConfig

if TYPE_CHECKING:
    from sqlit.domains.connections.store.connections import ConnectionStore


class TestConnectionStoreWithCredentials:
    """Integration tests for ConnectionStore with credentials service."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.creds_service = PlaintextCredentialsService()
        set_credentials_service(self.creds_service)

    def teardown_method(self) -> None:
        """Clean up after tests."""
        reset_credentials_service()
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_store(self) -> ConnectionStore:
        """Create a ConnectionStore with the temp directory."""
        from sqlit.domains.connections.store.connections import ConnectionStore
        from sqlit.shared.core.store import JSONFileStore

        # Create a subclass that uses our temp path
        class TempConnectionStore(ConnectionStore):
            def __init__(self, tmpdir: str, creds_service):
                # Don't call parent __init__, just set up manually
                JSONFileStore.__init__(self, Path(tmpdir) / "connections.json")
                self._credentials_service = creds_service

        return TempConnectionStore(self.tmpdir, self.creds_service)

    def test_save_removes_passwords_from_json(self) -> None:
        """Test that saving connections removes passwords from JSON file."""
        store = self._create_store()

        config = ConnectionConfig(
            name="test_db",
            db_type="postgresql",
            server="localhost",
            username="user",
            password="secret_password",
            ssh_enabled=True,
            ssh_host="bastion",
            ssh_username="ssh_user",
            ssh_password="ssh_secret",
        )

        store.save_all([config])

        # Read the JSON file directly
        json_path = Path(self.tmpdir) / "connections.json"
        with open(json_path) as f:
            saved_data = json.load(f)
        if isinstance(saved_data, dict):
            saved_data = saved_data.get("connections", [])

        # Passwords should be null in JSON (indicating "load from credentials service")
        assert saved_data[0]["endpoint"]["password"] is None
        assert saved_data[0]["tunnel"]["password"] is None

        # But should be in the credentials service
        assert self.creds_service.get_password("test_db") == "secret_password"
        assert self.creds_service.get_ssh_password("test_db") == "ssh_secret"

    def test_load_restores_passwords_from_credentials_service(self) -> None:
        """Test that loading connections restores passwords."""
        # Set up credentials in the service
        self.creds_service.set_password("test_db", "secret_password")
        self.creds_service.set_ssh_password("test_db", "ssh_secret")

        # Write a config file with null passwords (indicates "load from credentials service")
        json_path = Path(self.tmpdir) / "connections.json"
        with open(json_path, "w") as f:
            json.dump(
                [
                    {
                        "name": "test_db",
                        "db_type": "postgresql",
                        "server": "localhost",
                        "username": "user",
                        "password": None,  # null = load from credentials service
                        "ssh_password": None,  # null = load from credentials service
                        "port": "5432",
                        "database": "",
                        "auth_type": "sql",
                        "trusted_connection": False,
                        "file_path": "",
                        "ssh_enabled": True,
                        "ssh_host": "bastion",
                        "ssh_port": "22",
                        "ssh_username": "ssh_user",
                        "ssh_auth_type": "key",
                        "ssh_key_path": "",
                        "supabase_region": "",
                        "supabase_project_id": "",
                    }
                ],
                f,
            )

        store = self._create_store()
        loaded = store.load_all()

        assert len(loaded) == 1
        assert loaded[0].tcp_endpoint.password == "secret_password"
        assert loaded[0].tunnel is not None
        assert loaded[0].tunnel.password == "ssh_secret"

    def test_delete_removes_credentials(self) -> None:
        """Test that deleting a connection removes credentials."""
        store = self._create_store()

        config = ConnectionConfig(
            name="test_db",
            db_type="postgresql",
            server="localhost",
            username="user",
            password="secret",
            ssh_enabled=True,
            ssh_host="bastion",
            ssh_username="ssh_user",
            ssh_password="ssh_secret",
        )

        store.save_all([config])

        # Verify credentials exist
        assert self.creds_service.get_password("test_db") == "secret"
        assert self.creds_service.get_ssh_password("test_db") == "ssh_secret"

        # Delete the connection
        store.delete("test_db")

        # Credentials should be gone
        assert self.creds_service.get_password("test_db") is None
        assert self.creds_service.get_ssh_password("test_db") is None

    def test_empty_password_is_stored(self) -> None:
        """Test that empty password is stored (explicitly set to empty).

        Empty string means the user explicitly set an empty password,
        which is valid for databases supporting passwordless auth.
        None means "not set" which would trigger a prompt.
        """
        store = self._create_store()

        # Create config with empty password (explicitly empty, e.g., CockroachDB insecure)
        config = ConnectionConfig(
            name="test_db",
            db_type="postgresql",
            server="localhost",
            username="user",
            password="",  # Empty = explicitly empty, no prompt
        )

        store.save_all([config])

        # Load and verify password is still empty
        loaded = store.load_all()
        assert loaded[0].tcp_endpoint.password == ""

        # Credentials service should have empty string stored
        assert self.creds_service.get_password("test_db") == ""

    def test_none_password_means_prompt_on_connect(self) -> None:
        """Test that None password means prompt on connect."""
        store = self._create_store()

        # Create config with None password (user wants to be prompted)
        config = ConnectionConfig(
            name="test_db",
            db_type="postgresql",
            server="localhost",
            username="user",
            password=None,  # None = prompt on connect
        )

        store.save_all([config])

        # Load and verify password is still None
        loaded = store.load_all()
        assert loaded[0].tcp_endpoint.password is None

        # Credentials service should not have a password
        assert self.creds_service.get_password("test_db") is None

    def test_migration_from_plaintext_preserves_existing_passwords(self) -> None:
        """Test that existing plaintext passwords in JSON are preserved during migration."""
        # Write a config file WITH passwords (simulating old format)
        json_path = Path(self.tmpdir) / "connections.json"
        with open(json_path, "w") as f:
            json.dump(
                [
                    {
                        "name": "legacy_db",
                        "db_type": "postgresql",
                        "server": "localhost",
                        "username": "user",
                        "password": "legacy_password",  # Old plaintext password
                        "ssh_password": "legacy_ssh",
                        "port": "5432",
                        "database": "",
                        "auth_type": "sql",
                        "trusted_connection": False,
                        "file_path": "",
                        "ssh_enabled": True,
                        "ssh_host": "bastion",
                        "ssh_port": "22",
                        "ssh_username": "user",
                        "ssh_auth_type": "password",
                        "ssh_key_path": "",
                        "supabase_region": "",
                        "supabase_project_id": "",
                    }
                ],
                f,
            )

        store = self._create_store()
        loaded = store.load_all()

        # Legacy passwords from JSON should be loaded
        assert loaded[0].tcp_endpoint.password == "legacy_password"
        assert loaded[0].tunnel is not None
        assert loaded[0].tunnel.password == "legacy_ssh"

        # Re-save to migrate to keyring
        store.save_all(loaded)

        # Now passwords should be in keyring
        assert self.creds_service.get_password("legacy_db") == "legacy_password"
        assert self.creds_service.get_ssh_password("legacy_db") == "legacy_ssh"

        # And JSON should be clean (null indicates load from credentials service)
        with open(json_path) as f:
            saved_data = json.load(f)
        if isinstance(saved_data, dict):
            saved_data = saved_data.get("connections", [])
        assert saved_data[0]["endpoint"]["password"] is None
        assert saved_data[0]["tunnel"]["password"] is None
