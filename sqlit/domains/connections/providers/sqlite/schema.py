"""Connection schema for SQLite."""

from sqlit.domains.connections.providers.schema_helpers import ConnectionSchema, _file_path_field

SCHEMA = ConnectionSchema(
    db_type="sqlite",
    display_name="SQLite",
    fields=(_file_path_field("/path/to/database.db"),),
    supports_ssh=False,
    is_file_based=True,
)
