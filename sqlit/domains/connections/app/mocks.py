"""Mock profiles for demo recordings and testing.

Usage:
    sqlit --mock=sqlite-demo   # Pre-configured SQLite with demo data
    sqlit --mock=empty         # Empty connections, but mock adapters available
    sqlit --mock=multi-db      # Multiple database connections
    sqlit --mock=perf-test --demo-rows=10000  # Performance testing with 10k rows
    sqlit --mock=driver-install-success --mock-missing-drivers=postgresql --mock-install=success
    sqlit --mock=driver-install-fail --mock-missing-drivers=mysql --mock-install=fail

Performance Testing:
    Use --demo-rows=COUNT with any mock profile to generate fake data.
    If Faker is installed (pip install Faker), realistic data is generated.
    Otherwise, simple placeholder data is used.

    Examples:
        sqlit --mock=perf-test --demo-rows=1000    # 1k rows
        sqlit --mock=perf-test --demo-rows=10000   # 10k rows
        sqlit --mock=sqlite-demo --demo-rows=5000  # Any profile works

Long Text Testing:
    Use --demo-long-text to generate data with long varchar columns.
    Useful for testing how the UI handles text truncation.

    Examples:
        sqlit --mock=sqlite-demo --demo-long-text             # 10 rows with long text
        sqlit --mock=sqlite-demo --demo-long-text --demo-rows=50  # 50 rows with long text
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, cast

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.providers.catalog import get_provider, get_provider_schema, get_provider_spec
from sqlit.domains.connections.providers.explorer_nodes import DefaultExplorerNodeProvider
from sqlit.domains.connections.providers.adapter_provider import AdapterConfigValidator
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderMetadata, SchemaCapabilities
from sqlit.domains.connections.providers.schema_helpers import ConnectionSchema
from sqlit.domains.connections.providers.adapters.base import ColumnInfo, DatabaseAdapter, IndexInfo, SequenceInfo, TriggerInfo


def _generate_fake_data(row_count: int) -> tuple[list[str], list[tuple]]:
    """Generate fake data rows using Faker if available, otherwise basic data.

    Args:
        row_count: Number of rows to generate.

    Returns:
        Tuple of (columns, rows).
    """
    try:
        from faker import Faker

        fake = Faker()
        Faker.seed(42)  # Reproducible results

        columns = ["id", "name", "email", "phone", "address", "created_at"]
        rows = []
        for i in range(row_count):
            rows.append((
                i + 1,
                fake.name(),
                fake.email(),
                fake.phone_number(),
                fake.address().replace("\n", ", "),
                fake.date_time().isoformat(),
            ))
        return columns, rows

    except ImportError:
        # Faker not installed - generate simple data
        columns = ["id", "name", "email", "value", "status", "created_at"]
        rows = []
        statuses = ["active", "inactive", "pending", "archived"]
        for i in range(row_count):
            rows.append((
                i + 1,
                f"User {i + 1}",
                f"user{i + 1}@example.com",
                f"{round((i * 17.5) % 1000, 2):.2f}",  # Pseudo-random values
                statuses[i % len(statuses)],
                f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
            ))
        return columns, rows


def _generate_long_text_data(row_count: int) -> tuple[list[str], list[tuple]]:
    """Generate data with long varchar columns for testing truncation.

    Creates columns with varying text lengths to test UI truncation behavior.
    Useful for verifying how long text fields are displayed/truncated.

    Args:
        row_count: Number of rows to generate.

    Returns:
        Tuple of (columns, rows).
    """
    # Column lengths designed to test truncation boundaries
    text_lengths = {
        "short_text": 15,       # Short, no truncation expected
        "medium_text": 50,      # Around typical column width
        "long_text": 150,       # Definitely needs truncation
        "very_long_text": 500,  # Very long content
        "description": 300,     # Realistic long field
    }

    columns = ["id", "name"] + list(text_lengths.keys())
    rows = []

    for i in range(row_count):
        row: list[object] = [i + 1, f"Row {i + 1}"]
        for col_name, length in text_lengths.items():
            # Generate text with visible pattern showing row number and column
            base = f"[R{i + 1}:{col_name[:6]}]"
            # Fill with Lorem-style content
            filler = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
            text = base + (filler * ((length // len(filler)) + 1))
            text = text[:length]
            row.append(text)
        rows.append(tuple(row))

    return columns, rows


class MockConnection:
    """Mock database connection object."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def cursor(self) -> MockCursor:
        return MockCursor()


