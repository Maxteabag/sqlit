## ADDED Requirements

### Requirement: Provider package stays inert until registration
The Exasol provider package SHALL consist of `__init__.py` and `adapter.py` only. It MUST NOT
contain `provider.py`, because `providers/catalog.py::_discover_providers` walks every
subpackage of `providers/` and imports `<name>/provider.py`, which would register Exasol as a
live provider before `DatabaseType.EXASOL` and its connection schema exist.

`_discover_providers` SHALL skip a subpackage when it contains no `provider` module, so that a
package staged below registration cannot break discovery. Without this, the unconditional
import raises `ModuleNotFoundError` and no provider at all resolves.

#### Scenario: A subpackage without provider.py does not break discovery
- **WHEN** `get_supported_db_types()` is called with the adapter-only exasol package present
- **THEN** it returns the 29 registered providers
- **AND** no `ModuleNotFoundError` is raised

#### Scenario: Package contains no provider module
- **WHEN** the provider package directory is listed
- **THEN** it contains exactly `__init__.py` and `adapter.py`
- **AND** no `provider.py` is present

#### Scenario: Catalog discovery is unaffected
- **WHEN** `get_supported_db_types()` is called after this change
- **THEN** `"exasol"` is absent from the result
- **AND** `tests/test_schema_capabilities.py` passes unchanged (9 passed)

#### Scenario: Package docstring matches house style
- **WHEN** `__init__.py` is read
- **THEN** its entire content is the single docstring `"""Provider package."""`

### Requirement: Adapter subclasses DatabaseAdapter directly
`ExasolAdapter` SHALL extend `DatabaseAdapter`, not `CursorBasedAdapter`, because pyexasol is
a native WebSocket client that exposes no `.cursor()` method. Every abstract member of
`DatabaseAdapter` MUST be implemented.

#### Scenario: Class is importable and concrete
- **WHEN** `ExasolAdapter()` is instantiated
- **THEN** instantiation succeeds without `TypeError` for unimplemented abstract methods

#### Scenario: Base class choice
- **WHEN** the class declaration is inspected
- **THEN** `DatabaseAdapter` is its direct base
- **AND** `CursorBasedAdapter` does not appear in its MRO

### Requirement: Adapter declares Exasol's capability shape
The adapter SHALL expose the following capability properties, which
`build_adapter_provider` reads via `getattr`.

| Property | Value |
|---|---|
| `name` | `"Exasol"` |
| `install_extra` | `"exasol"` |
| `install_package` | `"pyexasol"` |
| `driver_import_names` | `("pyexasol",)` |
| `supports_multiple_databases` | `False` |
| `supports_cross_database_queries` | `False` |
| `supports_stored_procedures` | `True` |
| `supports_indexes` | `False` |
| `supports_triggers` | `False` |
| `supports_sequences` | `False` |
| `default_schema` | `""` |

The adapter MUST NOT override `supports_process_worker`: `process_worker.py` calls
`provider.connection_factory.connect(...)` inside the child process, so it opens its own
WebSocket rather than pickling one, and pyexasol returns plain picklable tuples.

#### Scenario: Capability properties report Exasol's shape
- **WHEN** each property in the table above is read from an `ExasolAdapter` instance
- **THEN** it returns the listed value

#### Scenario: Process worker support is inherited
- **WHEN** the class body is inspected
- **THEN** `supports_process_worker` is not defined on `ExasolAdapter`
- **AND** the inherited value is `True`

#### Scenario: Schema-only table display
- **WHEN** `format_table_name("MYSCHEMA", "T")` is called
- **THEN** it returns `"MYSCHEMA.T"`, because `default_schema` is empty so no schema is elided

### Requirement: Driver import is lazy
`connect()` SHALL obtain the driver through the inherited
`self._import_driver_module("pyexasol", ...)`, passing `driver_name=self.name`,
`extra_name=self.install_extra` and `package_name=self.install_package`. The module MUST NOT
be imported at module scope, so that a missing driver produces sqlit's normal install prompt
instead of an `ImportError` at collection time.

#### Scenario: Module imports without the driver installed
- **WHEN** `adapter.py` is imported in an environment with no `pyexasol`
- **THEN** the import succeeds

#### Scenario: Missing driver surfaces the install prompt
- **WHEN** `connect()` is called with no `pyexasol` installed
- **THEN** the error raised by `import_driver_module` names the `exasol` extra and the
  `pyexasol` package

