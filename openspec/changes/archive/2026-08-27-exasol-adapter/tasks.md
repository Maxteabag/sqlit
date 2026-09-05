## 1. Package skeleton and capability declaration

Corresponds to plan.md step 1.

- [x] 1.1 Create `sqlit/domains/connections/providers/exasol/__init__.py` containing exactly
      the docstring `"""Provider package."""`. Do **not** create `provider.py` — see design D-context;
      it would activate auto-discovery and break `tests/test_schema_capabilities.py`.
- [x] 1.2 Create `sqlit/domains/connections/providers/exasol/adapter.py` with the module
      docstring, `from __future__ import annotations`, and imports of `ColumnInfo`,
      `DatabaseAdapter`, `IndexInfo`, `SequenceInfo`, `TableInfo`, `TriggerInfo` from
      `providers.adapters.base`, plus a `TYPE_CHECKING` import of `ConnectionConfig`.
- [x] 1.3 Declare `class ExasolAdapter(DatabaseAdapter)` (design D1 — not
      `CursorBasedAdapter`, pyexasol has no `.cursor()`).
- [x] 1.4 Add the driver-metadata properties: `name` -> `"Exasol"`, `install_extra` ->
      `"exasol"`, `install_package` -> `"pyexasol"`, `driver_import_names` -> `("pyexasol",)`.
- [x] 1.5 Add the capability properties per the spec table: `supports_multiple_databases`
      `False`, `supports_cross_database_queries` `False`, `supports_stored_procedures` `True`,
      `supports_indexes` `False`, `supports_triggers` `False`, `supports_sequences` `False`,
      `default_schema` `""`. Do **not** define `supports_process_worker` (design D7).
- [x] 1.6 Stub every remaining abstract method (`connect`, `get_databases`, `get_tables`,
      `get_views`, `get_columns`, `get_procedures`, `get_indexes`, `get_triggers`,
      `get_sequences`, `quote_identifier`, `build_select_query`, `execute_query`,
      `execute_non_query`) with correct signatures raising `NotImplementedError`, so the file
      is importable while groups 2-4 fill it in.
- [x] 1.7 Verify: `uv run python -c "from sqlit.domains.connections.providers.exasol.adapter import ExasolAdapter; print(ExasolAdapter)"`
      then `uv run ruff check sqlit && uv run mypy sqlit`.

## 2. Connection and TLS

Corresponds to plan.md step 2. Depends on group 1.

- [x] 2.1 Add `import ssl` and import `TLS_MODE_DISABLE`, `TLS_MODE_REQUIRE`, `get_tls_files`,
      `get_tls_mode`, `tls_mode_verifies_cert` from `providers.tls`; import `get_default_port`
      from `providers.registry` (design D4 — matches all ten existing TCP adapters).
- [x] 2.2 Implement `_tls_args(self, config) -> dict[str, Any]` per the spec's mapping table:
      `disable` -> `encryption=False`; `default` -> `encryption=True` with no
      `websocket_sslopt`; `require` -> `cert_reqs=ssl.CERT_NONE`; verifying modes ->
      `cert_reqs=ssl.CERT_REQUIRED`.
- [x] 2.3 In the verifying branch, add `ca_certs` / `certfile` / `keyfile` to
      `websocket_sslopt` only for non-empty paths from `get_tls_files` (spec scenario
      "Unconfigured certificate files are omitted").
- [x] 2.4 Implement `connect()`: resolve `config.tcp_endpoint`, raise `ValueError` when it is
      `None`, and lazily obtain the driver via `self._import_driver_module("pyexasol",
      driver_name=self.name, extra_name=self.install_extra, package_name=self.install_package)`.
      No module-scope `import pyexasol`.
- [x] 2.5 Build the base kwargs: `dsn` as host and port joined by a colon with port from
      `int(endpoint.port or get_default_port("exasol"))`, `schema` from
      `config.get_option("schema", "")`, and `autocommit=True`.
- [x] 2.6 Branch on `config.get_option("authenticator", "password")` and add **only** that
      method's credentials — `user`+`password`, or `access_token`, or `refresh_token` (design
      D5: the unused keys must be absent, not empty, or pyexasol rejects the combination).
- [x] 2.7 Apply `_tls_args(config)` and then `config.extra_options` last (design D6), and
      return `pyexasol.connect(**connect_args)`.
- [x] 2.8 Verify: `uv run ruff check sqlit && uv run mypy sqlit`. Behaviour is covered later by
      plan.md step 10.

## 3. Introspection

Corresponds to plan.md step 3. Depends on group 1.

