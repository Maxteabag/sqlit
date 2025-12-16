from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .postgresql import PostgreSQLAdapter

if TYPE_CHECKING:
    from ...config import ConnectionConfig


class SupabaseAdapter(PostgreSQLAdapter):
    @property
    def name(self) -> str:
        return "Supabase"

    @property
    def supports_multiple_databases(self) -> bool:
        return False

    def connect(self, config: ConnectionConfig) -> Any:
        from dataclasses import replace

        transformed = replace(
            config,
            server=f"aws-0-{config.supabase_region}.pooler.supabase.com",
            port="5432",
            username=f"postgres.{config.supabase_project_id}",
            database="postgres",
        )
        return super().connect(transformed)
