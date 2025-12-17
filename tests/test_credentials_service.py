"""Tests for the credentials service."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sqlit.config import ConnectionConfig
from sqlit.services.credentials import (
    KEYRING_SERVICE_NAME,
    CredentialsService,
    KeyringCredentialsService,
    PlaintextFileCredentialsService,
    PlaintextCredentialsService,
    get_credentials_service,
    reset_credentials_service,
    set_credentials_service,
)


class TestPlaintextCredentialsService:
    """Tests for PlaintextCredentialsService."""

    def test_set_and_get_password(self) -> None:
        """Test setting and getting database password."""
        service = PlaintextCredentialsService()
        service.set_password("test_conn", "my_password")
        assert service.get_password("test_conn") == "my_password"

    def test_get_password_not_found(self) -> None:
        """Test getting a password that doesn't exist."""
        service = PlaintextCredentialsService()
        assert service.get_password("nonexistent") is None

    def test_delete_password(self) -> None:
        """Test deleting a password."""
        service = PlaintextCredentialsService()
        service.set_password("test_conn", "my_password")
        service.delete_password("test_conn")
        assert service.get_password("test_conn") is None

    def test_delete_nonexistent_password(self) -> None:
        """Test deleting a password that doesn't exist (should not raise)."""
        service = PlaintextCredentialsService()
        service.delete_password("nonexistent")  # Should not raise

    def test_set_and_get_ssh_password(self) -> None:
        """Test setting and getting SSH password."""
        service = PlaintextCredentialsService()
        service.set_ssh_password("test_conn", "ssh_pass")
        assert service.get_ssh_password("test_conn") == "ssh_pass"

    def test_get_ssh_password_not_found(self) -> None:
        """Test getting an SSH password that doesn't exist."""
        service = PlaintextCredentialsService()
        assert service.get_ssh_password("nonexistent") is None

    def test_delete_ssh_password(self) -> None:
        """Test deleting an SSH password."""
        service = PlaintextCredentialsService()
        service.set_ssh_password("test_conn", "ssh_pass")
        service.delete_ssh_password("test_conn")
        assert service.get_ssh_password("test_conn") is None

    def test_set_empty_password_stores_empty(self) -> None:
        """Test that setting an empty password stores it (not deletes).

        Empty string means "explicitly set to empty" which is valid for
        databases that support passwordless auth (e.g., CockroachDB insecure mode).
        """
        service = PlaintextCredentialsService()
        service.set_password("test_conn", "password")
        service.set_password("test_conn", "")
        assert service.get_password("test_conn") == ""

    def test_set_empty_ssh_password_stores_empty(self) -> None:
        """Test that setting an empty SSH password stores it (not deletes).

        Empty string means "explicitly set to empty" which is valid for
        some SSH configurations.
        """
        service = PlaintextCredentialsService()
        service.set_ssh_password("test_conn", "password")
        service.set_ssh_password("test_conn", "")
        assert service.get_ssh_password("test_conn") == ""

    def test_set_none_password_deletes(self) -> None:
        """Test that setting None deletes the password."""
        service = PlaintextCredentialsService()
        service.set_password("test_conn", "password")
        service.set_password("test_conn", None)
        assert service.get_password("test_conn") is None

    def test_set_none_ssh_password_deletes(self) -> None:
        """Test that setting None deletes the SSH password."""
        service = PlaintextCredentialsService()
        service.set_ssh_password("test_conn", "password")
        service.set_ssh_password("test_conn", None)
        assert service.get_ssh_password("test_conn") is None

    def test_rename_connection(self) -> None:
        """Test renaming a connection moves credentials."""
        service = PlaintextCredentialsService()
        service.set_password("old_name", "db_pass")
        service.set_ssh_password("old_name", "ssh_pass")

        service.rename_connection("old_name", "new_name")

        # Old credentials should be gone
        assert service.get_password("old_name") is None
        assert service.get_ssh_password("old_name") is None

        # New credentials should exist
        assert service.get_password("new_name") == "db_pass"
        assert service.get_ssh_password("new_name") == "ssh_pass"

    def test_delete_all_for_connection(self) -> None:
        """Test deleting all credentials for a connection."""
        service = PlaintextCredentialsService()
        service.set_password("test_conn", "db_pass")
        service.set_ssh_password("test_conn", "ssh_pass")

        service.delete_all_for_connection("test_conn")

        assert service.get_password("test_conn") is None
        assert service.get_ssh_password("test_conn") is None

    def test_multiple_connections(self) -> None:
        """Test storing credentials for multiple connections."""
        service = PlaintextCredentialsService()
        service.set_password("conn1", "pass1")
        service.set_password("conn2", "pass2")
        service.set_ssh_password("conn1", "ssh1")
        service.set_ssh_password("conn2", "ssh2")

        assert service.get_password("conn1") == "pass1"
        assert service.get_password("conn2") == "pass2"
        assert service.get_ssh_password("conn1") == "ssh1"
        assert service.get_ssh_password("conn2") == "ssh2"


