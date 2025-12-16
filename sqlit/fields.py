"""Field definitions for database connection forms.

This module provides UI-specific field definitions used by Textual forms.
Pure connection metadata is defined in db.schema; this module transforms
that metadata into UI widgets.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

# Re-export types from schema for backward compatibility
from .db.schema import FieldType, SelectOption

if TYPE_CHECKING:
    from .db.schema import ConnectionSchema, SchemaField


@dataclass
class FieldDefinition:
    """Definition of a form field for database connections."""

    name: str  # Maps to ConnectionConfig attribute
    label: str
    field_type: FieldType = FieldType.TEXT
    placeholder: str = ""
    required: bool = False
    default: str = ""
    options: list[SelectOption] = field(default_factory=list)  # For SELECT type
    # Function that takes current form values dict and returns True if field should be visible
    visible_when: Callable[[dict], bool] | None = None
    # Width hint: "full", "flex", or a number for fixed width
    width: str | int = "full"
    # Group fields on same row
    row_group: str | None = None
    # Whether the field should be hidden unless advanced mode is enabled
    advanced: bool = False
    # Tab to place the field in ("general", "advanced", "ssh")
    tab: str = "general"


@dataclass
class FieldGroup:
    """A group of related fields with optional visibility condition."""

    name: str
    fields: list[FieldDefinition]
    # Function that takes current form values dict and returns True if group should be visible
    visible_when: Callable[[dict], bool] | None = None


def get_common_server_fields(default_port: str, server_placeholder: str = "localhost") -> list[FieldDefinition]:
    """Get common fields for server-based databases."""
    return [
        FieldDefinition(
            name="server",
            label="Server",
            placeholder=server_placeholder,
            required=True,
            row_group="server_port",
            width="flex",
        ),
        FieldDefinition(
            name="port",
            label="Port",
            placeholder=default_port,
            default=default_port,
            row_group="server_port",
            width=12,
        ),
        FieldDefinition(
            name="database",
            label="Database",
            placeholder="(empty = browse all)",
        ),
    ]


def get_credential_fields() -> list[FieldDefinition]:
    """Get username/password fields."""
    return [
        FieldDefinition(
            name="username",
            label="Username",
            placeholder="username",
            required=True,
            row_group="credentials",
            width="flex",
        ),
        FieldDefinition(
            name="password",
            label="Password",
            field_type=FieldType.PASSWORD,
            row_group="credentials",
            width="flex",
        ),
    ]


# Transform functions: convert pure schema metadata to UI field definitions


def schema_field_to_definition(schema_field: SchemaField) -> FieldDefinition:
    """Convert a SchemaField (pure metadata) to a FieldDefinition (UI-specific).

    Args:
        schema_field: Pure connection field metadata from db.schema

    Returns:
        UI-specific FieldDefinition for Textual forms
    """
    # Convert immutable tuple of SelectOption to mutable list
    options = list(schema_field.options)

    # Determine width based on group membership
    width: str | int = "full"
    if schema_field.group == "server_port":
        width = "flex" if schema_field.name == "server" else 12
    elif schema_field.group == "credentials":
        width = "flex"

    return FieldDefinition(
        name=schema_field.name,
        label=schema_field.label,
        field_type=schema_field.field_type,
        placeholder=schema_field.placeholder,
        required=schema_field.required,
        default=schema_field.default,
        options=options,
        visible_when=schema_field.visible_when,
        width=width,
        row_group=schema_field.group,
        advanced=schema_field.advanced,
        tab=schema_field.tab,
    )


def schema_to_field_definitions(schema: ConnectionSchema) -> list[FieldDefinition]:
    """Convert a ConnectionSchema to a list of FieldDefinitions.

    Args:
        schema: Connection schema from db.schema

    Returns:
        List of UI-specific FieldDefinitions for Textual forms
    """
    return [schema_field_to_definition(f) for f in schema.fields]
