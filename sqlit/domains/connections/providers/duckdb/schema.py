"""Connection schema for DuckDB."""

from sqlit.domains.connections.providers.schema_helpers import ConnectionSchema, _file_path_field

SCHEMA = ConnectionSchema(
    db_type="duckdb",
    display_name="DuckDB",
    fields=(_file_path_field("/path/to/database.duckdb"),),
    supports_ssh=False,
    is_file_based=True,
)
