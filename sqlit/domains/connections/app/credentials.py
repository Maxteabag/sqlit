"""Credentials service for secure password storage.

This module provides an abstraction for storing and retrieving credentials
securely. The default implementation uses the OS keyring (macOS Keychain,
Windows Credential Locker, Linux Secret Service). A plaintext fallback
is provided for environments without keyring support (with user consent),
and an in-memory fallback is provided for testing.
"""

from __future__ import annotations

import secrets
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from sqlit.shared.core.store import CONFIG_DIR, JSONFileStore

if TYPE_CHECKING:
    pass

# Service name used for keyring storage
KEYRING_SERVICE_NAME = "sqlit"

# Settings key controlling whether plaintext credential storage is allowed.
ALLOW_PLAINTEXT_CREDENTIALS_SETTING = "allow_plaintext_credentials"


def is_keyring_usable() -> bool:
    """Return True if a usable keyring backend appears to be available."""
    try:
        import keyring
    except ImportError:
        return False

    try:
        backend = keyring.get_keyring()
        module_name = getattr(backend, "__module__", "") or ""
        priority = getattr(backend, "priority", None)
        if "keyring.backends.fail" in module_name:
            return False
        if isinstance(priority, (int, float)) and priority <= 0:
            return False

        # Minimal probe: read-only call to surface obvious misconfiguration.
        keyring.get_password(KEYRING_SERVICE_NAME, f"probe:{secrets.token_hex(8)}")
        return True
    except Exception:
        return False

class CredentialsService(ABC):
    """Abstract base class for credential storage services."""

    @abstractmethod
    def get_password(self, connection_name: str) -> str | None:
        """Retrieve the database password for a connection.

        Args:
            connection_name: The unique name of the connection.

        Returns:
            The password string, or None if not found.
        """
        ...

    @abstractmethod
    def set_password(self, connection_name: str, password: str) -> None:
        """Store the database password for a connection.

        Args:
            connection_name: The unique name of the connection.
            password: The password to store.
        """
        ...

    @abstractmethod
    def delete_password(self, connection_name: str) -> None:
        """Delete the database password for a connection.

        Args:
            connection_name: The unique name of the connection.
        """
        ...

    @abstractmethod
    def get_ssh_password(self, connection_name: str) -> str | None:
        """Retrieve the SSH password for a connection.

        Args:
            connection_name: The unique name of the connection.

        Returns:
            The SSH password string, or None if not found.
        """
        ...

    @abstractmethod
    def set_ssh_password(self, connection_name: str, password: str) -> None:
        """Store the SSH password for a connection.

        Args:
            connection_name: The unique name of the connection.
            password: The SSH password to store.
        """
        ...

    @abstractmethod
    def delete_ssh_password(self, connection_name: str) -> None:
        """Delete the SSH password for a connection.

        Args:
            connection_name: The unique name of the connection.
        """
        ...

    def rename_connection(self, old_name: str, new_name: str) -> None:
        """Rename credentials when a connection is renamed.

        Args:
            old_name: The old connection name.
            new_name: The new connection name.
        """
        # Get existing credentials
        db_password = self.get_password(old_name)
        ssh_password = self.get_ssh_password(old_name)

        # Store under new name
        if db_password:
            self.set_password(new_name, db_password)
        if ssh_password:
            self.set_ssh_password(new_name, ssh_password)

        # Delete old credentials
        self.delete_password(old_name)
        self.delete_ssh_password(old_name)

    def delete_all_for_connection(self, connection_name: str) -> None:
        """Delete all credentials for a connection.

        Args:
            connection_name: The unique name of the connection.
        """
        self.delete_password(connection_name)
        self.delete_ssh_password(connection_name)


class KeyringCredentialsService(CredentialsService):
    """Credentials service using OS keyring for secure storage.

    This implementation uses the `keyring` library to store passwords
    in the OS-provided secure storage:
    - macOS: Keychain
    - Windows: Credential Locker
    - Linux: Secret Service (GNOME Keyring, KDE Wallet, etc.)

    The keyring module is lazy-loaded to avoid import overhead when
    not needed.
    """

    def __init__(self) -> None:
        self._keyring: Any | None = None

    def _get_keyring(self) -> Any:
        if self._keyring is None:
            import keyring

            self._keyring = keyring
        return self._keyring

    def _make_key(self, connection_name: str, key_type: str) -> str:
        """Create a unique key for storage.

        Args:
            connection_name: The connection name.
            key_type: Type of credential ('db' or 'ssh').

        Returns:
            A unique key string.
        """
        return f"{connection_name}:{key_type}"

    def get_password(self, connection_name: str) -> str | None:
        try:
            keyring = self._get_keyring()
            key = self._make_key(connection_name, "db")
            value = keyring.get_password(KEYRING_SERVICE_NAME, key)
            return value if isinstance(value, str) else None
        except Exception:
            return None

    def set_password(self, connection_name: str, password: str) -> None:
        if password is None:
            self.delete_password(connection_name)
            return
        try:
            keyring = self._get_keyring()
            key = self._make_key(connection_name, "db")
            keyring.set_password(KEYRING_SERVICE_NAME, key, password)
        except Exception:
            pass

    def delete_password(self, connection_name: str) -> None:
        try:
            keyring = self._get_keyring()
            key = self._make_key(connection_name, "db")
            keyring.delete_password(KEYRING_SERVICE_NAME, key)
        except Exception:
            pass

    def get_ssh_password(self, connection_name: str) -> str | None:
        try:
            keyring = self._get_keyring()
            key = self._make_key(connection_name, "ssh")
            value = keyring.get_password(KEYRING_SERVICE_NAME, key)
            return value if isinstance(value, str) else None
        except Exception:
            return None

    def set_ssh_password(self, connection_name: str, password: str) -> None:
        if password is None:
            self.delete_ssh_password(connection_name)
            return
        try:
            keyring = self._get_keyring()
            key = self._make_key(connection_name, "ssh")
            keyring.set_password(KEYRING_SERVICE_NAME, key, password)
        except Exception:
            pass

    def delete_ssh_password(self, connection_name: str) -> None:
        try:
            keyring = self._get_keyring()
            key = self._make_key(connection_name, "ssh")
            keyring.delete_password(KEYRING_SERVICE_NAME, key)
        except Exception:
            pass


