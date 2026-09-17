## ADDED Requirements

### Requirement: Exasol unit tests run without the driver installed

The test files introduced by this change SHALL pass in an environment where `pyexasol` is not
importable. Where a test needs the driver, it SHALL supply a fake by seeding
`sys.modules["pyexasol"]` (`unittest.mock.patch.dict`), which `importlib.import_module` — and
therefore `_import_driver_module` — returns without touching the filesystem.

Tests MUST NOT patch `ExasolAdapter._import_driver_module` itself; the lazy-import call site,
including the `driver_name` / `extra_name` / `package_name` arguments that produce sqlit's install
prompt, is part of what is under test (design D2).

#### Scenario: Tests pass with no extras installed
- **WHEN** `uv sync --group test --no-dev` is used, as the default CI unit job does
- **AND** `uv run pytest tests/connections/providers/exasol/ -v` is run
- **THEN** every test passes
- **AND** no test is skipped for a missing driver

#### Scenario: Tests are collected by the default unit job
- **WHEN** the unit-test command from `.github/workflows/ci.yml` is run
- **THEN** the three new Exasol test files are collected
- **AND** no `--ignore` entry is required for them

#### Scenario: The driver fake is installed through sys.modules
- **WHEN** a test that calls `adapter.connect(config)` is inspected
- **THEN** it seeds a mock under the `"pyexasol"` key of `sys.modules`
- **AND** it reads the recorded call from that mock's `connect` attribute

### Requirement: Tests live in the per-provider test package

The tests SHALL reside in `tests/connections/providers/exasol/` as a package with an empty
`__init__.py`, mirroring `tests/connections/providers/hana/`, split as `test_schema.py`,
`test_connect.py` and `test_adapter.py`.

#### Scenario: Package layout
- **WHEN** the test tree is inspected
- **THEN** `tests/connections/providers/exasol/__init__.py` exists and is empty
- **AND** `test_schema.py`, `test_connect.py` and `test_adapter.py` sit beside it

#### Scenario: The directory is a single runnable gate
- **WHEN** `uv run pytest tests/connections/providers/exasol/ -v` is run
- **THEN** it collects and runs every Exasol unit test and nothing else

### Requirement: Conditional credential-field visibility is pinned

`test_schema.py` SHALL evaluate the `visible_when` predicates on `SCHEMA.fields` against a form-values
dict for each `authenticator` value, asserting that exactly the selected method's credential fields
are visible and the other methods' fields are hidden. Fields with no `visible_when` (`server`, `port`,
`authenticator`, `schema`) are always visible. No driver is involved.

#### Scenario: Password authentication
- **WHEN** the predicates are evaluated with `{"authenticator": "password"}`
- **THEN** `username` and `password` are visible
- **AND** `access_token` and `refresh_token` are hidden

#### Scenario: Access-token authentication
- **WHEN** the predicates are evaluated with `{"authenticator": "access_token"}`
- **THEN** `access_token` is visible
- **AND** `username`, `password` and `refresh_token` are hidden

#### Scenario: Refresh-token authentication
- **WHEN** the predicates are evaluated with `{"authenticator": "refresh_token"}`
- **THEN** `refresh_token` is visible
- **AND** `username`, `password` and `access_token` are hidden

#### Scenario: Absent authenticator falls back to password
- **WHEN** the predicates are evaluated with an empty dict
- **THEN** the visibility matches the `"password"` case, because each predicate defaults the lookup to
  `"password"`

#### Scenario: Unconditional fields stay visible
- **WHEN** the predicates are evaluated with any `authenticator` value
- **THEN** `server`, `port`, `authenticator` and `schema` carry no `visible_when` and are visible

### Requirement: Credentials passed to the driver match the selected authenticator, and only those

`test_connect.py` SHALL assert, for each `authenticator` value, both which credential kwargs
`pyexasol.connect` receives **and that the other methods' kwargs are absent from the call
entirely**. Asserting that an unused key is empty is not sufficient: pyexasol's login branches on
token truthiness, so a present-but-empty `access_token` silently reverts to password login
(design D3).

#### Scenario: Password authentication
- **WHEN** `connect()` runs with `authenticator` unset or `"password"`
- **THEN** the recorded kwargs contain `user` and `password` from the endpoint
- **AND** neither `access_token` nor `refresh_token` appears as a key

#### Scenario: Access-token authentication
- **WHEN** `connect()` runs with `authenticator == "access_token"`
- **THEN** the recorded kwargs contain `access_token`
- **AND** none of `user`, `password` or `refresh_token` appears as a key

#### Scenario: Refresh-token authentication
- **WHEN** `connect()` runs with `authenticator == "refresh_token"`
- **THEN** the recorded kwargs contain `refresh_token`
- **AND** none of `user`, `password` or `access_token` appears as a key

### Requirement: Endpoint, schema and autocommit kwargs are pinned

`test_connect.py` SHALL assert the non-credential kwargs `connect()` builds from the config: the
`dsn` string, the port fallback, the `schema` option and `autocommit`. It SHALL also cover the
rejection path for a config that carries no TCP endpoint.