### Requirement: Connection parameters are assembled from the endpoint and options
`connect()` SHALL require a TCP endpoint and raise `ValueError` otherwise. It SHALL build
`dsn` as host and port joined by a colon, where port is
`int(endpoint.port or get_default_port("exasol"))`, pass `schema` from
`config.get_option("schema", "")`, pass `autocommit=True`, then apply the TLS kwargs, then
apply `config.extra_options` last so callers can override anything.

#### Scenario: Endpoint is not TCP
- **WHEN** `connect()` is called with a config whose `tcp_endpoint` is `None`
- **THEN** `ValueError` is raised
- **AND** no connection attempt is made

#### Scenario: DSN combines host and port
- **WHEN** `connect()` runs for host `db.example.com` and port `8563`
- **THEN** `pyexasol.connect` receives `dsn` equal to `db.example.com:8563`

#### Scenario: Schema is forwarded
- **WHEN** the config option `schema` is `ANALYTICS`
- **THEN** `pyexasol.connect` receives `schema` equal to `ANALYTICS`

#### Scenario: Empty schema browses everything
- **WHEN** the config option `schema` is unset
- **THEN** `pyexasol.connect` receives `schema` equal to the empty string

#### Scenario: Autocommit is enabled
- **WHEN** `connect()` runs
- **THEN** `pyexasol.connect` receives `autocommit=True`

#### Scenario: Extra options are applied last
- **WHEN** `config.extra_options` sets `autocommit` to `False`
- **THEN** `pyexasol.connect` receives `autocommit=False`

### Requirement: Authentication method selects mutually exclusive credentials
`connect()` SHALL read `config.get_option("authenticator", "password")` and pass only that
method's credentials. Credentials for the other two methods MUST be absent from the kwargs,
not present-and-empty, because pyexasol rejects combinations of `password`, `access_token`
and `refresh_token`.

#### Scenario: Username and password
- **WHEN** `authenticator` is `password`
- **THEN** `pyexasol.connect` receives `user` and `password` from the endpoint
- **AND** `access_token` and `refresh_token` are absent from the kwargs

#### Scenario: OpenID access token
- **WHEN** `authenticator` is `access_token`
- **THEN** `pyexasol.connect` receives `access_token` from the `access_token` option
- **AND** `user`, `password` and `refresh_token` are absent from the kwargs

#### Scenario: OpenID refresh token
- **WHEN** `authenticator` is `refresh_token`
- **THEN** `pyexasol.connect` receives `refresh_token` from the `refresh_token` option
- **AND** `user`, `password` and `access_token` are absent from the kwargs

#### Scenario: Unset authenticator defaults to password
- **WHEN** the `authenticator` option is absent
- **THEN** the password credentials are used

### Requirement: TLS mode maps onto pyexasol encryption settings
A private `_tls_args(config)` helper SHALL translate the shared `tls_mode` option into
pyexasol kwargs using `get_tls_mode`, `tls_mode_verifies_cert` and `get_tls_files` from
`providers/tls.py`. This mapping matters because pyexasol defaults to `encryption=True` while
`exasol/docker-db` and most on-premise installations present a self-signed certificate, so an
unmapped connect fails certificate validation.

| `tls_mode` | kwargs |
|---|---|
| `default` | `encryption=True` |
| `disable` | `encryption=False` |
| `require` | `encryption=True`, `websocket_sslopt` with `cert_reqs` of `ssl.CERT_NONE` |
| `verify-ca` | `encryption=True`, `websocket_sslopt` with `cert_reqs` of `ssl.CERT_REQUIRED`, plus any configured files |
| `verify-full` | same as `verify-ca` |

Under the verifying modes, `ca_certs`, `certfile` and `keyfile` SHALL be included in
`websocket_sslopt` only when the corresponding path from `get_tls_files` is non-empty.

#### Scenario: Default mode encrypts
- **WHEN** `tls_mode` is absent or `default`
- **THEN** the kwargs contain `encryption=True`
- **AND** no `websocket_sslopt` key is present

#### Scenario: Disabled mode turns encryption off
- **WHEN** `tls_mode` is `disable`
- **THEN** the kwargs contain `encryption=False`
- **AND** no `websocket_sslopt` key is present

#### Scenario: Require mode encrypts without verifying
- **WHEN** `tls_mode` is `require`
- **THEN** the kwargs contain `encryption=True`
- **AND** `cert_reqs` in `websocket_sslopt` is `ssl.CERT_NONE`

#### Scenario: Verifying mode demands a valid certificate
- **WHEN** `tls_mode` is `verify-ca` or `verify-full`
- **THEN** the kwargs contain `encryption=True`
- **AND** `cert_reqs` in `websocket_sslopt` is `ssl.CERT_REQUIRED`

