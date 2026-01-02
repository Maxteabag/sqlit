"""Unit tests for validation logic (no UI required)."""

from sqlit.domains.connections.ui.fields import FieldDefinition
from sqlit.domains.connections.ui.validation import ValidationState, validate_connection_form


class TestValidationState:
    def test_empty_state_is_valid(self):
        state = ValidationState()
        assert state.is_valid()
        assert not state.has_error("any_field")

    def test_add_error_makes_invalid(self):
        state = ValidationState()
        state.add_error("field", "Error message")
        assert not state.is_valid()
        assert state.has_error("field")
        assert state.get_error("field") == "Error message"

    def test_clear_removes_errors(self):
        state = ValidationState()
        state.add_error("field", "Error")
        state.clear()
        assert state.is_valid()


class TestValidateConnectionForm:
    def test_mssql_requires_server_and_username(self):
        field_defs = {
            "server": FieldDefinition(name="server", label="Server", required=True),
            "username": FieldDefinition(name="username", label="Username", required=True),
        }

        state = validate_connection_form(
            name="test",
            db_type="mssql",
            values={},
            field_definitions=field_defs,
            existing_names=set(),
        )

        assert not state.is_valid()
        assert state.has_error("server")
        assert state.has_error("username")

    def test_valid_mssql_connection(self):
        field_defs = {
            "server": FieldDefinition(name="server", label="Server", required=True),
            "username": FieldDefinition(name="username", label="Username", required=True),
        }

        state = validate_connection_form(
            name="test",
            db_type="mssql",
            values={"server": "localhost", "username": "sa"},
            field_definitions=field_defs,
            existing_names=set(),
        )

        assert state.is_valid()

    def test_duplicate_name_rejected(self):
        state = validate_connection_form(
            name="existing",
            db_type="mssql",
            values={"server": "localhost", "username": "sa"},
            field_definitions={},
            existing_names={"existing", "other"},
        )

        assert not state.is_valid()
        assert state.has_error("name")
        assert "already exists" in state.get_error("name")

    def test_editing_allows_same_name(self):
        state = validate_connection_form(
            name="existing",
            db_type="mssql",
            values={"server": "localhost", "username": "sa"},
            field_definitions={},
            existing_names={"existing"},
            editing_name="existing",
        )

        assert state.is_valid()

    def test_sqlite_requires_existing_file(self, tmp_path):
        state = validate_connection_form(
            name="test",
            db_type="sqlite",
            values={"file_path": "/nonexistent/path.db"},
            field_definitions={},
            existing_names=set(),
        )

        assert not state.is_valid()
        assert state.has_error("file_path")
        assert "not found" in state.get_error("file_path")

    def test_sqlite_valid_with_existing_file(self, tmp_path):
        db_file = tmp_path / "test.db"
        db_file.touch()

        state = validate_connection_form(
            name="test",
            db_type="sqlite",
            values={"file_path": str(db_file)},
            field_definitions={},
            existing_names=set(),
        )

        assert state.is_valid()

    def test_ssh_validation_when_enabled(self):
        state = validate_connection_form(
            name="test",
            db_type="mssql",
            values={"server": "localhost", "username": "sa", "ssh_enabled": "enabled"},
            field_definitions={},
            existing_names=set(),
        )

        assert not state.is_valid()
        assert state.has_error("ssh_host")
        assert state.has_error("ssh_username")

    def test_ssh_key_required_for_key_auth(self):
        state = validate_connection_form(
            name="test",
            db_type="mssql",
            values={
                "server": "localhost",
                "username": "sa",
                "ssh_enabled": "enabled",
                "ssh_host": "bastion.example.com",
                "ssh_username": "user",
                "ssh_auth_type": "key",
            },
            field_definitions={},
            existing_names=set(),
        )

        assert not state.is_valid()
        assert state.has_error("ssh_key_path")