#### Scenario: DSN is host and port joined by a colon
- **WHEN** `connect()` runs against an endpoint with host `db.example.com` and port `1234`
- **THEN** the recorded kwargs contain `dsn == "db.example.com:1234"`

#### Scenario: Absent port falls back to the registered default
- **WHEN** the endpoint carries no port
- **THEN** the `dsn` port segment is `8563`, resolved through `get_default_port("exasol")`

#### Scenario: Schema option is forwarded
- **WHEN** the `schema` option is set to `TEST_SQLIT`
- **THEN** the recorded kwargs contain `schema == "TEST_SQLIT"`
- **AND** when the option is unset the value is the empty string, not omitted

#### Scenario: Autocommit is enabled at connect time
- **WHEN** `connect()` runs with any authenticator
- **THEN** the recorded kwargs contain `autocommit is True`

#### Scenario: A non-TCP configuration is rejected before importing the driver
- **WHEN** `connect()` is called with a config whose `tcp_endpoint` is `None`
- **THEN** `ValueError` is raised
- **AND** the fake driver's `connect` is never called

### Requirement: The TLS mode mapping is pinned for every mode

`test_connect.py` SHALL cover all five `tls_mode` values and assert the resulting `encryption` and
`websocket_sslopt` kwargs.

#### Scenario: Encryption disabled
- **WHEN** `tls_mode` is `disable`
- **THEN** the recorded kwargs contain `encryption is False`
- **AND** no `websocket_sslopt` key is present

#### Scenario: Driver default
- **WHEN** `tls_mode` is `default` or unset
- **THEN** the recorded kwargs contain `encryption is True`
- **AND** no `websocket_sslopt` key is present

#### Scenario: Encrypted without verification
- **WHEN** `tls_mode` is `require`
- **THEN** the recorded kwargs contain `encryption is True`
- **AND** `websocket_sslopt == {"cert_reqs": ssl.CERT_NONE}`

#### Scenario: Verifying modes request certificate validation
- **WHEN** `tls_mode` is `verify-ca` or `verify-full`
- **THEN** the recorded kwargs contain `encryption is True`
- **AND** `websocket_sslopt["cert_reqs"] == ssl.CERT_REQUIRED`

#### Scenario: Configured certificate files are forwarded
- **WHEN** `tls_mode` is a verifying mode and `tls_ca`, `tls_cert` and `tls_key` are set
- **THEN** `websocket_sslopt` carries them as `ca_certs`, `certfile` and `keyfile`

#### Scenario: Unconfigured certificate files are omitted
- **WHEN** `tls_mode` is a verifying mode and the certificate options are unset or whitespace
- **THEN** `websocket_sslopt` contains only `cert_reqs`
- **AND** no `ca_certs`, `certfile` or `keyfile` key is present

### Requirement: extra_options pass through and win on conflict

`test_connect.py` SHALL assert that `config.extra_options` reaches the driver verbatim and that it
overrides the kwargs `connect()` computes, since it is applied last.

#### Scenario: Unknown options reach the driver
- **WHEN** `extra_options` contains a key sqlit does not know
- **THEN** the recorded kwargs contain that key and value verbatim

#### Scenario: extra_options override computed kwargs
- **WHEN** `extra_options` sets a key that `connect()` also computes, such as `encryption`
- **THEN** the recorded kwargs carry the `extra_options` value

### Requirement: The introspection row-shape contract is pinned

`test_adapter.py` SHALL drive introspection off a mocked `conn.meta`, returning
already-fetched lists of dicts with UPPERCASE keys for the `list_*` helpers and an object requiring
`.fetchall()` for `execute_snapshot`. A test that fed tuples would pass against an index-based
implementation and so would not pin the contract at all.

#### Scenario: Tables are read by key
- **WHEN** `conn.meta.list_tables()` yields dicts with `TABLE_SCHEMA` and `TABLE_NAME`
- **THEN** `get_tables` returns the corresponding `(schema, name)` tuples in order

#### Scenario: Views are read by key
- **WHEN** `conn.meta.list_views()` yields dicts with `VIEW_SCHEMA` and `VIEW_NAME`
- **THEN** `get_views` returns the corresponding `(schema, name)` tuples in order

#### Scenario: Columns combine type and primary-key information
- **WHEN** `execute_snapshot` yields a primary-key row for `ID` and `list_columns` yields `ID` then
  `NAME`
- **THEN** `get_columns` returns `ColumnInfo("ID", <type>, is_primary_key=True)` followed by
  `ColumnInfo("NAME", <type>, is_primary_key=False)`
- **AND** the order from `list_columns` is preserved

#### Scenario: The primary-key query is snapshot-executed and parameterised
- **WHEN** `get_columns` runs for schema `S` and table `T`
- **THEN** the query goes through `conn.meta.execute_snapshot`, not `conn.execute`
- **AND** it filters on `CONSTRAINT_TYPE = 'PRIMARY KEY'`
- **AND** the schema and table are passed as query parameters rather than interpolated