class PlaintextCredentialsService(CredentialsService):
    """Credentials service storing passwords in memory (for testing).

    WARNING: This implementation stores passwords in memory only.
    It does NOT persist passwords. Use only for testing.
    """

    def __init__(self) -> None:
        self._passwords: dict[str, str] = {}
        self._ssh_passwords: dict[str, str] = {}

    def get_password(self, connection_name: str) -> str | None:
        return self._passwords.get(connection_name)

    def set_password(self, connection_name: str, password: str) -> None:
        if password is not None:
            self._passwords[connection_name] = password
        else:
            self.delete_password(connection_name)

    def delete_password(self, connection_name: str) -> None:
        self._passwords.pop(connection_name, None)

    def get_ssh_password(self, connection_name: str) -> str | None:
        return self._ssh_passwords.get(connection_name)

    def set_ssh_password(self, connection_name: str, password: str) -> None:
        if password is not None:
            self._ssh_passwords[connection_name] = password
        else:
            self.delete_ssh_password(connection_name)

    def delete_ssh_password(self, connection_name: str) -> None:
        self._ssh_passwords.pop(connection_name, None)


class PlaintextFileCredentialsService(CredentialsService):
    """Credentials service storing passwords in a local file.

    WARNING: This stores secrets in plaintext on disk. The credentials file is
    created under the config dir with restrictive permissions (0700/0600).
    """

    def __init__(self) -> None:
        self._store = JSONFileStore(CONFIG_DIR / "credentials.json")

    def _read_all(self) -> dict[str, str]:
        data = self._store._read_json()
        return data if isinstance(data, dict) else {}

    def _write_all(self, data: dict[str, str]) -> None:
        self._store._write_json(data)

    def _key(self, connection_name: str, kind: str) -> str:
        return f"{connection_name}:{kind}"

    def get_password(self, connection_name: str) -> str | None:
        return self._read_all().get(self._key(connection_name, "db"))

    def set_password(self, connection_name: str, password: str) -> None:
        if password is None:
            self.delete_password(connection_name)
            return
        data = self._read_all()
        data[self._key(connection_name, "db")] = password
        self._write_all(data)

    def delete_password(self, connection_name: str) -> None:
        data = self._read_all()
        data.pop(self._key(connection_name, "db"), None)
        self._write_all(data)

    def get_ssh_password(self, connection_name: str) -> str | None:
        return self._read_all().get(self._key(connection_name, "ssh"))

    def set_ssh_password(self, connection_name: str, password: str) -> None:
        if password is None:
            self.delete_ssh_password(connection_name)
            return
        data = self._read_all()
        data[self._key(connection_name, "ssh")] = password
        self._write_all(data)

    def delete_ssh_password(self, connection_name: str) -> None:
        data = self._read_all()
        data.pop(self._key(connection_name, "ssh"), None)
        self._write_all(data)


_credentials_service: CredentialsService | None = None


def build_credentials_service(settings_store: Any | None = None) -> CredentialsService:
    """Build a credentials service with an optional settings store."""
    if is_keyring_usable():
        return KeyringCredentialsService()

    if settings_store is None:
        from sqlit.domains.shell.store.settings import SettingsStore

        settings_store = SettingsStore.get_instance()

    settings = settings_store.load_all()
    allow_plaintext = bool(settings.get(ALLOW_PLAINTEXT_CREDENTIALS_SETTING))
    return PlaintextFileCredentialsService() if allow_plaintext else PlaintextCredentialsService()


def get_credentials_service() -> CredentialsService:
    """Get the global credentials service instance."""
    global _credentials_service
    if _credentials_service is None:
        _credentials_service = build_credentials_service()
    return _credentials_service


def set_credentials_service(service: CredentialsService | None) -> None:
    """Set the global credentials service instance.

    This is primarily useful for testing to inject a mock service.

    Args:
        service: The credentials service to use, or None to reset.
    """
    global _credentials_service
    _credentials_service = service


def reset_credentials_service() -> None:
    """Reset the credentials service to default.

    Useful for testing to ensure a clean state.
    """
    global _credentials_service
    _credentials_service = None