class TestKeyringCredentialsService:
    """Tests for KeyringCredentialsService."""

    def _create_service_with_mock_keyring(self) -> tuple[KeyringCredentialsService, MagicMock]:
        """Create a service with a mock keyring injected."""
        service = KeyringCredentialsService()
        mock_keyring = MagicMock()
        service._keyring = mock_keyring
        return service, mock_keyring

    def test_lazy_loading(self) -> None:
        """Test that keyring is lazy-loaded."""
        service = KeyringCredentialsService()
        assert service._keyring is None

    def test_make_key(self) -> None:
        """Test key generation for keyring storage."""
        service = KeyringCredentialsService()
        assert service._make_key("my_conn", "db") == "my_conn:db"
        assert service._make_key("my_conn", "ssh") == "my_conn:ssh"

    def test_set_password(self) -> None:
        """Test setting password via keyring."""
        service, mock_keyring = self._create_service_with_mock_keyring()

        service.set_password("test_conn", "my_password")

        mock_keyring.set_password.assert_called_once_with(
            KEYRING_SERVICE_NAME, "test_conn:db", "my_password"
        )

    def test_get_password(self) -> None:
        """Test getting password via keyring."""
        service, mock_keyring = self._create_service_with_mock_keyring()
        mock_keyring.get_password.return_value = "stored_password"

        result = service.get_password("test_conn")

        assert result == "stored_password"
        mock_keyring.get_password.assert_called_once_with(
            KEYRING_SERVICE_NAME, "test_conn:db"
        )

    def test_delete_password(self) -> None:
        """Test deleting password via keyring."""
        service, mock_keyring = self._create_service_with_mock_keyring()

        service.delete_password("test_conn")

        mock_keyring.delete_password.assert_called_once_with(
            KEYRING_SERVICE_NAME, "test_conn:db"
        )

    def test_set_ssh_password(self) -> None:
        """Test setting SSH password via keyring."""
        service, mock_keyring = self._create_service_with_mock_keyring()

        service.set_ssh_password("test_conn", "ssh_pass")

        mock_keyring.set_password.assert_called_once_with(
            KEYRING_SERVICE_NAME, "test_conn:ssh", "ssh_pass"
        )

    def test_get_ssh_password(self) -> None:
        """Test getting SSH password via keyring."""
        service, mock_keyring = self._create_service_with_mock_keyring()
        mock_keyring.get_password.return_value = "ssh_stored"

        result = service.get_ssh_password("test_conn")

        assert result == "ssh_stored"
        mock_keyring.get_password.assert_called_once_with(
            KEYRING_SERVICE_NAME, "test_conn:ssh"
        )

    def test_delete_ssh_password(self) -> None:
        """Test deleting SSH password via keyring."""
        service, mock_keyring = self._create_service_with_mock_keyring()

        service.delete_ssh_password("test_conn")

        mock_keyring.delete_password.assert_called_once_with(
            KEYRING_SERVICE_NAME, "test_conn:ssh"
        )

    def test_set_empty_password_stores_empty(self) -> None:
        """Test that setting empty password stores it (not deletes)."""
        service, mock_keyring = self._create_service_with_mock_keyring()

        service.set_password("test_conn", "")

        mock_keyring.set_password.assert_called_once_with(
            KEYRING_SERVICE_NAME, "test_conn:db", ""
        )

    def test_set_none_password_deletes(self) -> None:
        """Test that setting None password calls delete."""
        service, mock_keyring = self._create_service_with_mock_keyring()

        service.set_password("test_conn", None)

        mock_keyring.delete_password.assert_called_once_with(
            KEYRING_SERVICE_NAME, "test_conn:db"
        )

    def test_keyring_error_returns_none(self) -> None:
        """Test that keyring errors return None for get operations."""
        service, mock_keyring = self._create_service_with_mock_keyring()
        mock_keyring.get_password.side_effect = Exception("Keyring error")

        result = service.get_password("test_conn")
        assert result is None

    def test_keyring_error_on_set_silently_fails(self) -> None:
        """Test that keyring errors on set are silently caught."""
        service, mock_keyring = self._create_service_with_mock_keyring()
        mock_keyring.set_password.side_effect = Exception("Keyring error")

        # Should not raise
        service.set_password("test_conn", "password")


