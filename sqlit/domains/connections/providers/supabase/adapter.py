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
        shard = config.get_option("supabase_aws_shard", "aws-0")
        shard = str(shard).strip() or "aws-0"
        if shard.startswith("aws") and not shard.startswith("aws-"):
            suffix = shard.removeprefix("aws")
            if suffix.isdigit():
                shard = f"aws-{suffix}"
        elif shard.isdigit():
            shard = f"aws-{shard}"
        transformed = config.with_endpoint(
            host=f"{shard}-{region}.pooler.supabase.com",
            port="5432",
            username=f"postgres.{project_id}",
            database="postgres",
        )
        return super().connect(transformed)