#### Scenario: Certificate files are forwarded when configured
- **WHEN** `tls_mode` is `verify-full` and `tls_ca`, `tls_cert` and `tls_key` are all set
- **THEN** `websocket_sslopt` contains `ca_certs`, `certfile` and `keyfile` with those paths

#### Scenario: Unconfigured certificate files are omitted
- **WHEN** `tls_mode` is `verify-ca` and only `tls_ca` is set
- **THEN** `websocket_sslopt` contains `ca_certs`
- **AND** `certfile` and `keyfile` are absent from `websocket_sslopt`

### Requirement: Introspection uses snapshot metadata reads
All introspection SHALL go through `conn.meta.*`, which prefixes each query with Exasol's
snapshot-execution hint and therefore cannot be blocked by metadata locks.

`conn.meta.list_tables()`, `list_views()` and `list_columns()` return **lists of dicts** with
UPPERCASE keys — pyexasol enforces `fetch_dict=True` on metadata reads specifically to stop
callers depending on column order — so results MUST be read by key, never by index.
`conn.meta.execute_snapshot()` returns an `ExaStatement`, so it requires an explicit
`.fetchall()`, which likewise yields dicts.

#### Scenario: Databases are not a concept in Exasol
- **WHEN** `get_databases(conn)` is called
- **THEN** it returns an empty list without querying the connection

#### Scenario: Tables are listed by schema and name
- **WHEN** `get_tables(conn)` is called
- **THEN** `conn.meta.list_tables()` is used
- **AND** each row yields a pair taken from the `TABLE_SCHEMA` and `TABLE_NAME` keys

#### Scenario: Views are listed by schema and name
- **WHEN** `get_views(conn)` is called
- **THEN** `conn.meta.list_views()` is used
- **AND** each row yields a pair taken from the `VIEW_SCHEMA` and `VIEW_NAME` keys

#### Scenario: Metadata rows are read by key
- **WHEN** a mocked `conn.meta.list_tables()` returns dicts whose keys are in a different
  order than declared
- **THEN** `get_tables` still returns the correct schema and name pairs

### Requirement: Column introspection reports primary keys
`get_columns(conn, table, database=None, schema=None)` SHALL read name and type from
`conn.meta.list_columns(schema, table)` using keys `COLUMN_NAME` and `COLUMN_TYPE`, and
determine the primary-key set with `conn.meta.execute_snapshot(...).fetchall()` against
`SYS.EXA_ALL_CONSTRAINT_COLUMNS` filtered on a `CONSTRAINT_TYPE` of `PRIMARY KEY` plus the
schema and table, reading `COLUMN_NAME` from each row. It returns `ColumnInfo` objects in the
order `list_columns` yields them.

#### Scenario: Columns carry name and declared type
- **WHEN** `get_columns` runs for a table with a decimal `ID` and a varchar `NAME`
- **THEN** it returns `ColumnInfo` entries with those names and their `COLUMN_TYPE` strings

#### Scenario: Primary key columns are flagged
- **WHEN** the constraint query reports `ID` as a primary-key column
- **THEN** the `ID` entry has `is_primary_key` set to `True`
- **AND** every other entry has `is_primary_key` set to `False`

#### Scenario: Table without a primary key
- **WHEN** the constraint query returns no rows
- **THEN** every returned `ColumnInfo` has `is_primary_key` set to `False`

#### Scenario: Composite primary key
- **WHEN** the constraint query reports both `A` and `B` as primary-key columns
- **THEN** both entries have `is_primary_key` set to `True`

### Requirement: Stored procedures are read from EXA_ALL_SCRIPTS
`get_procedures(conn, database=None)` SHALL query `SYS.EXA_ALL_SCRIPTS` through
`conn.meta.execute_snapshot(...).fetchall()`, filtering on a `SCRIPT_TYPE` of `SCRIPTING` —
the value Exasol uses for scripting programs, as distinct from `UDF`, `ADAPTER` and
`PREPROCESSOR` — and return the script names.

#### Scenario: Scripting programs are returned
- **WHEN** `EXA_ALL_SCRIPTS` contains a `SCRIPTING` entry named `MY_PROC`
- **THEN** `get_procedures` includes that name

#### Scenario: UDFs are not stored procedures
- **WHEN** `EXA_ALL_SCRIPTS` contains a `UDF` entry
- **THEN** `get_procedures` excludes it

### Requirement: Unsupported object types return empty lists
`get_indexes`, `get_triggers` and `get_sequences` SHALL each return an empty list without
querying the connection. All three MUST still be defined even though their capability flags
are `False`, because they are abstract on `DatabaseAdapter`. They are empty because Exasol's
indexes are auto-managed and unnamed, it has no triggers, and it uses IDENTITY columns rather
than sequences.