- [x] 3.1 Implement `get_databases` returning an empty list without touching `conn`.
- [x] 3.2 Implement `get_tables` from `conn.meta.list_tables()`, reading each row by the
      `TABLE_SCHEMA` and `TABLE_NAME` **keys**. Design D2: these helpers return `list[dict]`
      with UPPERCASE keys because pyexasol enforces `fetch_dict=True` — positional indexing
      raises `KeyError` and `mypy` will not catch it.
- [x] 3.3 Implement `get_views` the same way from `conn.meta.list_views()`, keys `VIEW_SCHEMA`
      and `VIEW_NAME`.
- [x] 3.4 Implement the primary-key lookup in `get_columns`: `conn.meta.execute_snapshot(...)`
      against `SYS.EXA_ALL_CONSTRAINT_COLUMNS` filtered on `CONSTRAINT_TYPE = 'PRIMARY KEY'`
      plus `CONSTRAINT_SCHEMA` and `CONSTRAINT_TABLE`, then an explicit `.fetchall()` —
      `execute_snapshot` returns an `ExaStatement`, unlike the `list_*` helpers — collecting
      `COLUMN_NAME` into a set.
- [x] 3.5 Complete `get_columns` from `conn.meta.list_columns(schema, table)`, mapping
      `COLUMN_NAME` and `COLUMN_TYPE` into `ColumnInfo` with `is_primary_key` from the set
      built in 3.4, preserving the order `list_columns` yields.
- [x] 3.6 Implement `get_procedures` via `conn.meta.execute_snapshot(...).fetchall()` on
      `SYS.EXA_ALL_SCRIPTS` filtered to `SCRIPT_TYPE = 'SCRIPTING'` (the scripting-program
      value, as opposed to `UDF` / `ADAPTER` / `PREPROCESSOR`), returning `SCRIPT_NAME` values.
- [x] 3.7 Implement `get_indexes`, `get_triggers` and `get_sequences` as empty-list returns
      that never touch `conn` — abstract on the base class, so required despite the `False`
      capability flags.
- [x] 3.8 Verify: `uv run ruff check sqlit && uv run mypy sqlit`. Behaviour is covered later by
      plan.md step 11.

## 4. Query execution and identifier quoting

Corresponds to plan.md step 4. Depends on group 1.

- [x] 4.1 Implement `execute_query`: call `conn.execute(query)`, then **first** test
      `stmt.result_type != "resultSet"` and return empty columns/rows/`False`. Design D3: this
      guard must precede any fetch, because `ExaStatement.__next__` raises `ExaRuntimeError`
      ("Attempt to fetch from statement without result set") and `fetchmany()` iterates.
- [x] 4.2 Complete `execute_query`: with `max_rows` unset return `stmt.column_names()` and all
      rows as tuples with `truncated=False`; with `max_rows` set fetch `max_rows + 1`, set
      `truncated` from the overflow, and trim to `max_rows`.
- [x] 4.3 Implement `execute_non_query` as `int(conn.execute(query).rowcount())` —
      `rowcount` is a **method** on `ExaStatement`, not a property. No explicit commit;
      `autocommit=True` is set at connect time.
- [x] 4.4 Override `execute_test_query` to run `conn.execute(self.test_query).fetchval()`,
      since the inherited implementation at `providers/adapters/base.py` calls `conn.cursor()`.
- [x] 4.5 Implement `quote_identifier`: wrap in double quotes, doubling any embedded double
      quote.
- [x] 4.6 Implement `build_select_query` producing `SELECT * FROM` against the quoted
      schema-qualified name with a trailing `LIMIT`, omitting the schema segment when the
      schema is empty.
- [x] 4.7 Verify: `uv run ruff check sqlit && uv run mypy sqlit`. Behaviour is covered later by
      plan.md step 11.

## 5. Change gate and plan bookkeeping

- [x] 5.1 Confirm no `NotImplementedError` stubs from 1.6 remain in `adapter.py`.
- [x] 5.2 Confirm the package still contains only `__init__.py` and `adapter.py`, and that
      `uv run pytest tests/test_schema_capabilities.py -v` passes — proving Exasol is still
      undiscovered (spec: "Provider package stays inert until registration").
- [x] 5.3 Run the change gate: `uv run ruff check sqlit && uv run mypy sqlit`.
- [x] 5.4 In `plan.md`, set steps 1, 2, 3 and 4 to `done` in the Status table and update the
      progress count to `4 / 15 done`.
- [x] 5.5 Append a `plan.md` Session log row recording the two resolutions from design D3 and
      D2: `stmt.result_type` chosen over empty `column_names()` and checked before fetching;
      and `conn.meta.*` returning dicts with UPPERCASE keys rather than tuples, which corrects
      step 3's notation.
