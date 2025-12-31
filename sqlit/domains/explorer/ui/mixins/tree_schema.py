"""Schema service helpers for explorer tree mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from sqlit.shared.ui.protocols import TreeMixinHost

if TYPE_CHECKING:
    from sqlit.domains.connections.app.session import ConnectionSession


class TreeSchemaMixin:
    """Mixin providing schema service and cache helpers."""

    _session: ConnectionSession | None = None
    _schema_service: Any | None = None
    _schema_service_session: Any | None = None

    def _get_object_cache(self) -> dict[str, dict[str, Any]]:
        cache = getattr(self, "_db_object_cache", None)
        if cache is None:
            cache = {}
            self._db_object_cache = cache
        return cache

    def _get_schema_service(self: TreeMixinHost) -> Any | None:
        if not self._session:
            return None
        if self._schema_service is None or self._schema_service_session is not self._session:
            from sqlit.domains.explorer.app.schema_service import DbArgResolver, ExplorerSchemaService

            db_arg_resolver = getattr(self, "_get_metadata_db_arg", None)
            if not callable(db_arg_resolver):
                db_arg_resolver = None
            else:
                db_arg_resolver = cast(DbArgResolver, db_arg_resolver)
            self._schema_service = ExplorerSchemaService(
                session=self._session,
                object_cache=self._get_object_cache(),
                db_arg_resolver=db_arg_resolver,
            )
            self._schema_service_session = self._session
        return self._schema_service
