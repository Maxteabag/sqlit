"""Tests for the plaintext credentials service."""

from __future__ import annotations

from sqlit.domains.connections.app.credentials import PlaintextCredentialsService


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