class MockCursor:
    """Mock database cursor."""

    def __init__(self, results: list[tuple] | None = None, columns: list[str] | None = None):
        self._results = results or [(1, "Alice"), (2, "Bob")]
        self._columns = columns or ["id", "name"]
        self.description = [(c,) for c in self._columns]

    def execute(self, query: str, params: tuple = ()) -> None:
        pass

    def fetchall(self) -> list[tuple]:
        return self._results

    def fetchone(self) -> tuple | None:
        return self._results[0] if self._results else None

    def close(self) -> None:
        pass


class MockDatabaseAdapter(DatabaseAdapter):
    """Mock database adapter for demo/testing."""

    def __init__(
        self,
        name: str = "MockDB",
        tables: list[tuple[str, str]] | None = None,
        views: list[tuple[str, str]] | None = None,
        columns: dict[str, list[ColumnInfo]] | None = None,
        indexes: list[IndexInfo] | None = None,
        triggers: list[TriggerInfo] | None = None,
        sequences: list[SequenceInfo] | None = None,
        query_results: dict[str, tuple[list[str], list[tuple]]] | None = None,
        default_schema: str = "",
        default_query_result: tuple[list[str], list[tuple]] | None = None,
        connect_result: str = "success",
        connect_error: str = "Connection failed",
        required_fields: list[str] | None = None,
        allowed_connections: list[dict[str, Any]] | None = None,
        auth_error: str = "Authentication failed",
        query_delay: float = 0.0,
        demo_rows: int = 0,
        demo_long_text: bool = False,
    ):
        self._name = name
        self._tables = tables or []
        self._views = views or []
        self._columns = columns or {}
        self._indexes = indexes or []
        self._triggers = triggers or []
        self._sequences = sequences or []
        self._query_results = query_results or {}
        self._default_schema = default_schema
        self._default_query_result = default_query_result or (
            ["id", "name"],
            [(1, "Sample Row 1"), (2, "Sample Row 2")],
        )
        self._connect_result = (connect_result or "success").strip().lower()
        self._connect_error = connect_error or "Connection failed"
        self._required_fields = required_fields or []
        self._allowed_connections = allowed_connections or []
        self._auth_error = auth_error or "Authentication failed"
        self._query_delay = query_delay
        self._demo_rows = demo_rows
        self._demo_long_text = demo_long_text

    def apply_query_delay(self, delay: float) -> None:
        if delay > 0:
            self._query_delay = delay

    def apply_demo_options(self, demo_rows: int, demo_long_text: bool) -> None:
        if demo_rows > 0:
            self._demo_rows = demo_rows
        if demo_long_text:
            self._demo_long_text = True

    @property
    def name(self) -> str:
        return self._name

    @property
    def default_schema(self) -> str:
        return self._default_schema

    @property
    def supports_multiple_databases(self) -> bool:
        return False

    @property
    def supports_stored_procedures(self) -> bool:
        return False

    def connect(self, config: ConnectionConfig) -> Any:
        if self._connect_result not in {"success", "ok", "pass"}:
            raise Exception(self._connect_error)

        if self._required_fields:
            missing = [field for field in self._required_fields if not getattr(config, field, None)]
            if missing:
                message = self._connect_error or f"Missing required fields: {', '.join(missing)}"
                raise Exception(message)

        if self._allowed_connections:
            if not any(_matches_connection_rule(config, rule) for rule in self._allowed_connections):
                raise Exception(self._auth_error)
        return MockConnection()

    def get_databases(self, conn: Any) -> list[str]:
        return []

    def get_tables(self, conn: Any, database: str | None = None) -> list[tuple[str, str]]:
        return self._tables

    def get_views(self, conn: Any, database: str | None = None) -> list[tuple[str, str]]:
        return self._views

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        if schema:
            return self._columns.get(f"{schema}.{table}", self._columns.get(table, []))
        return self._columns.get(table, [])

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        return []

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        return self._indexes

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        return self._triggers

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        return self._sequences

    def get_index_definition(
        self, conn: Any, index_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get mock index definition."""
        for idx in self._indexes:
            if idx.name == index_name:
                return {
                    "name": idx.name,
                    "table_name": idx.table_name,
                    "columns": [],
                    "is_unique": idx.is_unique,
                    "definition": f"CREATE INDEX {idx.name} ON {idx.table_name} (...)",
                }
        return {
            "name": index_name,
            "table_name": table_name,
            "columns": [],
            "is_unique": False,
            "definition": None,
        }

    def get_trigger_definition(
        self, conn: Any, trigger_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get mock trigger definition."""
        for trg in self._triggers:
            if trg.name == trigger_name:
                return {
                    "name": trg.name,
                    "table_name": trg.table_name,
                    "timing": "AFTER",
                    "event": "INSERT",
                    "definition": f"CREATE TRIGGER {trg.name} AFTER INSERT ON {trg.table_name} ...",
                }
        return {
            "name": trigger_name,
            "table_name": table_name,
            "timing": None,
            "event": None,
            "definition": None,
        }

    def get_sequence_definition(
        self, conn: Any, sequence_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get mock sequence definition."""
        for seq in self._sequences:
            if seq.name == sequence_name:
                return {
                    "name": seq.name,
                    "start_value": 1,
                    "increment": 1,
                    "min_value": 1,
                    "max_value": 9223372036854775807,
                    "cycle": False,
                }
        return {
            "name": sequence_name,
            "start_value": None,
            "increment": None,
            "min_value": None,
            "max_value": None,
            "cycle": None,
        }

    def quote_identifier(self, name: str) -> str:
        return f'"{name}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        if schema:
            return f'SELECT * FROM "{schema}"."{table}" LIMIT {limit}'
        return f'SELECT * FROM "{table}" LIMIT {limit}'

    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        """Execute a query and return (columns, rows, truncated)."""
        import time

        if self._query_delay > 0:
            time.sleep(self._query_delay)

        # Check if demo long text mode is enabled (for testing truncation)
        demo_long_text = self._demo_long_text
        demo_rows = self._demo_rows
        if not demo_long_text:
            import os

            demo_long_text = bool(os.environ.get("SQLIT_DEMO_LONG_TEXT"))
            if demo_long_text and demo_rows == 0:
                demo_rows_env = os.environ.get("SQLIT_DEMO_ROWS", "10")
                try:
                    demo_rows = int(demo_rows_env)
                except ValueError:
                    demo_rows = 10

        if demo_long_text:
            demo_row_count = demo_rows or 10
            cols, rows = _generate_long_text_data(demo_row_count)
            if max_rows and len(rows) > max_rows:
                return cols, rows[:max_rows], True
            return cols, rows, False

        # Check if demo rows mode is enabled
        if demo_rows == 0:
            import os

            demo_rows_env = os.environ.get("SQLIT_DEMO_ROWS", "")
            if demo_rows_env:
                try:
                    demo_rows = int(demo_rows_env)
                except ValueError:
                    demo_rows = 0
        if demo_rows > 0:
            cols, rows = _generate_fake_data(demo_rows)
            if max_rows and len(rows) > max_rows:
                return cols, rows[:max_rows], True
            return cols, rows, False

        query_lower = query.lower().strip()

        # Check for specific query results (case-insensitive pattern matching)
        for pattern, result in self._query_results.items():
            if pattern.lower() in query_lower:
                cols, rows = result
                if max_rows and len(rows) > max_rows:
                    return cols, rows[:max_rows], True
                return cols, rows, False

        # Return default result for any other query
        cols, rows = self._default_query_result
        if max_rows and len(rows) > max_rows:
            return cols, rows[:max_rows], True
        return cols, rows, False

    def execute_non_query(self, conn: Any, query: str) -> int:
        return 1


def build_mock_provider(db_type: str, adapter: MockDatabaseAdapter) -> DatabaseProvider:
    real_provider: DatabaseProvider | None
    try:
        real_provider = get_provider(db_type)
    except Exception:
        real_provider = None

    if real_provider is not None:
        metadata = real_provider.metadata
        schema = real_provider.schema
        driver = real_provider.driver
        docker_detector = real_provider.docker_detector
        def _display_info(config: ConnectionConfig) -> str:
            return real_provider.display_info(config)

        display_info = _display_info
    else:
        spec = None
        try:
            spec = get_provider_spec(db_type)
        except Exception:
            spec = None

        display_name = adapter.name or (spec.display_name if spec else db_type.upper())
        badge_label = spec.badge_label if spec and spec.badge_label else display_name
        metadata = ProviderMetadata(
            db_type=db_type,
            display_name=display_name,
            badge_label=badge_label,
            default_port=spec.default_port if spec else "",
            supports_ssh=spec.supports_ssh if spec else True,
            is_file_based=spec.is_file_based if spec else False,
            has_advanced_auth=spec.has_advanced_auth if spec else False,
            requires_auth=spec.requires_auth if spec else True,
            url_schemes=spec.url_schemes if spec else (),
        )
        schema = get_provider_schema(db_type) if spec else ConnectionSchema(
            db_type=db_type,
            display_name=display_name,
            fields=(),
            supports_ssh=metadata.supports_ssh,
            is_file_based=metadata.is_file_based,
            has_advanced_auth=metadata.has_advanced_auth,
            default_port=metadata.default_port,
            requires_auth=metadata.requires_auth,
        )
        driver = None
        docker_detector = None

        def _display_info(config: ConnectionConfig) -> str:
            endpoint = getattr(config, "endpoint", None)
            if endpoint and getattr(endpoint, "kind", "") == "file":
                return str(getattr(endpoint, "path", "")) or config.name
            tcp_endpoint = getattr(config, "tcp_endpoint", None)
            if tcp_endpoint is None:
                tcp_endpoint = endpoint
            if tcp_endpoint and getattr(tcp_endpoint, "kind", "") != "file":
                host = str(getattr(tcp_endpoint, "host", ""))
                port = str(getattr(tcp_endpoint, "port", ""))
                database = str(getattr(tcp_endpoint, "database", ""))
                db_part = f"/{database}" if database else ""
                port_part = f":{port}" if port else ""
                info = f"{host}{port_part}{db_part}".strip()
                if info:
                    return info
            return config.name

        display_info = _display_info

    capabilities = SchemaCapabilities(
        supports_multiple_databases=bool(getattr(adapter, "supports_multiple_databases", False)),
        supports_cross_database_queries=bool(getattr(adapter, "supports_cross_database_queries", False)),
        supports_stored_procedures=bool(getattr(adapter, "supports_stored_procedures", False)),
        supports_indexes=bool(getattr(adapter, "supports_indexes", False)),
        supports_triggers=bool(getattr(adapter, "supports_triggers", False)),
        supports_sequences=bool(getattr(adapter, "supports_sequences", False)),
        default_schema=str(getattr(adapter, "default_schema", "")),
        system_databases=frozenset(getattr(adapter, "system_databases", frozenset())),
    )

    def apply_database_override(config: ConnectionConfig, database: str | None) -> ConnectionConfig:
        override = getattr(adapter, "apply_database_override", None)
        if callable(override) and database:
            return cast(ConnectionConfig, override(config, database))
        return config

    def post_connect(conn: Any, config: ConnectionConfig) -> None:
        hook = getattr(adapter, "detect_capabilities", None)
        if callable(hook):
            hook(conn, config)

    def post_connect_warnings(config: ConnectionConfig) -> list[str]:
        getter = getattr(adapter, "get_post_connect_warnings", None)
        if callable(getter):
            return list(cast(Iterable[str], getter(config)))
        return []

    def get_auth_type(config: ConnectionConfig) -> Any | None:
        getter = getattr(adapter, "get_auth_type", None)
        if callable(getter):
            return getter(config)
        return None

    return DatabaseProvider(
        metadata=metadata,
        schema=schema,
        capabilities=capabilities,
        driver=driver,
        connection_factory=adapter,
        query_executor=adapter,
        schema_inspector=adapter,
        dialect=adapter,
        config_validator=AdapterConfigValidator(schema=schema, adapter=adapter),
        docker_detector=docker_detector,
        explorer_nodes=DefaultExplorerNodeProvider(),
        display_info=display_info,
        apply_database_override=apply_database_override,
        post_connect=post_connect,
        post_connect_warnings=post_connect_warnings,
        get_auth_type=get_auth_type,
    )


# =============================================================================
# Default Mock Adapters - used when profiles don't define their own
# =============================================================================


def create_default_sqlite_adapter() -> MockDatabaseAdapter:
    """Create a default SQLite mock adapter with demo data."""
    return MockDatabaseAdapter(
        name="SQLite",
        tables=[
            ("main", "users"),
            ("main", "products"),
            ("main", "orders"),
        ],
        views=[],
        columns={
            "users": [
                ColumnInfo("id", "INTEGER"),
                ColumnInfo("name", "TEXT"),
                ColumnInfo("email", "TEXT"),
                ColumnInfo("created_at", "TEXT"),
            ],
            "products": [
                ColumnInfo("id", "INTEGER"),
                ColumnInfo("name", "TEXT"),
                ColumnInfo("price", "REAL"),
                ColumnInfo("stock", "INTEGER"),
            ],
            "orders": [
                ColumnInfo("id", "INTEGER"),
                ColumnInfo("user_id", "INTEGER"),
                ColumnInfo("product_id", "INTEGER"),
                ColumnInfo("quantity", "INTEGER"),
                ColumnInfo("created_at", "TEXT"),
            ],
        },
        query_results={
            # Patterns use just table name - matches both "SELECT * FROM users"
            # and schema-qualified 'SELECT * FROM "main"."users"'
            "users": (
                ["id", "name", "email", "created_at"],
                [
                    (1, "Alice Johnson", "alice@example.com", "2024-01-15"),
                    (2, "Bob Smith", "bob@example.com", "2024-01-16"),
                    (3, "Charlie Brown", "charlie@example.com", "2024-01-17"),
                ],
            ),
            "products": (
                ["id", "name", "price", "stock"],
                [
                    (1, "Widget", 9.99, 100),
                    (2, "Gadget", 19.99, 50),
                    (3, "Gizmo", 29.99, 25),
                ],
            ),
            "orders": (
                ["id", "user_id", "product_id", "quantity", "created_at"],
                [
                    (1, 1, 1, 2, "2024-01-20"),
                    (2, 1, 2, 1, "2024-01-21"),
                    (3, 2, 3, 3, "2024-01-22"),
                ],
            ),
            # JOIN query results for demo
            "join users": (
                ["user", "product", "qty", "total", "order_date"],
                [
                    ("Alice Johnson", "Widget", 2, 19.98, "2024-01-20"),
                    ("Alice Johnson", "Gadget", 1, 19.99, "2024-01-21"),
                    ("Bob Smith", "Gizmo", 3, 89.97, "2024-01-22"),
                ],
            ),
            "group by": (
                ["customer", "total_orders", "total_spent"],
                [
                    ("Alice Johnson", 2, 39.97),
                    ("Bob Smith", 1, 89.97),
                ],
            ),
            "restock_urgency": (
                ["name", "price", "stock", "restock_urgency"],
                [
                    ("Gizmo", 29.99, 25, "High"),
                    ("Gadget", 19.99, 50, "Medium"),
                ],
            ),
        },
        default_schema="main",
        default_query_result=(
            ["result"],
            [("Query executed successfully",)],
        ),
    )


def create_default_postgresql_adapter() -> MockDatabaseAdapter:
    """Create a default PostgreSQL mock adapter."""
    return MockDatabaseAdapter(
        name="PostgreSQL",
        tables=[
            ("public", "users"),
            ("public", "accounts"),
        ],
        views=[],
        columns={
            "users": [
                ColumnInfo("id", "SERIAL"),
                ColumnInfo("username", "VARCHAR"),
                ColumnInfo("email", "VARCHAR"),
            ],
            "accounts": [
                ColumnInfo("id", "SERIAL"),
                ColumnInfo("user_id", "INTEGER"),
                ColumnInfo("balance", "NUMERIC"),
            ],
        },
        query_results={},
        default_schema="public",
    )


def create_default_mysql_adapter() -> MockDatabaseAdapter:
    """Create a default MySQL mock adapter."""
    return MockDatabaseAdapter(
        name="MySQL",
        tables=[
            ("", "customers"),
            ("", "orders"),
        ],
        views=[],
        columns={
            "customers": [
                ColumnInfo("id", "INT"),
                ColumnInfo("name", "VARCHAR"),
                ColumnInfo("email", "VARCHAR"),
            ],
        },
        query_results={},
        default_schema="",
    )


def create_default_supabase_adapter() -> MockDatabaseAdapter:
    """Create a default Supabase mock adapter with typical Supabase tables."""
    return MockDatabaseAdapter(
        name="Supabase",
        tables=[
            ("public", "profiles"),
            ("public", "posts"),
            ("public", "comments"),
            ("auth", "users"),
        ],
        views=[],
        columns={
            "profiles": [
                ColumnInfo("id", "UUID"),
                ColumnInfo("username", "TEXT"),
                ColumnInfo("full_name", "TEXT"),
                ColumnInfo("avatar_url", "TEXT"),
                ColumnInfo("created_at", "TIMESTAMPTZ"),
                ColumnInfo("updated_at", "TIMESTAMPTZ"),
            ],
            "posts": [
                ColumnInfo("id", "UUID"),
                ColumnInfo("user_id", "UUID"),
                ColumnInfo("title", "TEXT"),
                ColumnInfo("content", "TEXT"),
                ColumnInfo("published", "BOOLEAN"),
                ColumnInfo("created_at", "TIMESTAMPTZ"),
            ],
            "comments": [
                ColumnInfo("id", "UUID"),
                ColumnInfo("post_id", "UUID"),
                ColumnInfo("user_id", "UUID"),
                ColumnInfo("content", "TEXT"),
                ColumnInfo("created_at", "TIMESTAMPTZ"),
            ],
            "auth.users": [
                ColumnInfo("id", "UUID"),
                ColumnInfo("email", "TEXT"),
                ColumnInfo("encrypted_password", "TEXT"),
                ColumnInfo("email_confirmed_at", "TIMESTAMPTZ"),
                ColumnInfo("last_sign_in_at", "TIMESTAMPTZ"),
                ColumnInfo("created_at", "TIMESTAMPTZ"),
                ColumnInfo("updated_at", "TIMESTAMPTZ"),
            ],
        },
        query_results={
            "profiles": (
                ["id", "username", "full_name", "avatar_url", "created_at", "updated_at"],
                [
                    ("a1b2c3d4-e5f6-7890-abcd-ef1234567890", "alice_dev", "Alice Developer", "https://avatars.example.com/alice.png", "2024-01-15 10:30:00+00", "2024-01-20 14:22:00+00"),
                    ("b2c3d4e5-f6a7-8901-bcde-f12345678901", "bob_builder", "Bob Builder", "https://avatars.example.com/bob.png", "2024-01-16 11:45:00+00", "2024-01-21 09:15:00+00"),
                    ("c3d4e5f6-a7b8-9012-cdef-123456789012", "charlie_coder", "Charlie Coder", None, "2024-01-17 08:00:00+00", "2024-01-17 08:00:00+00"),
                ],
            ),
            "posts": (
                ["id", "user_id", "title", "content", "published", "created_at"],
                [
                    ("d4e5f6a7-b8c9-0123-def0-234567890123", "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "Getting Started with Supabase", "Supabase is an open source Firebase alternative...", True, "2024-01-18 12:00:00+00"),
                    ("e5f6a7b8-c9d0-1234-ef01-345678901234", "b2c3d4e5-f6a7-8901-bcde-f12345678901", "Building Real-time Apps", "Real-time functionality is built into Supabase...", True, "2024-01-19 15:30:00+00"),
                ],
            ),
            "comments": (
                ["id", "post_id", "user_id", "content", "created_at"],
                [
                    ("f6a7b8c9-d0e1-2345-f012-456789012345", "d4e5f6a7-b8c9-0123-def0-234567890123", "b2c3d4e5-f6a7-8901-bcde-f12345678901", "Great introduction!", "2024-01-18 14:00:00+00"),
                    ("a7b8c9d0-e1f2-3456-0123-567890123456", "d4e5f6a7-b8c9-0123-def0-234567890123", "c3d4e5f6-a7b8-9012-cdef-123456789012", "Very helpful, thanks!", "2024-01-18 16:30:00+00"),
                ],
            ),
            "auth.users": (
                ["id", "email", "encrypted_password", "email_confirmed_at", "last_sign_in_at", "created_at", "updated_at"],
                [
                    ("a1b2c3d4-e5f6-7890-abcd-ef1234567890", "alice@example.com", "$2a$10$...", "2024-01-15 10:35:00+00", "2024-01-22 08:00:00+00", "2024-01-15 10:30:00+00", "2024-01-22 08:00:00+00"),
                    ("b2c3d4e5-f6a7-8901-bcde-f12345678901", "bob@example.com", "$2a$10$...", "2024-01-16 12:00:00+00", "2024-01-21 09:00:00+00", "2024-01-16 11:45:00+00", "2024-01-21 09:00:00+00"),
                    ("c3d4e5f6-a7b8-9012-cdef-123456789012", "charlie@example.com", "$2a$10$...", "2024-01-17 08:05:00+00", "2024-01-20 17:30:00+00", "2024-01-17 08:00:00+00", "2024-01-20 17:30:00+00"),
                ],
            ),
        },
        default_schema="public",
        default_query_result=(
            ["result"],
            [("Query executed successfully",)],
        ),
    )


# Registry of default adapters by database type
DEFAULT_MOCK_ADAPTERS: dict[str, Callable[[], MockDatabaseAdapter]] = {
    "sqlite": create_default_sqlite_adapter,
    "postgresql": create_default_postgresql_adapter,
    "mysql": create_default_mysql_adapter,
    "supabase": create_default_supabase_adapter,
}


def get_default_mock_adapter(
    db_type: str,
    *,
    query_delay: float = 0.0,
    demo_rows: int = 0,
    demo_long_text: bool = False,
) -> MockDatabaseAdapter:
    """Get a default mock adapter for a database type."""
    factory = DEFAULT_MOCK_ADAPTERS.get(db_type)
    if factory:
        adapter = factory()
        adapter.apply_query_delay(query_delay)
        adapter.apply_demo_options(demo_rows, demo_long_text)
        return adapter
    # Fallback for unknown types
    return MockDatabaseAdapter(
        name=f"Mock{db_type.title()}",
        query_delay=query_delay,
        demo_rows=demo_rows,
        demo_long_text=demo_long_text,
    )


def _matches_connection_rule(config: ConnectionConfig, rule: dict[str, Any]) -> bool:
    for key, value in rule.items():
        if config.get_field_value(key, None) != value:
            return False
    return True


# =============================================================================
# Mock Profiles
# =============================================================================


@dataclass
class MockProfile:
    """A mock profile containing connections and adapter configuration."""

    name: str
    connections: list[ConnectionConfig] = field(default_factory=list)
    adapters: dict[str, MockDatabaseAdapter] = field(default_factory=dict)
    use_default_adapters: bool = True  # Use default adapters when profile doesn't define one
    query_delay: float = 0.0
    demo_rows: int = 0
    demo_long_text: bool = False
    _providers: dict[str, DatabaseProvider] = field(default_factory=dict, init=False, repr=False)

    def get_adapter(self, db_type: str) -> MockDatabaseAdapter:
        """Get adapter for a database type, falling back to defaults."""
        if db_type in self.adapters:
            adapter = self.adapters[db_type]
            adapter.apply_query_delay(self.query_delay)
            adapter.apply_demo_options(self.demo_rows, self.demo_long_text)
            return adapter
        if self.use_default_adapters:
            return get_default_mock_adapter(
                db_type,
                query_delay=self.query_delay,
                demo_rows=self.demo_rows,
                demo_long_text=self.demo_long_text,
            )
        return MockDatabaseAdapter(
            name=f"Mock{db_type.title()}",
            query_delay=self.query_delay,
            demo_rows=self.demo_rows,
            demo_long_text=self.demo_long_text,
        )

    def get_provider(self, db_type: str) -> DatabaseProvider:
        """Get provider for a database type, building one from mock adapters."""
        if db_type in self._providers:
            return self._providers[db_type]
        adapter = self.get_adapter(db_type)
        provider = build_mock_provider(db_type, adapter)
        self._providers[db_type] = provider
        return provider


def _create_sqlite_demo_profile() -> MockProfile:
    """Create the sqlite-demo profile with pre-configured connection."""
    connections = [
        ConnectionConfig.from_dict(
            {
                "name": "Demo SQLite",
                "db_type": "sqlite",
                "endpoint": {"kind": "file", "path": "./demo.db"},
            }
        ),
    ]

    return MockProfile(
        name="sqlite-demo",
        connections=connections,
        adapters={"sqlite": create_default_sqlite_adapter()},
        use_default_adapters=True,
    )


def _create_empty_profile() -> MockProfile:
    """Create an empty profile with no connections but default mock adapters."""
    return MockProfile(
        name="empty",
        connections=[],
        adapters={},
        use_default_adapters=True,  # Still use default mock adapters when connecting
    )


def _create_multi_db_profile() -> MockProfile:
    """Create a profile with multiple database types."""
    connections = [
        ConnectionConfig.from_dict(
            {
                "name": "Production PostgreSQL",
                "db_type": "postgresql",
                "endpoint": {
                    "kind": "tcp",
                    "host": "prod.example.com",
                    "port": "5432",
                    "database": "app_db",
                    "username": "admin",
                    "password": None,
                },
            }
        ),
        ConnectionConfig.from_dict(
            {
                "name": "Local SQLite",
                "db_type": "sqlite",
                "endpoint": {"kind": "file", "path": "./local.db"},
            }
        ),
        ConnectionConfig.from_dict(
            {
                "name": "Dev MySQL",
                "db_type": "mysql",
                "endpoint": {
                    "kind": "tcp",
                    "host": "localhost",
                    "port": "3306",
                    "database": "dev_db",
                    "username": "root",
                    "password": None,
                },
            }
        ),
    ]

    return MockProfile(
        name="multi-db",
        connections=connections,
        adapters={},
        use_default_adapters=True,
    )


def _create_driver_install_success_profile() -> MockProfile:
    """Profile intended for demoing the driver install UX."""
    connections = [
        ConnectionConfig.from_dict(
            {
                "name": "PostgreSQL (missing driver)",
                "db_type": "postgresql",
                "endpoint": {
                    "kind": "tcp",
                    "host": "localhost",
                    "port": "5432",
                    "database": "postgres",
                    "username": "user",
                    "password": None,
                },
            }
        ),
    ]
    return MockProfile(
        name="driver-install-success",
        connections=connections,
        adapters={},
        use_default_adapters=True,
    )


def _create_driver_install_fail_profile() -> MockProfile:
    """Profile intended for demoing the driver install failure UX."""
    connections = [
        ConnectionConfig.from_dict(
            {
                "name": "MySQL (missing driver)",
                "db_type": "mysql",
                "endpoint": {
                    "kind": "tcp",
                    "host": "localhost",
                    "port": "3306",
                    "database": "test_sqlit",
                    "username": "user",
                    "password": None,
                },
            }
        ),
    ]
    return MockProfile(
        name="driver-install-fail",
        connections=connections,
        adapters={},
        use_default_adapters=True,
    )


def _create_supabase_demo_profile() -> MockProfile:
    """Create a Supabase demo profile with empty connections but mock adapter."""
    return MockProfile(
        name="supabase-demo",
        connections=[],
        adapters={"supabase": create_default_supabase_adapter()},
        use_default_adapters=True,
    )


def _create_perf_test_profile() -> MockProfile:
    """Create a performance testing profile.

    Usage:
        sqlit --mock=perf-test --demo-rows=10000

    This profile is designed for testing DataTable rendering performance
    with large datasets. Use --demo-rows to specify the number of rows.
    """
    connections = [
        ConnectionConfig.from_dict(
            {
                "name": "Performance Test DB",
                "db_type": "sqlite",
                "endpoint": {"kind": "file", "path": "./perf_test.db"},
            }
        ),
    ]

    # Create an adapter that's optimized for perf testing
    # (minimal schema, fast responses)
    adapter = MockDatabaseAdapter(
        name="SQLite",
        tables=[
            ("main", "large_table"),
            ("main", "users"),
            ("main", "transactions"),
        ],
        views=[],
        columns={
            "large_table": [
                ColumnInfo("id", "INTEGER"),
                ColumnInfo("name", "TEXT"),
                ColumnInfo("email", "TEXT"),
                ColumnInfo("phone", "TEXT"),
                ColumnInfo("address", "TEXT"),
                ColumnInfo("created_at", "TEXT"),
            ],
            "users": [
                ColumnInfo("id", "INTEGER"),
                ColumnInfo("name", "TEXT"),
                ColumnInfo("email", "TEXT"),
            ],
            "transactions": [
                ColumnInfo("id", "INTEGER"),
                ColumnInfo("user_id", "INTEGER"),
                ColumnInfo("amount", "REAL"),
                ColumnInfo("timestamp", "TEXT"),
            ],
        },
        default_schema="main",
    )

    return MockProfile(
        name="perf-test",
        connections=connections,
        adapters={"sqlite": adapter},
        use_default_adapters=True,
    )


# Registry of available mock profiles
MOCK_PROFILES: dict[str, Callable[[], MockProfile]] = {
    "sqlite-demo": _create_sqlite_demo_profile,
    "empty": _create_empty_profile,
    "multi-db": _create_multi_db_profile,
    "driver-install-success": _create_driver_install_success_profile,
    "driver-install-fail": _create_driver_install_fail_profile,
    "supabase-demo": _create_supabase_demo_profile,
    "perf-test": _create_perf_test_profile,
}


def get_mock_profile(name: str) -> MockProfile | None:
    """Get a mock profile by name."""
    factory = MOCK_PROFILES.get(name)
    if factory:
        return factory()
    return None


def list_mock_profiles() -> list[str]:
    """List available mock profile names."""
    return list(MOCK_PROFILES.keys())
