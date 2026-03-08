"""Query execution helpers decoupled from UI."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from sqlit.domains.query.app.cancellable import CancellableQuery
from sqlit.domains.query.app.query_service import NonQueryResult, QueryResult, parse_use_statement


@dataclass(frozen=True)
class QueryExecutionPlan:
    handle: QueryExecutionHandle | None
    use_database: str | None


@dataclass(frozen=True)
class QueryExecutionOutcome:
    result: QueryResult | NonQueryResult
    elapsed_ms: float


class QueryExecutionHandle:
    """Wrapper for executing and cancelling a single query."""

    def __init__(
        self,
        *,
        query: str,
        config: Any,
        provider: Any,
        tunnel: Any | None,
        history_store: Any,
    ) -> None:
        self._query = query
        self._config = config
        self._history_store = history_store
        self._cancellable = CancellableQuery(
            sql=query,
            config=config,
            provider=provider,
            tunnel=tunnel,
        )
        self._save_name = getattr(config, "name", "")

    async def run(self, max_rows: int | None, *, save_to_history: bool = True) -> QueryExecutionOutcome:
        start_time = time.perf_counter()
        result = await asyncio.to_thread(self._cancellable.execute, max_rows)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        if save_to_history and self._save_name:
            self._history_store.save_query(self._save_name, self._query)
        return QueryExecutionOutcome(result=result, elapsed_ms=elapsed_ms)

    def cancel(self) -> bool:
        return self._cancellable.cancel()

    @property
    def is_cancelled(self) -> bool:
        return self._cancellable.is_cancelled


def resolve_execution_config(
    *,
    config: Any,
    provider: Any,
    target_db: str | None,
    active_db: str | None,
) -> Any:
    endpoint = getattr(config, "tcp_endpoint", None)
    current_db = endpoint.database if endpoint else ""
    if target_db and target_db != current_db:
        config = provider.apply_database_override(config, target_db)
    endpoint = getattr(config, "tcp_endpoint", None)
    current_db = endpoint.database if endpoint else ""
    if active_db and active_db != current_db and not target_db:
        config = provider.apply_database_override(config, active_db)
    return config


def build_execution_plan(
    *,
    query: str,
    config: Any,
    provider: Any,
    tunnel: Any | None,
    history_store: Any,
) -> QueryExecutionPlan:
    use_db = parse_use_statement(query)
    if use_db is not None:
        return QueryExecutionPlan(handle=None, use_database=use_db)
    handle = QueryExecutionHandle(
        query=query,
        config=config,
        provider=provider,
        tunnel=tunnel,
        history_store=history_store,
    )
    return QueryExecutionPlan(handle=handle, use_database=None)
