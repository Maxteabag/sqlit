from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class SupabaseAdapter(PostgreSQLAdapter):
    @property
    def name(self) -> str:
        return "Supabase"

    @property
    def supports_multiple_databases(self) -> bool:
        return False

    def connect(self, config: ConnectionConfig) -> Any:
        region = config.get_option("supabase_region", "")
        project_id = config.get_option("supabase_project_id", "")
        transformed = config.with_endpoint(
            host=f"aws-0-{region}.pooler.supabase.com",
            port="5432",
            username=f"postgres.{project_id}",
            database="postgres",
        )
        return super().connect(transformed)
