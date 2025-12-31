"""Default mock adapters for common database types."""

from __future__ import annotations

from collections.abc import Callable

from sqlit.domains.connections.providers.adapters.base import ColumnInfo

from .mock_adapter_core import MockDatabaseAdapter

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
                    (
                        "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "alice_dev",
                        "Alice Developer",
                        "https://avatars.example.com/alice.png",
                        "2024-01-15 10:30:00+00",
                        "2024-01-20 14:22:00+00",
                    ),
                    (
                        "b2c3d4e5-f6a7-8901-bcde-f12345678901",
                        "bob_builder",
                        "Bob Builder",
                        "https://avatars.example.com/bob.png",
                        "2024-01-16 11:45:00+00",
                        "2024-01-21 09:15:00+00",
                    ),
                    (
                        "c3d4e5f6-a7b8-9012-cdef-123456789012",
                        "charlie_coder",
                        "Charlie Coder",
                        None,
                        "2024-01-17 08:00:00+00",
                        "2024-01-17 08:00:00+00",
                    ),
                ],
            ),
            "posts": (
                ["id", "user_id", "title", "content", "published", "created_at"],
                [
                    (
                        "d4e5f6a7-b8c9-0123-def0-234567890123",
                        "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "Getting Started with Supabase",
                        "Supabase is an open source Firebase alternative...",
                        True,
                        "2024-01-18 12:00:00+00",
                    ),
                    (
                        "e5f6a7b8-c9d0-1234-ef01-345678901234",
                        "b2c3d4e5-f6a7-8901-bcde-f12345678901",
                        "Building Real-time Apps",
                        "Real-time functionality is built into Supabase...",
                        True,
                        "2024-01-19 15:30:00+00",
                    ),
                ],
            ),
            "comments": (
                ["id", "post_id", "user_id", "content", "created_at"],
                [
                    (
                        "f6a7b8c9-d0e1-2345-f012-456789012345",
                        "d4e5f6a7-b8c9-0123-def0-234567890123",
                        "b2c3d4e5-f6a7-8901-bcde-f12345678901",
                        "Great introduction!",
                        "2024-01-18 14:00:00+00",
                    ),
                    (
                        "a7b8c9d0-e1f2-3456-0123-567890123456",
                        "d4e5f6a7-b8c9-0123-def0-234567890123",
                        "c3d4e5f6-a7b8-9012-cdef-123456789012",
                        "Very helpful, thanks!",
                        "2024-01-18 16:30:00+00",
                    ),
                ],
            ),
            "auth.users": (
                [
                    "id",
                    "email",
                    "encrypted_password",
                    "email_confirmed_at",
                    "last_sign_in_at",
                    "created_at",
                    "updated_at",
                ],
                [
                    (
                        "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "alice@example.com",
                        "$2a$10$...",
                        "2024-01-15 10:35:00+00",
                        "2024-01-22 08:00:00+00",
                        "2024-01-15 10:30:00+00",
                        "2024-01-22 08:00:00+00",
                    ),
                    (
                        "b2c3d4e5-f6a7-8901-bcde-f12345678901",
                        "bob@example.com",
                        "$2a$10$...",
                        "2024-01-16 12:00:00+00",
                        "2024-01-21 09:00:00+00",
                        "2024-01-16 11:45:00+00",
                        "2024-01-21 09:00:00+00",
                    ),
                    (
                        "c3d4e5f6-a7b8-9012-cdef-123456789012",
                        "charlie@example.com",
                        "$2a$10$...",
                        "2024-01-17 08:05:00+00",
                        "2024-01-20 17:30:00+00",
                        "2024-01-17 08:00:00+00",
                        "2024-01-20 17:30:00+00",
                    ),
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