class TestGlobalCredentialsService:
    """Tests for global credentials service functions."""

    def teardown_method(self) -> None:
        """Reset global service after each test."""
        reset_credentials_service()

    def test_set_and_get_service(self) -> None:
        """Test setting and getting the global service."""
        service = PlaintextCredentialsService()
        set_credentials_service(service)
        assert get_credentials_service() is service

    def test_reset_service(self) -> None:
        """Test resetting the global service."""
        service = PlaintextCredentialsService()
        set_credentials_service(service)
        reset_credentials_service()

        # Should create a new service
        new_service = get_credentials_service()
        assert new_service is not service

    @patch("sqlit.services.credentials.KeyringCredentialsService")
    @patch("sqlit.services.credentials.is_keyring_usable", return_value=True)
    def test_default_service_is_keyring(self, _mock_usable: MagicMock, mock_keyring_class: MagicMock) -> None:
        """Test that default service is keyring-based."""
        mock_instance = MagicMock()
        mock_keyring_class.return_value = mock_instance

        service = get_credentials_service()

        assert service is mock_instance

    @patch("sqlit.services.credentials.is_keyring_usable", return_value=False)
    @patch("sqlit.stores.settings.load_settings", return_value={})
    def test_fallback_to_in_memory_when_no_consent(
        self, _mock_settings: MagicMock, _mock_usable: MagicMock
    ) -> None:
        """Test fallback to in-memory plaintext when keyring isn't usable and consent not recorded."""
        reset_credentials_service()
        service = get_credentials_service()
        assert isinstance(service, PlaintextCredentialsService)

    @patch("sqlit.services.credentials.is_keyring_usable", return_value=False)
    @patch("sqlit.stores.settings.load_settings", return_value={"allow_plaintext_credentials": True})
    def test_plaintext_file_when_consent_recorded(
        self, _mock_settings: MagicMock, _mock_usable: MagicMock
    ) -> None:
        """Test fallback to plaintext file store when user consent is recorded."""
        reset_credentials_service()
        service = get_credentials_service()
        assert isinstance(service, PlaintextFileCredentialsService)


def test_plaintext_file_credentials_service_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("sqlit.services.credentials.CONFIG_DIR", tmp_path)
    service = PlaintextFileCredentialsService()
    service.set_password("conn", "dbpass")
    service.set_ssh_password("conn", "sshpass")
    assert service.get_password("conn") == "dbpass"
    assert service.get_ssh_password("conn") == "sshpass"


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

    def _create_store(self) -> "ConnectionStore":
        """Create a ConnectionStore with the temp directory."""
        from sqlit.stores.base import JSONFileStore
        from sqlit.stores.connections import ConnectionStore

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
            ssh_password="ssh_secret",
        )

        store.save_all([config])

        # Read the JSON file directly
        json_path = Path(self.tmpdir) / "connections.json"
        with open(json_path) as f:
            saved_data = json.load(f)

        # Passwords should be null in JSON (indicating "load from credentials service")
        assert saved_data[0]["password"] is None
        assert saved_data[0]["ssh_password"] is None

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
                        "driver": "ODBC Driver 18 for SQL Server",
                        "trusted_connection": False,
                        "file_path": "",
                        "ssh_enabled": False,
                        "ssh_host": "",
                        "ssh_port": "22",
                        "ssh_username": "",
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
        assert loaded[0].password == "secret_password"
        assert loaded[0].ssh_password == "ssh_secret"

    def test_delete_removes_credentials(self) -> None:
        """Test that deleting a connection removes credentials."""
        store = self._create_store()

        config = ConnectionConfig(
            name="test_db",
            db_type="postgresql",
            server="localhost",
            password="secret",
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
        assert loaded[0].password == ""

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
        assert loaded[0].password is None

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
                        "driver": "ODBC Driver 18 for SQL Server",
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
        assert loaded[0].password == "legacy_password"
        assert loaded[0].ssh_password == "legacy_ssh"

        # Re-save to migrate to keyring
        store.save_all(loaded)

        # Now passwords should be in keyring
        assert self.creds_service.get_password("legacy_db") == "legacy_password"
        assert self.creds_service.get_ssh_password("legacy_db") == "legacy_ssh"

        # And JSON should be clean (null indicates load from credentials service)
        with open(json_path) as f:
            saved_data = json.load(f)
        assert saved_data[0]["password"] is None
        assert saved_data[0]["ssh_password"] is None