#### Scenario: Indexes, triggers and sequences are empty
- **WHEN** `get_indexes(conn)`, `get_triggers(conn)` and `get_sequences(conn)` are called
- **THEN** each returns an empty list
- **AND** no method on `conn` is invoked

### Requirement: Query execution returns columns, rows and a truncation flag
`execute_query(conn, query, max_rows=None)` SHALL execute via `conn.execute(query)` and
return a triple of columns, rows and a truncation flag. It MUST decide whether a result set
exists by testing `stmt.result_type` **before** fetching, because pyexasol raises
`ExaRuntimeError` with the message "Attempt to fetch from statement without result set" when
iterating a row-count statement. `result_type` is a public attribute whose values are exactly
`resultSet` and `rowCount`.

When `max_rows` is set, the implementation SHALL fetch one row beyond the limit to detect
truncation, then trim to `max_rows`. Rows MUST be returned as tuples.

#### Scenario: Unlimited fetch
- **WHEN** `execute_query` runs with `max_rows` of `None` on a statement returning 3 rows
- **THEN** it returns those 3 rows and the truncation flag is `False`

#### Scenario: Fewer rows than the limit
- **WHEN** `max_rows` is 10 and the statement has 4 rows
- **THEN** all 4 rows are returned and the truncation flag is `False`

#### Scenario: Exactly the limit is not truncation
- **WHEN** `max_rows` is 10 and the statement has exactly 10 rows
- **THEN** 10 rows are returned and the truncation flag is `False`

#### Scenario: One row over the limit is truncation
- **WHEN** `max_rows` is 10 and the statement has 11 rows
- **THEN** 10 rows are returned and the truncation flag is `True`

#### Scenario: Statement with no result set
- **WHEN** `execute_query` runs a statement whose `result_type` is `rowCount`
- **THEN** it returns empty columns, no rows, and a truncation flag of `False`
- **AND** no fetch method is called on the statement

### Requirement: Non-query execution returns the affected row count
`execute_non_query(conn, query)` SHALL execute via `conn.execute(query)` and return
`int(stmt.rowcount())`. `rowcount` is a **method** on `ExaStatement`, not a property, so it
MUST be called. No explicit commit is issued, because the connection is opened with
`autocommit=True`.

#### Scenario: Row count is returned
- **WHEN** an `INSERT` affecting 5 rows is executed
- **THEN** `execute_non_query` returns 5

#### Scenario: Rowcount is invoked as a method
- **WHEN** `execute_non_query` runs against a mocked statement
- **THEN** `rowcount()` is called
- **AND** the returned value is an integer

### Requirement: Connection test bypasses the cursor-based default
The adapter SHALL override `execute_test_query(conn)`, because the inherited implementation
calls `conn.cursor()`, which pyexasol does not provide. The override SHALL run
`conn.execute(self.test_query)` and then `fetchval()` on the result.

#### Scenario: Test query runs without a cursor
- **WHEN** `execute_test_query(conn)` is called
- **THEN** `conn.execute` is called with the inherited `SELECT 1` test query
- **AND** `fetchval()` is called on the result
- **AND** `conn.cursor` is never accessed

### Requirement: Identifiers are quoted with doubled double quotes
`quote_identifier(name)` SHALL wrap the name in double quotes and escape any embedded double
quote by doubling it.

#### Scenario: Plain identifier
- **WHEN** `quote_identifier` is called with `MY_TABLE`
- **THEN** it returns that name wrapped in double quotes

#### Scenario: Embedded double quote is doubled
- **WHEN** `quote_identifier` is called with a name containing one double quote
- **THEN** that double quote appears doubled inside the surrounding quotes

### Requirement: Select queries are schema-qualified and LIMIT-bounded
`build_select_query(table, limit, database=None, schema=None)` SHALL produce a
`SELECT * FROM` statement against the quoted schema-qualified table with a trailing `LIMIT`
clause, omitting the schema segment when the schema is empty.

#### Scenario: Schema-qualified select
- **WHEN** `build_select_query` is called for table `T` in schema `S` with a limit of 100
- **THEN** it selects from the quoted `S`-dot-`T` name and ends with `LIMIT 100`

#### Scenario: Unqualified select
- **WHEN** `build_select_query` is called for table `T` with a limit of 50 and no schema
- **THEN** it selects from the quoted `T` name alone and ends with `LIMIT 50`

#### Scenario: Identifiers in the select are quoted
- **WHEN** `build_select_query` is called with a lowercase table name
- **THEN** the name appears double-quoted, preserving its case
