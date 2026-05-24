"""Connection schema for osquery."""

from sqlit.domains.connections.providers.schema_helpers import (
    ConnectionSchema,
    FieldType,
    SchemaField,
    SelectOption,
)


def _connection_mode_is_socket(v: dict) -> bool:
    return v.get("connection_mode") == "socket"


def _connection_mode_is_spawn(v: dict) -> bool:
    return v.get("connection_mode", "spawn") == "spawn"


SCHEMA = ConnectionSchema(
    db_type="osquery",
    display_name="osquery",
    fields=(
        SchemaField(
            name="connection_mode",
            label="Connection Mode",
            field_type=FieldType.SELECT,
            options=(
                SelectOption("spawn", "Spawn Instance (embedded)"),
                SelectOption("socket", "Connect to Socket"),
            ),
            default="spawn",
        ),
        SchemaField(
            name="socket_path",
            label="Socket Path",
            placeholder="/var/osquery/osquery.em",
            required=False,
            visible_when=_connection_mode_is_socket,
            description="Path to osqueryd extension socket",
        ),
        SchemaField(
            name="binary_path",
            label="osqueryd Binary Path",
            placeholder="/usr/bin/osqueryd",
            required=False,
            visible_when=_connection_mode_is_spawn,
            description="Path to osqueryd binary. Leave blank for the platform default.",
        ),
    ),
    supports_ssh=False,
    is_file_based=False,
    default_port="",
    requires_auth=False,
)
