"""Validation state and logic for forms."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .db.providers import is_file_based

if TYPE_CHECKING:
    from .fields import FieldDefinition


@dataclass
class ValidationState:
    """Holds validation errors for a form."""

    errors: dict[str, str] = field(default_factory=dict)
    tab_errors: set[str] = field(default_factory=set)

    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def has_error(self, field_name: str) -> bool:
        return field_name in self.errors

    def get_error(self, field_name: str) -> str | None:
        return self.errors.get(field_name)

    def add_error(self, field_name: str, message: str) -> None:
        self.errors[field_name] = message

    def has_tab_error(self, tab_id: str) -> bool:
        return tab_id in self.tab_errors

    def add_tab_error(self, tab_id: str) -> None:
        self.tab_errors.add(tab_id)

    def clear(self) -> None:
        self.errors.clear()
        self.tab_errors.clear()


def validate_connection_form(
    name: str,
    db_type: str,
    values: dict,
    field_definitions: dict[str, FieldDefinition],
    existing_names: set[str],
    editing_name: str | None = None,
) -> ValidationState:
    """Validate connection form values.

    Args:
        name: Connection name
        db_type: Database type (mssql, postgresql, etc.)
        values: Form field values
        field_definitions: Field definitions with required flags
        existing_names: Set of existing connection names
        editing_name: If editing, the original name (to allow keeping same name)

    Returns:
        ValidationState with any errors found
    """
    state = ValidationState()

    # Validate name uniqueness
    if name in existing_names and name != editing_name:
        state.add_error("name", "Name already exists.")

    # Validate required fields
    for field_name, field_def in field_definitions.items():
        if not field_def.required:
            continue

        is_visible = True
        if field_def.visible_when:
            is_visible = field_def.visible_when(values)

        if is_visible and not values.get(field_name):
            state.add_error(field_name, "Required.")

    # File path validation for file-based databases
    if is_file_based(db_type):
        fp = values.get("file_path", "").strip()
        if not fp:
            state.add_error("file_path", "Required.")
        elif not Path(fp).exists():
            state.add_error("file_path", "File not found.")

    # SSH validation
    ssh_enabled = values.get("ssh_enabled") == "enabled"
    if ssh_enabled:
        if not values.get("ssh_host"):
            state.add_error("ssh_host", "Required.")
        if not values.get("ssh_username"):
            state.add_error("ssh_username", "Required.")
        if values.get("ssh_auth_type") == "key" and not values.get("ssh_key_path"):
            state.add_error("ssh_key_path", "Required for key authentication.")

    return state
