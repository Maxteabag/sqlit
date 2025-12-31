"""Tests for global credentials service selection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sqlit.domains.connections.app.credentials import (
    PlaintextCredentialsService,
    PlaintextFileCredentialsService,
    get_credentials_service,
    reset_credentials_service,
    set_credentials_service,
)


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

    @patch("sqlit.domains.connections.app.credentials.KeyringCredentialsService")
    @patch("sqlit.domains.connections.app.credentials.is_keyring_usable", return_value=True)
    def test_default_service_is_keyring(self, _mock_usable: MagicMock, mock_keyring_class: MagicMock) -> None:
        """Test that default service is keyring-based."""
        mock_instance = MagicMock()
        mock_keyring_class.return_value = mock_instance

        service = get_credentials_service()

        assert service is mock_instance

    @patch("sqlit.domains.connections.app.credentials.is_keyring_usable", return_value=False)
    @patch("sqlit.domains.shell.store.settings.SettingsStore.get_instance")
    def test_fallback_to_in_memory_when_no_consent(
        self, mock_store_get: MagicMock, _mock_usable: MagicMock
    ) -> None:
        """Test fallback to in-memory plaintext when keyring isn't usable and consent not recorded."""
        mock_store = MagicMock()
        mock_store.load_all.return_value = {}
        mock_store_get.return_value = mock_store
        reset_credentials_service()
        service = get_credentials_service()
        assert isinstance(service, PlaintextCredentialsService)

    @patch("sqlit.domains.connections.app.credentials.is_keyring_usable", return_value=False)
    @patch("sqlit.domains.shell.store.settings.SettingsStore.get_instance")
    def test_plaintext_file_when_consent_recorded(
        self, mock_store_get: MagicMock, _mock_usable: MagicMock
    ) -> None:
        """Test fallback to plaintext file store when user consent is recorded."""
        mock_store = MagicMock()
        mock_store.load_all.return_value = {"allow_plaintext_credentials": True}
        mock_store_get.return_value = mock_store
        reset_credentials_service()
        service = get_credentials_service()
        assert isinstance(service, PlaintextFileCredentialsService)


def test_plaintext_file_credentials_service_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("sqlit.domains.connections.app.credentials.CONFIG_DIR", tmp_path)
    service = PlaintextFileCredentialsService()
    service.set_password("conn", "dbpass")
    service.set_ssh_password("conn", "sshpass")
    assert service.get_password("conn") == "dbpass"
    assert service.get_ssh_password("conn") == "sshpass"
