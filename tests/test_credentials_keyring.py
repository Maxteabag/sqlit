"""Tests for the keyring credentials service."""

from __future__ import annotations

from unittest.mock import MagicMock

from sqlit.domains.connections.app.credentials import (
    CredentialsStoreError,
    KEYRING_SERVICE_NAME,
    KeyringCredentialsService,
)


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

    def test_keyring_error_on_set_raises(self) -> None:
        """Test that keyring errors on set raise a storage error."""
        service, mock_keyring = self._create_service_with_mock_keyring()
        mock_keyring.set_password.side_effect = Exception("Keyring error")

        try:
            service.set_password("test_conn", "password")
        except CredentialsStoreError:
            return
        raise AssertionError("Expected CredentialsStoreError")
