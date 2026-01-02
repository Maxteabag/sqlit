"""Schema loading and caching helpers for autocomplete."""

from __future__ import annotations

from typing import Any, cast

from sqlit.domains.connections.providers.model import ProcedureInspector
from sqlit.domains.query.completion import extract_table_refs
from sqlit.shared.ui.protocols import AutocompleteMixinHost
from sqlit.shared.ui.spinner import Spinner


class AutocompleteSchemaMixin:
    """Mixin providing schema loading and caching for autocomplete."""

    _schema_worker: Any | None = None
    _schema_spinner: Spinner | None = None
    _schema_cache: dict[str, Any] = {}
    _table_metadata: dict[str, tuple[str, str, str | None]] = {}
    _columns_loading: set[str] = set()
    _db_object_cache: dict[str, dict[str, list[Any]]] = {}
    _schema_indexing: bool = False
    _schema_pending_dbs: list[str | None] = []
    _schema_total_jobs: int = 0
    _schema_completed_jobs: int = 0
    _schema_scheduler: Any | None = None

    def _run_db_call(self: AutocompleteMixinHost, fn: Any, *args: Any, **kwargs: Any) -> Any:
        session = getattr(self, "_session", None)
        if session is not None:
            return session.executor.submit(fn, *args, **kwargs).result()
        return fn(*args, **kwargs)

    def _reconnect_for_autocomplete(self: AutocompleteMixinHost, target_db: str | None) -> bool:
        session = getattr(self, "_session", None)
        if session is None:
            return False
        try:
            session.switch_database(target_db or "")
            self.current_config = session.config
            self.current_connection = session.connection
            return True
        except Exception as error:
            self.log.error(f"Error reconnecting for autocomplete: {error}")
            return False

    def _load_columns_for_table(self: AutocompleteMixinHost, table_name: str, *, allow_retry: bool = True) -> None:
        """Lazy load columns for a specific table (async via worker)."""
        if not self.current_connection or not self.current_provider:
            return

        if not hasattr(self, "_columns_loading") or self._columns_loading is None:
            self._columns_loading = set()

        if table_name in self._columns_loading:
            return

        metadata = self._table_metadata.get(table_name)
        if not metadata:
            return

        schema_name, actual_table_name, database = metadata
        self._columns_loading.add(table_name)

        def work() -> None:
            provider = self.current_provider
            connection = self.current_connection
            if not provider or not connection:
                column_names = []
            else:
                try:
                    db_arg = database
                    if hasattr(self, "_get_metadata_db_arg"):
                        db_arg = self._get_metadata_db_arg(database)
                    columns = self._run_db_call(
                        provider.schema_inspector.get_columns,
                        connection,
                        actual_table_name,
                        db_arg,
                        schema_name,
                    )
                    column_names = [c.name for c in columns]
                except Exception:
                    self.call_from_thread(
                        self._on_autocomplete_columns_error,
                        table_name,
                        actual_table_name,
                        database,
                        allow_retry,
                    )
                    return

            self.call_from_thread(
                self._on_autocomplete_columns_loaded,
                table_name,
                actual_table_name,
                column_names,
            )

        self.run_worker(work, name=f"load-columns-{table_name}", thread=True, exclusive=False)

    def _on_autocomplete_columns_loaded(
        self: AutocompleteMixinHost, table_name: str, actual_table_name: str, column_names: list[str]
    ) -> None:
        """Handle column load completion for autocomplete on main thread."""
        self._columns_loading.discard(table_name)
        self._schema_cache["columns"][table_name] = column_names
        self._schema_cache["columns"][actual_table_name.lower()] = column_names

        # Refresh autocomplete if visible (replaces "Loading..." with actual columns)
        if self._autocomplete_visible:
            text = self.query_input.text
            cursor_loc = self.query_input.cursor_location
            cursor_pos = self._location_to_offset(text, cursor_loc)
            current_word = self._get_current_word(text, cursor_pos)
            suggestions = self._get_autocomplete_suggestions(text, cursor_pos)
            if suggestions:
                self._show_autocomplete(suggestions, current_word)
            else:
                self._hide_autocomplete()

    def _on_autocomplete_columns_error(
        self: AutocompleteMixinHost,
        table_name: str,
        actual_table_name: str,
        database: str | None,
        allow_retry: bool,
    ) -> None:
        """Handle column load error for autocomplete and retry once after reconnect."""
        self._columns_loading.discard(table_name)

        target_db = database
        if not target_db and hasattr(self, "_get_effective_database"):
            target_db = self._get_effective_database()

        if allow_retry and target_db is not None:
            if not self._reconnect_for_autocomplete(target_db):
                self.log.error(f"Error reconnecting for columns on {actual_table_name}")
                return
            self._load_columns_for_table(table_name, allow_retry=False)
            return

        self.log.error(f"Error loading columns for {actual_table_name}")

    def _has_tables_needing_columns(self: AutocompleteMixinHost, text: str) -> bool:
        """Check if there are tables in the query that need column loading."""
        if not text.strip():
            return False

        table_refs = extract_table_refs(text)
        columns_cache = self._schema_cache.get("columns", {})
        loading: set[str] = getattr(self, "_columns_loading", set())

        for ref in table_refs:
            table_key = ref.name.lower()
            if table_key in columns_cache or table_key in loading:
                continue
            if table_key in self._table_metadata:
                return True
        return False

    def _preload_columns_for_query(self: AutocompleteMixinHost) -> None:
        """Preload columns for all tables found in the current query (runs during idle)."""
        if not self.current_connection or not self.current_provider:
            return

        text = self.query_input.text
        if not text.strip():
            return

        # Extract table references from the query
        table_refs = extract_table_refs(text)
        columns_cache = self._schema_cache.get("columns", {})
        loading: set[str] = getattr(self, "_columns_loading", set())

        for ref in table_refs:
            table_key = ref.name.lower()
            # Skip if already loaded or currently loading
            if table_key in columns_cache or table_key in loading:
                continue
            # Skip if not a known table
            if table_key not in self._table_metadata:
                continue
            # Queue column loading
            self._load_columns_for_table(table_key)

    def _load_schema_cache(self: AutocompleteMixinHost) -> None:
        """Load database schema for autocomplete using threaded workers."""
        if not self.current_connection or not self.current_config or not self.current_provider:
            return

        # Cancel any existing schema worker
        if hasattr(self, "_schema_worker") and self._schema_worker is not None:
            self._schema_worker.cancel()

        # Initialize empty cache immediately
        self._schema_cache = {
            "tables": [],
            "views": [],
            "columns": {},
            "procedures": [],
        }
        self._table_metadata = {}
        self._columns_loading = set()  # Clear any in-progress column loads
        self._db_object_cache = {}  # Clear shared object cache

        # Start schema indexing spinner
        self._start_schema_spinner()

        # Load schema directly using threaded workers (no idle scheduler needed)
        self._load_schema_directly()

    def _load_schema_directly(self: AutocompleteMixinHost) -> None:
        """Load schema using threaded workers - runs immediately without idle scheduler."""
        provider = self.current_provider
        inspector = provider.schema_inspector if provider else None
        connection = self.current_connection
        config = self.current_config

        if not provider or not inspector or not connection or not config:
            self._stop_schema_spinner()
            return
        caps = provider.capabilities

        # Track pending database loads
        self._schema_pending_dbs = []
        self._schema_total_jobs = 0
        self._schema_completed_jobs = 0

        if caps.supports_multiple_databases:
            db = None
            if hasattr(self, "_get_effective_database"):
                db = self._get_effective_database()
            if db:
                # Single database specified - load immediately
                self._on_databases_loaded([db])
            elif caps.supports_cross_database_queries:
                # Need to fetch database list - offload to thread
                def work() -> None:
                    try:
                        all_dbs = self._run_db_call(inspector.get_databases, connection)
                        system_dbs = {s.lower() for s in caps.system_databases}
                        databases = [d for d in all_dbs if d.lower() not in system_dbs]
                        self.call_from_thread(self._on_databases_loaded, databases)
                    except Exception as e:
                        self.call_from_thread(self._on_databases_error, e)

                self.run_worker(work, thread=True, name="get-databases")
            else:
                self._stop_schema_spinner()
        else:
            # No multiple databases - just proceed with None
            self._on_databases_loaded([None])

    def _load_schema_via_idle_scheduler(self: AutocompleteMixinHost, scheduler: Any) -> None:
        """Load schema using idle scheduler for smoother UI."""
        from sqlit.domains.shell.app.idle_scheduler import Priority

        provider = self.current_provider
        inspector = provider.schema_inspector if provider else None
        connection = self.current_connection
        config = self.current_config

        if not provider or not inspector or not connection or not config:
            self._stop_schema_spinner()
            return
        caps = provider.capabilities

        # Track pending database loads
        self._schema_pending_dbs = []
        self._schema_total_jobs = 0
        self._schema_completed_jobs = 0
        # Store scheduler reference for use in callbacks
        self._schema_scheduler = scheduler

        def get_databases_job() -> None:
            """First job: dispatch thread to get list of databases."""
            if caps.supports_multiple_databases:
                db = None
                if hasattr(self, "_get_effective_database"):
                    db = self._get_effective_database()
                if db:
                    # Single database specified - no need for DB call
                    self._on_databases_loaded([db])
                elif caps.supports_cross_database_queries:
                    # Need to fetch database list - offload to thread
                    def work() -> None:
                        try:
                            all_dbs = self._run_db_call(inspector.get_databases, connection)
                            system_dbs = {s.lower() for s in caps.system_databases}
                            databases = [d for d in all_dbs if d.lower() not in system_dbs]
                            self.call_from_thread(self._on_databases_loaded, databases)
                        except Exception as e:
                            self.call_from_thread(self._on_databases_error, e)

                    self.run_worker(work, thread=True, name="get-databases")
                else:
                    self._stop_schema_spinner()
            else:
                # No multiple databases - just proceed with None
                self._on_databases_loaded([None])

        # Queue the first job with high priority
        scheduler.request_idle_callback(
            get_databases_job,
            priority=Priority.HIGH,
            name="schema-load",
        )

    def _on_databases_loaded(self: AutocompleteMixinHost, databases: list) -> None:
        """Handle databases list loaded - spawn threaded workers for each database."""
        provider = self.current_provider

        if not provider:
            self._stop_schema_spinner()
            return
        caps = provider.capabilities

        self._schema_pending_dbs = databases
        self._schema_total_jobs = len(databases) * 3  # tables, views, procedures per db
        supports_procedures = caps.supports_stored_procedures and isinstance(provider.schema_inspector, ProcedureInspector)

        # Spawn workers directly - they're threaded so won't block
        for database in databases:
            self._load_tables_job(database)
            self._load_views_job(database)
            if supports_procedures:
                self._load_procedures_job(database)
            else:
                self._schema_completed_jobs += 1  # Skip procedures

    def _on_databases_error(self: AutocompleteMixinHost, error: Exception) -> None:
        """Handle error getting databases list."""
        self.log.error(f"Error getting databases: {error}")
        self._stop_schema_spinner()

    def _load_tables_job(self: AutocompleteMixinHost, database: str | None) -> None:
        """Idle job: load tables for a single database (dispatches to thread)."""
        provider = self.current_provider
        connection = self.current_connection

        if not provider or not connection:
            self._schema_job_complete()
            return
        inspector = provider.schema_inspector
        if not isinstance(inspector, ProcedureInspector):
            self._schema_job_complete()
            return

        cache_key = database or "__default__"

        # Check shared cache first (may have been populated by tree expansion)
        if cache_key in self._db_object_cache and "tables" in self._db_object_cache[cache_key]:
            self._process_tables_result(self._db_object_cache[cache_key]["tables"], database, cache_key)
            return

        # Offload DB call to thread
        def work() -> None:
            try:
                db_arg = database
                if hasattr(self, "_get_metadata_db_arg"):
                    db_arg = self._get_metadata_db_arg(database)
                tables = self._run_db_call(inspector.get_tables, connection, db_arg)
                # Store in shared cache and process on main thread
                self.call_from_thread(self._on_tables_loaded, tables, database, cache_key)
            except Exception as e:
                self.call_from_thread(self._on_tables_error, e, database)

        self.run_worker(work, thread=True, name=f"load-tables-{cache_key}")

    def _on_tables_loaded(self: AutocompleteMixinHost, tables: list, database: str | None, cache_key: str) -> None:
        """Handle tables loaded from thread."""
        if cache_key not in self._db_object_cache:
            self._db_object_cache[cache_key] = {}
        self._db_object_cache[cache_key]["tables"] = tables
        self._process_tables_result(tables, database, cache_key)

    def _on_tables_error(self: AutocompleteMixinHost, error: Exception, database: str | None) -> None:
        """Handle tables load error from thread."""
        self.log.error(f"Error loading tables for {database}: {error}")
        self._schema_job_complete()

    def _process_tables_result(self: AutocompleteMixinHost, tables: list, database: str | None, cache_key: str) -> None:
        """Process tables result on main thread."""
        provider = self.current_provider
        if not provider:
            self._schema_job_complete()
            return
        dialect = provider.dialect

        try:
            single_db = len(getattr(self, "_schema_pending_dbs", [None])) == 1

            for schema_name, table_name in tables:
                if single_db:
                    self._schema_cache["tables"].append(table_name)
                else:
                    quoted_db = dialect.quote_identifier(database) if database else ""
                    quoted_schema = dialect.quote_identifier(schema_name)
                    quoted_table = dialect.quote_identifier(table_name)
                    if database:
                        full_name = f"{quoted_db}.{quoted_schema}.{quoted_table}"
                    else:
                        full_name = f"{quoted_schema}.{quoted_table}"
                    self._schema_cache["tables"].append(full_name)

                # Store metadata for column loading
                display_name = dialect.format_table_name(schema_name, table_name)
                self._table_metadata[display_name.lower()] = (schema_name, table_name, database)
                self._table_metadata[table_name.lower()] = (schema_name, table_name, database)
                if database:
                    self._table_metadata[f"{database}.{table_name}".lower()] = (schema_name, table_name, database)
                    if not single_db:
                        self._table_metadata[full_name.lower()] = (schema_name, table_name, database)

        except Exception as e:
            self.log.error(f"Error processing tables for {database}: {e}")

        self._schema_job_complete()

    def _load_views_job(self: AutocompleteMixinHost, database: str | None) -> None:
        """Idle job: load views for a single database (dispatches to thread)."""
        provider = self.current_provider
        connection = self.current_connection

        if not provider or not connection:
            self._schema_job_complete()
            return
        inspector = provider.schema_inspector
        if not isinstance(inspector, ProcedureInspector):
            self._schema_job_complete()
            return

        cache_key = database or "__default__"

        # Check shared cache first (may have been populated by tree expansion)
        if cache_key in self._db_object_cache and "views" in self._db_object_cache[cache_key]:
            self._process_views_result(self._db_object_cache[cache_key]["views"], database, cache_key)
            return

        # Offload DB call to thread
        def work() -> None:
            try:
                db_arg = database
                if hasattr(self, "_get_metadata_db_arg"):
                    db_arg = self._get_metadata_db_arg(database)
                views = self._run_db_call(inspector.get_views, connection, db_arg)
                self.call_from_thread(self._on_views_loaded, views, database, cache_key)
            except Exception as e:
                self.call_from_thread(self._on_views_error, e, database)

        self.run_worker(work, thread=True, name=f"load-views-{cache_key}")

    def _on_views_loaded(self: AutocompleteMixinHost, views: list, database: str | None, cache_key: str) -> None:
        """Handle views loaded from thread."""
        if cache_key not in self._db_object_cache:
            self._db_object_cache[cache_key] = {}
        self._db_object_cache[cache_key]["views"] = views
        self._process_views_result(views, database, cache_key)

    def _on_views_error(self: AutocompleteMixinHost, error: Exception, database: str | None) -> None:
        """Handle views load error from thread."""
        self.log.error(f"Error loading views for {database}: {error}")
        self._schema_job_complete()

    def _process_views_result(self: AutocompleteMixinHost, views: list, database: str | None, cache_key: str) -> None:
        """Process views result on main thread."""
        provider = self.current_provider
        if not provider:
            self._schema_job_complete()
            return
        dialect = provider.dialect

        try:
            single_db = len(getattr(self, "_schema_pending_dbs", [None])) == 1

            for schema_name, view_name in views:
                if single_db:
                    self._schema_cache["views"].append(view_name)
                else:
                    quoted_db = dialect.quote_identifier(database) if database else ""
                    quoted_schema = dialect.quote_identifier(schema_name)
                    quoted_view = dialect.quote_identifier(view_name)
                    if database:
                        full_name = f"{quoted_db}.{quoted_schema}.{quoted_view}"
                    else:
                        full_name = f"{quoted_schema}.{quoted_view}"
                    self._schema_cache["views"].append(full_name)

                # Store metadata for column loading
                display_name = dialect.format_table_name(schema_name, view_name)
                self._table_metadata[display_name.lower()] = (schema_name, view_name, database)
                self._table_metadata[view_name.lower()] = (schema_name, view_name, database)
                if database:
                    self._table_metadata[f"{database}.{view_name}".lower()] = (schema_name, view_name, database)
                    if not single_db:
                        self._table_metadata[full_name.lower()] = (schema_name, view_name, database)

        except Exception as e:
            self.log.error(f"Error processing views for {database}: {e}")

        self._schema_job_complete()

    def _load_procedures_job(self: AutocompleteMixinHost, database: str | None) -> None:
        """Idle job: load procedures for a single database (dispatches to thread)."""
        provider = self.current_provider
        connection = self.current_connection

        if not provider or not connection:
            self._schema_job_complete()
            return
        inspector = provider.schema_inspector
        if not isinstance(inspector, ProcedureInspector):
            self._schema_job_complete()
            return
        procedure_inspector = cast(ProcedureInspector, inspector)

        cache_key = database or "__default__"

        # Check shared cache first (may have been populated by tree expansion)
        if cache_key in self._db_object_cache and "procedures" in self._db_object_cache[cache_key]:
            self._process_procedures_result(self._db_object_cache[cache_key]["procedures"], cache_key)
            return

        # Offload DB call to thread
        def work() -> None:
            try:
                db_arg = database
                if hasattr(self, "_get_metadata_db_arg"):
                    db_arg = self._get_metadata_db_arg(database)
                procedures = self._run_db_call(procedure_inspector.get_procedures, connection, db_arg)
                self.call_from_thread(self._on_procedures_loaded, procedures, database, cache_key)
            except Exception as e:
                self.call_from_thread(self._on_procedures_error, e, database)

        self.run_worker(work, thread=True, name=f"load-procedures-{cache_key}")

    def _on_procedures_loaded(self: AutocompleteMixinHost, procedures: list, database: str | None, cache_key: str) -> None:
        """Handle procedures loaded from thread."""
        if cache_key not in self._db_object_cache:
            self._db_object_cache[cache_key] = {}
        self._db_object_cache[cache_key]["procedures"] = procedures
        self._process_procedures_result(procedures, cache_key)

    def _on_procedures_error(self: AutocompleteMixinHost, error: Exception, database: str | None) -> None:
        """Handle procedures load error from thread."""
        self.log.error(f"Error loading procedures for {database}: {error}")
        self._schema_job_complete()

    def _process_procedures_result(self: AutocompleteMixinHost, procedures: list, cache_key: str) -> None:
        """Process procedures result on main thread."""
        try:
            self._schema_cache["procedures"].extend(procedures)
        except Exception as e:
            self.log.error(f"Error processing procedures: {e}")

        self._schema_job_complete()

    def _schema_job_complete(self: AutocompleteMixinHost) -> None:
        """Called when a schema loading job completes."""
        self._schema_completed_jobs = getattr(self, "_schema_completed_jobs", 0) + 1
        total = getattr(self, "_schema_total_jobs", 1)

        if self._schema_completed_jobs >= total:
            # All jobs done - deduplicate and finalize
            self._schema_cache["tables"] = list(dict.fromkeys(self._schema_cache["tables"]))
            self._schema_cache["views"] = list(dict.fromkeys(self._schema_cache["views"]))
            self._schema_cache["procedures"] = list(dict.fromkeys(self._schema_cache["procedures"]))
            self._stop_schema_spinner()

    def _start_schema_spinner(self: AutocompleteMixinHost) -> None:
        """Start the schema indexing spinner animation."""
        self._schema_indexing = True
        if self._schema_spinner is not None:
            self._schema_spinner.stop()
        spinner = Spinner(self, on_tick=lambda _: self._update_status_bar(), fps=10)
        self._schema_spinner = spinner
        spinner.start()

    def _stop_schema_spinner(self: AutocompleteMixinHost) -> None:
        """Stop the schema indexing spinner animation."""
        self._schema_indexing = False
        if self._schema_spinner is not None:
            self._schema_spinner.stop()
            self._schema_spinner = None
        self._update_status_bar()

    def action_cancel_schema_indexing(self: AutocompleteMixinHost) -> None:
        """Cancel ongoing schema indexing."""
        if hasattr(self, "_schema_worker") and self._schema_worker is not None:
            self._schema_worker.cancel()
            self._schema_worker = None
        self._stop_schema_spinner()
        self.notify("Schema indexing cancelled")

    async def _load_schema_cache_async(self: AutocompleteMixinHost) -> None:
        """Load database schema asynchronously.

        Only loads tables, views, and procedures.
        Columns are lazy-loaded on demand when user types `table.`
        """
        import asyncio

        provider = self.current_provider
        connection = self.current_connection
        config = self.current_config

        if not provider or not connection or not config:
            self._stop_schema_spinner()
            return
        inspector = provider.schema_inspector
        dialect = provider.dialect
        caps = provider.capabilities

        schema_cache: dict = {
            "tables": [],
            "views": [],
            "columns": {},
            "procedures": [],
        }
        table_metadata: dict[str, tuple[str, str, str | None]] = {}

        async def run_db_call(fn: Any, *args: Any, **kwargs: Any) -> Any:
            session = getattr(self, "_session", None)
            if session is not None:
                return await session.executor.run_async(fn, *args, **kwargs)
            return await asyncio.to_thread(fn, *args, **kwargs)

        try:
            databases: list[str | None]
            if caps.supports_multiple_databases:
                db = None
                if hasattr(self, "_get_effective_database"):
                    db = self._get_effective_database()
                if db:
                    # Active/default database is set - only load that one
                    databases = [db]
                elif caps.supports_cross_database_queries:
                    # No default database - load all non-system databases
                    all_dbs = await run_db_call(inspector.get_databases, connection)
                    system_dbs = {s.lower() for s in caps.system_databases}
                    databases = [d for d in all_dbs if d.lower() not in system_dbs]
                else:
                    databases = []
            else:
                databases = [None]

            for database in databases:
                try:
                    # Get tables
                    db_arg = database
                    if hasattr(self, "_get_metadata_db_arg"):
                        db_arg = self._get_metadata_db_arg(database)
                    tables = await run_db_call(inspector.get_tables, connection, db_arg)
                    for schema_name, table_name in tables:
                        # Use simple name if we have a default database, full qualifier otherwise
                        if len(databases) == 1:
                            # Single database - use simple table name
                            schema_cache["tables"].append(table_name)
                        else:
                            # Multiple databases - use full qualifier [db].[schema].[table]
                            quoted_db = dialect.quote_identifier(database) if database else ""
                            quoted_schema = dialect.quote_identifier(schema_name)
                            quoted_table = dialect.quote_identifier(table_name)
                            if database:
                                full_name = f"{quoted_db}.{quoted_schema}.{quoted_table}"
                            else:
                                full_name = f"{quoted_schema}.{quoted_table}"
                            schema_cache["tables"].append(full_name)
                        # Keep metadata for column loading (multiple keys for flexible lookup)
                        display_name = dialect.format_table_name(schema_name, table_name)
                        table_metadata[display_name.lower()] = (schema_name, table_name, database)
                        table_metadata[table_name.lower()] = (schema_name, table_name, database)
                        if database:
                            table_metadata[f"{database}.{table_name}".lower()] = (schema_name, table_name, database)
                            # Also store with full quoted name for [db].[schema].[table] lookups
                            if len(databases) > 1:
                                table_metadata[full_name.lower()] = (schema_name, table_name, database)

                    # Get views
                    views = await run_db_call(inspector.get_views, connection, db_arg)
                    for schema_name, view_name in views:
                        # Use simple name if we have a default database, full qualifier otherwise
                        if len(databases) == 1:
                            # Single database - use simple view name
                            schema_cache["views"].append(view_name)
                        else:
                            # Multiple databases - use full qualifier [db].[schema].[view]
                            quoted_db = dialect.quote_identifier(database) if database else ""
                            quoted_schema = dialect.quote_identifier(schema_name)
                            quoted_view = dialect.quote_identifier(view_name)
                            if database:
                                full_name = f"{quoted_db}.{quoted_schema}.{quoted_view}"
                            else:
                                full_name = f"{quoted_schema}.{quoted_view}"
                            schema_cache["views"].append(full_name)
                        # Keep metadata for column loading (multiple keys for flexible lookup)
                        display_name = dialect.format_table_name(schema_name, view_name)
                        table_metadata[display_name.lower()] = (schema_name, view_name, database)
                        table_metadata[view_name.lower()] = (schema_name, view_name, database)
                        if database:
                            table_metadata[f"{database}.{view_name}".lower()] = (schema_name, view_name, database)
                            # Also store with full quoted name for [db].[schema].[view] lookups
                            if len(databases) > 1:
                                table_metadata[full_name.lower()] = (schema_name, view_name, database)

                    # Get procedures
                    if caps.supports_stored_procedures and isinstance(inspector, ProcedureInspector):
                        procedures = await run_db_call(inspector.get_procedures, connection, db_arg)
                        schema_cache["procedures"].extend(procedures)

                except Exception:
                    pass

            # Deduplicate
            schema_cache["tables"] = list(dict.fromkeys(schema_cache["tables"]))
            schema_cache["views"] = list(dict.fromkeys(schema_cache["views"]))
            schema_cache["procedures"] = list(dict.fromkeys(schema_cache["procedures"]))

            # Update cache - columns will be lazy-loaded when needed
            self._update_schema_cache(schema_cache, table_metadata)

        except Exception as e:
            self.notify(f"Error loading schema: {e}", severity="warning")
        finally:
            self._stop_schema_spinner()

    def _update_schema_cache(self: AutocompleteMixinHost, schema_cache: dict, table_metadata: dict | None = None) -> None:
        """Update the schema cache (called on main thread)."""
        self._schema_cache = schema_cache
        if table_metadata is not None:
            self._table_metadata = table_metadata