#### Scenario: A table with no primary key yields no flagged column
- **WHEN** the primary-key snapshot returns no rows
- **THEN** every returned `ColumnInfo` has `is_primary_key` false

#### Scenario: An unspecified schema is passed through as empty
- **WHEN** `get_columns` is called without a schema
- **THEN** `list_columns` receives the empty string
- **AND** this pins a deliberate spec-faithful choice — the path is unreachable from the explorer,
  and no fallback is substituted (design D8)

#### Scenario: Procedures come from the scripting scripts
- **WHEN** `get_procedures` runs
- **THEN** it snapshot-executes against `SYS.EXA_ALL_SCRIPTS` filtered to `SCRIPT_TYPE = 'SCRIPTING'`
- **AND** returns the `SCRIPT_NAME` values

#### Scenario: Unsupported object kinds return empty without querying
- **WHEN** `get_databases`, `get_indexes`, `get_triggers` or `get_sequences` is called
- **THEN** each returns an empty list
- **AND** the connection mock records no call at all

### Requirement: Result-set detection precedes any fetch

`test_adapter.py` SHALL assert that `execute_query` inspects `stmt.result_type` before any fetch,
because `ExaStatement.__next__` raises `ExaRuntimeError` for a `rowCount` statement and `fetchmany()`
iterates.

Every statement mock MUST set `result_type` explicitly: on a bare `MagicMock` the inequality is
trivially true, which would let a result-set test pass while asserting nothing (see the second risk
in design.md).

#### Scenario: A row-count statement returns empty without fetching
- **WHEN** `execute_query` runs against a statement whose `result_type` is `rowCount`
- **THEN** it returns empty columns, empty rows and `truncated` false
- **AND** neither `fetchall` nor `fetchmany` is called on the statement

#### Scenario: A result-set statement is fetched
- **WHEN** `execute_query` runs against a statement whose `result_type` is `resultSet`
- **THEN** the column names come from `stmt.column_names()`
- **AND** the rows are returned as tuples

### Requirement: The truncation flag is pinned at the max_rows boundary

`test_adapter.py` SHALL cover the `max_rows` boundary in both directions: `execute_query` requests
`max_rows + 1` rows to detect truncation, MUST report it, and MUST trim the surplus before
returning.

#### Scenario: Unlimited fetch is never truncated
- **WHEN** `execute_query` runs with `max_rows` unset
- **THEN** all rows from `fetchall` are returned
- **AND** `truncated` is false

#### Scenario: Exactly max_rows rows available
- **WHEN** `max_rows` is 2 and the statement yields 2 rows
- **THEN** 2 rows are returned
- **AND** `truncated` is false

#### Scenario: More than max_rows rows available
- **WHEN** `max_rows` is 2 and the statement yields 3 rows
- **THEN** exactly 2 rows are returned
- **AND** `truncated` is true

#### Scenario: One extra row is requested
- **WHEN** `execute_query` runs with `max_rows` set to 2
- **THEN** `fetchmany` is called with 3

### Requirement: Row counts and the test query use pyexasol's statement API

`test_adapter.py` SHALL pin the two places the adapter departs from the DB-API shape of its base
class: `rowcount` is a **method** on `ExaStatement` rather than a property, and `execute_test_query`
is overridden because the inherited implementation calls `conn.cursor()`, which pyexasol does not
provide.

#### Scenario: rowcount is invoked as a method
- **WHEN** `execute_non_query` runs
- **THEN** the statement's `rowcount` is **called**, not read as a property
- **AND** the returned value is an `int`

#### Scenario: No explicit commit is issued
- **WHEN** `execute_non_query` runs
- **THEN** the connection mock records no `commit` call, because `autocommit=True` is set at connect
  time

#### Scenario: The connection test avoids cursor()
- **WHEN** `execute_test_query` runs
- **THEN** `conn.execute("SELECT 1")` is called and `fetchval()` is taken from the result
- **AND** `conn.cursor` is never accessed

### Requirement: Identifier quoting and select building are pinned

`test_adapter.py` SHALL assert that `quote_identifier` wraps in double quotes and doubles any
embedded double quote, and that `build_select_query` MUST omit the schema segment entirely when no
schema is given rather than emitting a leading dot.

#### Scenario: Plain identifier
- **WHEN** `quote_identifier("MY_TABLE")` is called
- **THEN** it returns `"MY_TABLE"` wrapped in double quotes

#### Scenario: Embedded double quote is doubled
- **WHEN** `quote_identifier` is called with an identifier containing a double quote
- **THEN** that character is doubled inside the quoted result

#### Scenario: Schema-qualified select
- **WHEN** `build_select_query("T", 10, schema="S")` is called
- **THEN** it returns a `SELECT * FROM` against the quoted `"S"."T"` with `LIMIT 10`

#### Scenario: Select without a schema omits the schema segment
- **WHEN** `build_select_query("T", 10)` is called with no schema
- **THEN** the result references only the quoted table, with no leading dot
