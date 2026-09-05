# Add Exasol provider to sqlit

> **Multi-session plan.** Read `## How to use this plan` before doing anything.

---

## How to use this plan

This plan is designed to be implemented across several sessions. The status table below is the
single source of truth for what is done.

**Protocol for every session:**

1. Read the **Status** table. Ignore prose elsewhere until you know where you are.
2. Pick work: the lowest-numbered step whose `Depends on` steps are all `done`.
3. **If that step belongs to an atomic group, you must take the entire group in this session
   or take nothing.** Atomic groups leave the repo red (failing tests / failing CI) if split
   across sessions. See `## Atomic groups`.
4. Set the picked steps to `wip` in the Status table before starting.
5. Implement, then run the step's **Verify** command. Only when it passes, set the step to `done`.
6. Append one line to the **Session log**.
7. If you stop mid-step, leave it `wip` and write what is half-done in the Session log. A `wip`
   step means "read the diff before continuing" — do not assume it is untouched.

**States:** `todo` / `wip` / `done` / `skipped` (with a reason in the Session log).

**Never** mark a step `done` without running its Verify command. **Never** start a step in an
atomic group unless the whole group fits in the session.

---

## Status

| # | Step | Group | Depends on | State |
|---|------|-------|-----------|-------|
| 1 | Package skeleton + `ExasolAdapter` shell & capabilities | — | — | `done` |
| 2 | `adapter.py`: `connect()` + `_tls_args()` | — | 1 | `done` |
| 3 | `adapter.py`: introspection methods | — | 1 | `done` |
| 4 | `adapter.py`: query execution + identifier quoting | — | 1 | `done` |
| 5 | `schema.py` | **ACT** | 1 | `done` |
| 6 | `DatabaseType.EXASOL` + display order | **ACT** | — | `done` |
| 7 | `provider.py` + `register_provider(SPEC)` | **ACT** | 2, 3, 4, 5, 6 | `done` |
| 8 | `pyproject.toml`: extra, mypy override, pytest marker | — | — | `done` |
| 9 | Unit tests: `test_schema.py` | — | 5, 7 | `done` |
| 10 | Unit tests: `test_connect.py` | — | 2, 7, 8 | `done` |
| 11 | Unit tests: `test_adapter.py` | — | 3, 4, 7, 8 | `done` |
| 12 | Docker compose service + `tests/fixtures/exasol.py` + conftest | **INT** | 7, 8 | `done` |
| 13 | `tests/test_exasol.py` | **INT** | 12 | `done` |
| 14 | `.github/workflows/ci.yml`: unit-job ignore + `test-exasol` job | **INT** | 13 | `done` |
| 15 | Docs: `CONTRIBUTING.md` + `README.md` | — | 7 | `done` |

**Progress: 15 / 15 done.** Update this count when you change the table.

---

## Atomic groups

A group must be completed within one session. Splitting it leaves the branch failing.

### Group `ACT` — steps 5, 6, 7 (activation)

**Why atomic:** providers are auto-discovered. `providers/catalog.py:22` (`_discover_providers`)
walks every subpackage of `providers/` and imports `<name>/provider.py`. The instant `provider.py`
exists, Exasol is a live registered provider, and:

- `tests/test_schema_capabilities.py::TestCatalogConsistency::test_database_type_enum_matches_schema`
  asserts `{t.value for t in DatabaseType} == set(get_supported_db_types())` — **exact set
  equality**. `provider.py` without step 6 fails. Step 6 without `provider.py` also fails.
- The same test class calls `get_connection_schema(db_type)` for every discovered type and asserts
  `schema.db_type == db_type` and `schema.display_name == get_display_name(db_type)`. So `schema.py`
  (step 5) must exist and agree with `ProviderSpec` in the same commit.

**Estimated size:** small — three short files/edits. Comfortably one session.

**Ordering within the group:** write 5 and 6 first, `provider.py` last. `provider.py` is the switch
that turns discovery on.

### Group `INT` — steps 13, 14 (integration test + CI)

**Why atomic:** the unit-test CI job excludes integration tests *by filename*
(`.github/workflows/ci.yml:71-82`). Creating `tests/test_exasol.py` without adding
`--ignore=tests/test_exasol.py` to that job means CI collects and runs a test that needs a Docker
container it does not have.

Step 12 (compose + fixtures) is safe on its own because the fixture guards with `pytest.skip`, but
13 and 14 must land together.

**Recommended merge:** take 12 + 13 + 14 in one session. 12 alone delivers nothing testable.

### Steps 2, 3, 4 — *not* atomic, but keep them before `ACT`

`provider.py`'s `provider_factory` imports `ExasolAdapter` **lazily**, so an incomplete `adapter.py`
breaks no test (mypy flags abstract classes only at instantiation, and nothing instantiates it until
a connection is opened). This is why the adapter is built first, in pieces, and activation comes
after: the repo is never in a "provider is selectable but crashes on connect" state between sessions.

If you have a large session available, 1-4 together is a clean unit of work.

---

## Context

sqlit ships ~29 database providers but not Exasol. We want to add one and upstream it as a PR
to `Maxteabag/sqlit`.

**There is no "adding a new dialect" documentation in this repo.** `CONTRIBUTING.md` covers only
dev setup, test commands, per-database env vars, and the product vision. `docs/` is screenshots
and demo GIFs. `.github/` has only CI workflows. So the convention has to be read off the code —
which is what this plan encodes.

The convention: providers are **auto-discovered** (see Group `ACT` above). Adding a provider is
therefore: drop in a 4-file package, then patch the handful of places that are *not* auto-discovered.

Closest existing templates: `providers/hana/` (single database, many schemas, enterprise DB) and
`providers/snowflake/` (auth-method dropdown).

## Decisions

| Decision | Choice |
|---|---|
| Driver | `pyexasol` (2.3.2, requires-python `>=3.10,<3.15` — compatible with sqlit's `>=3.10`) |
| Base class | `DatabaseAdapter` directly, **not** `CursorBasedAdapter` — pyexasol is a native WebSocket client, not DB-API 2.0 |
| Schema model | Schema-only, HANA-style: `supports_multiple_databases=False`, `get_databases()` returns `[]`, tables grouped by schema in the explorer |
| Auth | Dropdown: Username & Password / OpenID Access Token / OpenID Refresh Token |
| TLS | Reuse shared `TLS_FIELDS` + `providers/tls.py` helpers, mapped to pyexasol `encryption` + `websocket_sslopt` |
| Tests | Mocked unit tests **and** Docker integration tests (`exasol/docker-db`, enterprise profile) |

---

# Steps

## Step 1 — Package skeleton + `ExasolAdapter` shell & capabilities

**Group:** — | **Depends on:** — | **State:** `done`

**Files:** `sqlit/domains/connections/providers/exasol/__init__.py`,
`sqlit/domains/connections/providers/exasol/adapter.py`

`__init__.py` is `"""Provider package."""` — matches every other provider.

Create `class ExasolAdapter(DatabaseAdapter)` with the capability properties below and every
abstract method present but raising `NotImplementedError` (filled in by steps 2-4). Capabilities are
declared as properties; `build_adapter_provider` reads them via `getattr`.

| Property | Value | Why |
|---|---|---|
| `supports_multiple_databases` | `False` | Exasol has no database layer |
| `supports_cross_database_queries` | `False` | Mirrors `HanaAdapter`; only affects the unused `requires_database_selection()` and the database segment in `qualified_name()`, which is always empty here |
| `supports_stored_procedures` | `True` | Exposed from `EXA_ALL_SCRIPTS` |
| `supports_indexes` | `False` | Exasol indexes are auto-managed and unnamed |
| `supports_triggers` | `False` | Exasol has no triggers |
| `supports_sequences` | `False` | Exasol uses IDENTITY columns |
| `default_schema` | `""` | No universal default; every table stays schema-qualified |

Do **not** override `supports_process_worker`. `process_worker.py:327` calls
`provider.connection_factory.connect(...)` *inside* the child process — it opens its own connection
rather than pickling one — so the WebSocket is fine, and pyexasol returns plain picklable tuples.
(`SurrealDBAdapter` disables it, but that reasoning does not apply here.)

**Verify:**

```
uv run python -c "from sqlit.domains.connections.providers.exasol.adapter import ExasolAdapter; print(ExasolAdapter)"
uv run ruff check sqlit && uv run mypy sqlit
```

---

## Step 2 — `adapter.py`: `connect()` + `_tls_args()`

**Group:** — | **Depends on:** 1 | **State:** `done`

**Files:** `providers/exasol/adapter.py`

Lazily import the driver through the inherited `self._import_driver_module("pyexasol", ...)`, so a
missing driver produces sqlit's normal install prompt:

```python
connect_args = {"dsn": f"{host}:{port}", "schema": config.get_option("schema", ""), "autocommit": True}
# authenticator == "password"       -> user=..., password=...
# authenticator == "access_token"   -> access_token=...
# authenticator == "refresh_token"  -> refresh_token=...
connect_args.update(self._tls_args(config))
connect_args.update(config.extra_options)
return pyexasol.connect(**connect_args)
```

`autocommit=True` matches the house convention (`postgresql/adapter.py:124`, `mysql/adapter.py:87`,
`mssql/adapter.py:265`) and is also pyexasol's default.

`_tls_args(config)` uses `get_tls_mode`, `tls_mode_verifies_cert`, `get_tls_files` from
`providers/tls.py`:

| `tls_mode` | pyexasol kwargs |
|---|---|
| `default` | `encryption=True` (pyexasol default) |
| `disable` | `encryption=False` |
| `require` | `encryption=True, websocket_sslopt={"cert_reqs": ssl.CERT_NONE}` |
| `verify-ca` / `verify-full` | `encryption=True, websocket_sslopt={"cert_reqs": ssl.CERT_REQUIRED, "ca_certs": ..., "certfile": ..., "keyfile": ...}` |

This matters: pyexasol defaults to `encryption=True`, and both `exasol/docker-db` and most on-prem
installs use a self-signed cert, so without `require` a naive connect fails cert validation.

**Verify:** `uv run ruff check sqlit && uv run mypy sqlit` (behaviour is covered by step 10).

---

## Step 3 — `adapter.py`: introspection methods

**Group:** — | **Depends on:** 1 | **State:** `done`

**Files:** `providers/exasol/adapter.py`

Use `conn.meta.*`, which wraps every query in Exasol's `/*snapshot execution*/` hint and so cannot be
blocked by metadata locks. This is the pyexasol-recommended path and is strictly better than
hand-rolled SQL.

| Method | Implementation |
|---|---|
| `get_databases` | `return []` |
| `get_tables` | `conn.meta.list_tables()` -> `(TABLE_SCHEMA, TABLE_NAME)` |
| `get_views` | `conn.meta.list_views()` -> `(VIEW_SCHEMA, VIEW_NAME)` |
| `get_columns` | `conn.meta.list_columns(schema, table)` for name/type + `conn.meta.execute_snapshot` on `SYS.EXA_ALL_CONSTRAINT_COLUMNS WHERE CONSTRAINT_TYPE = 'PRIMARY KEY'` for the PK set -> `ColumnInfo(name, data_type, is_primary_key)` |
| `get_procedures` | `conn.meta.execute_snapshot` on `SYS.EXA_ALL_SCRIPTS` (columns `SCRIPT_SCHEMA`, `SCRIPT_NAME`, `SCRIPT_TYPE`) |
| `get_indexes` / `get_triggers` / `get_sequences` | `return []` (abstract on the base class, must be defined even though the capability flags are `False`) |

All system-table column names above are verified against the Exasol docs.

**Verify:** `uv run ruff check sqlit && uv run mypy sqlit` (behaviour is covered by step 11).

---

## Step 4 — `adapter.py`: query execution + identifier quoting

**Group:** — | **Depends on:** 1 | **State:** `done`

**Files:** `providers/exasol/adapter.py`

This is the reason this cannot be `CursorBasedAdapter` — pyexasol has no `.cursor()`.

```python
def execute_query(self, conn, query, max_rows=None):
    stmt = conn.execute(query)
    columns = stmt.column_names()
    if not columns:
        return [], [], False
    if max_rows is None:
        return columns, list(stmt.fetchall()), False
    rows = stmt.fetchmany(max_rows + 1)          # one extra to detect truncation
    truncated = len(rows) > max_rows
    return columns, [tuple(r) for r in rows[:max_rows]], truncated

def execute_non_query(self, conn, query):
    return int(conn.execute(query).rowcount())   # rowcount() is a method, not a property
```

Also override `execute_test_query` (the base implementation at `adapters/base.py:215` calls
`conn.cursor()`): `conn.execute("SELECT 1").fetchval()`.

`quote_identifier` -> double quotes with `"` doubled. `build_select_query` ->
`SELECT * FROM "S"."T" LIMIT n`.

**Open item to resolve in this step:** the code above uses `column_names()` being empty to mean "no
result set". `stmt.result_type` exists and may be cleaner — confirm against the installed pyexasol
and use whichever is public API. Record the choice in the Session log.

**Verify:** `uv run ruff check sqlit && uv run mypy sqlit` (behaviour is covered by step 11).

---

## Step 5 — `schema.py`

**Group:** **ACT** (with 6, 7) | **Depends on:** 1 | **State:** `done`

**Files:** `providers/exasol/schema.py`

Follows `providers/snowflake/schema.py` for the conditional-visibility pattern and
`providers/clickhouse/schema.py` for the `+ SSH_FIELDS + TLS_FIELDS` tail.

```python
SCHEMA = ConnectionSchema(
    db_type="exasol",
    display_name="Exasol",
    fields=(
        _server_field(),                    # from schema_helpers
        _port_field("8563"),
        SchemaField("authenticator", "Authentication", FieldType.DROPDOWN,
                    options=(SelectOption("password", "Username & Password"),
                             SelectOption("access_token", "OpenID Access Token"),
                             SelectOption("refresh_token", "OpenID Refresh Token")),
                    default="password"),
        _username_field(),                  # visible_when authenticator == "password"
        _password_field(),                  # visible_when authenticator == "password"
        SchemaField("access_token",  "Access Token",  FieldType.PASSWORD, ...),   # visible_when access_token
        SchemaField("refresh_token", "Refresh Token", FieldType.PASSWORD, ...),   # visible_when refresh_token
        SchemaField("schema", "Schema", placeholder="(empty = browse all)"),
    ) + SSH_FIELDS + TLS_FIELDS,
    default_port="8563",
    has_advanced_auth=True,
)
```

Field name `authenticator` (not `auth_type`) deliberately mirrors Snowflake and avoids the legacy
top-level `auth_type` key that `ConnectionConfig.from_dict` special-cases (`domain/config.py:158`).

Non-endpoint fields (`authenticator`, `access_token`, `refresh_token`, `schema`) land in
`config.options` automatically (`config.py:240-246`) and are read with `config.get_option(...)`.
The CLI derives `--authenticator` / `--access-token` / `--schema` flags from these fields for free
(`cli/helpers.py:43`).

`display_name` must be exactly `"Exasol"` — step 7's `ProviderSpec.display_name` has to match, or
`test_display_names_match_schema` fails.

**Verify:** part of the Group `ACT` verify at step 7.

---

## Step 6 — `DatabaseType.EXASOL` + display order

**Group:** **ACT** (with 5, 7) | **Depends on:** — | **State:** `done`

**Files:** `sqlit/domains/connections/domain/config.py`

Add `EXASOL = "exasol"` to `DatabaseType` (enum starts line 11; place it between `DB2` and
`FIREBIRD`) **and** an entry in `DATABASE_TYPE_DISPLAY_ORDER` (line 44) near the other enterprise
engines, after `TERADATA`.

Both are needed: `tests/test_schema_capabilities.py` asserts the enum set *exactly equals* the
discovered provider set, and the connection picker renders only from the display order
(`ui/screens/connection.py:331`). Nothing tests the display order for completeness, so a missing
entry here fails silently as "Exasol is not in the picker".

**Verify:** part of the Group `ACT` verify at step 7.

---

## Step 7 — `provider.py` + `register_provider(SPEC)`

**Group:** **ACT** (with 5, 6) | **Depends on:** 2, 3, 4, 5, 6 | **State:** `done`

**Files:** `providers/exasol/provider.py`

Same shape as `providers/teradata/provider.py`:

```python
SPEC = ProviderSpec(
    db_type="exasol", display_name="Exasol",
    schema_path=("sqlit.domains.connections.providers.exasol.schema", "SCHEMA"),
    supports_ssh=True, has_advanced_auth=True, default_port="8563",
    badge_label="Exasol", url_schemes=("exasol", "exa"),
    display_info=_display_info,          # "host:port/SCHEMA"
    provider_factory=_provider_factory,  # lazily imports ExasolAdapter
    docker_detector=DockerDetector(image_patterns=("exasol/docker-db",), default_user="sys"),
)
register_provider(SPEC)
```

**Verify (this is the Group `ACT` gate — must pass before marking 5, 6, 7 `done`):**

```
uv run pytest tests/test_schema_capabilities.py -v
uv run ruff check sqlit && uv run mypy sqlit
```

---

## Step 8 — `pyproject.toml`: extra, mypy override, pytest marker

**Group:** — | **Depends on:** — | **State:** `todo`

**Files:** `pyproject.toml`

- `exasol = ["pyexasol>=2.0.0"]` extra; add the same pin to `all`.
- Add `"pyexasol"` to the mypy `ignore_missing_imports` override list (~line 228).
- Add `"exasol: Exasol database tests"` to `[tool.pytest.ini_options] markers`.

**Verify:**

```
uv sync --extra exasol
uv run python -c "import pyexasol; print(pyexasol.__version__)"
uv run mypy sqlit
```

---

## Step 9 — Unit tests: `test_schema.py`

**Group:** — | **Depends on:** 5, 7 | **State:** `todo`

**Files:** `tests/connections/providers/exasol/__init__.py`,
`tests/connections/providers/exasol/test_schema.py`

Assert the `visible_when` predicates hide/show the right credential fields for each `authenticator`
value. No driver needed.

**Verify:** `uv run pytest tests/connections/providers/exasol/test_schema.py -v`

---

## Step 10 — Unit tests: `test_connect.py`

**Group:** — | **Depends on:** 2, 7, 8 | **State:** `todo`

**Files:** `tests/connections/providers/exasol/test_connect.py`

Mocked, runs in the default CI job. Follow
`tests/connections/providers/hana/test_get_columns.py` (`MagicMock` connection, assert on the SQL and
kwargs actually passed):

- each `authenticator` value produces the right `pyexasol.connect` kwargs (`password` vs
  `access_token` vs `refresh_token`, **and that the unused ones are absent**);
- each `tls_mode` produces the right `encryption` / `websocket_sslopt`;
- `extra_options` passthrough.

**Note:** patch the module that `_import_driver_module("pyexasol", ...)` returns rather than relying
on pyexasol being installed, so this test also passes in the no-extras unit job. If patching the lazy
import proves awkward, that is the one place this step may need a design decision — record it in the
Session log.

**Verify:** `uv run pytest tests/connections/providers/exasol/test_connect.py -v`

---

## Step 11 — Unit tests: `test_adapter.py`

**Group:** — | **Depends on:** 3, 4, 7, 8 | **State:** `todo`

**Files:** `tests/connections/providers/exasol/test_adapter.py`

- `get_tables` / `get_views` / `get_columns` shapes off mocked `conn.meta.*`; PK detection.
- `execute_query` truncation flag at the `max_rows` boundary (exactly `max_rows` rows -> not
  truncated; `max_rows + 1` -> truncated and trimmed).
- `execute_non_query` calls `rowcount()` (method, not property).
- `quote_identifier` escaping of an embedded double quote.

**Verify:** `uv run pytest tests/connections/providers/exasol/ -v`

---

## Step 12 — Docker compose service + fixtures + conftest

**Group:** **INT** (recommended: merge with 13, 14) | **Depends on:** 7, 8 | **State:** `done`

**Files:** `infra/docker/docker-compose.test.yml`, `tests/fixtures/exasol.py`, `tests/conftest.py`

Compose: an `exasol` service under the existing `enterprise` profile (alongside `db2` /
`oracle11g`), since the image is large and slow: `image: exasol/docker-db:latest-8`,
`privileged: true`, `stop_grace_period: 120s`, `ports: ["${EXASOL_PORT:-8563}:8563"]`.

`tests/fixtures/exasol.py` mirrors `tests/fixtures/clickhouse.py`: env-var constants, `is_port_open`
guard, `pytest.skip` when the container or driver is absent, and an `exasol_db` fixture that
creates/drops a `TEST_SQLIT` schema. Defaults `sys` / `exasol` (the `docker-db` defaults).

Register with `from tests.fixtures.exasol import *` in `tests/conftest.py` (the fixture import block
is alphabetical, starting line 5).

**The fixture module must be import-safe with no pyexasol installed** — no top-level driver import —
because `conftest.py` is imported by the unit-test job.

**Verify:**

```
docker compose -f infra/docker/docker-compose.test.yml --profile enterprise config
uv run pytest tests/connections -v          # conftest still imports cleanly
```

---

## Step 13 — `tests/test_exasol.py`

**Group:** **INT** — must land with 14 | **Depends on:** 12 | **State:** `done`

**Files:** `tests/test_exasol.py`

`TestExasolIntegration(BaseDatabaseTests)` with a `DatabaseTestConfig(db_type="exasol",
display_name="Exasol", ...)`, plus a `test_create_exasol_connection` CLI test like
`tests/test_clickhouse.py:26`.

The connection must be created with `--tls-mode require`, since `docker-db` presents a self-signed
cert — which conveniently makes the integration test exercise the TLS mapping from step 2.

**Do not mark `done` without step 14.** This file breaks the unit CI job until 14 adds its ignore.

**Verify:** with the container up (see step 12; this image takes several minutes to boot):
`uv run pytest tests/test_exasol.py -v`

---

## Step 14 — `.github/workflows/ci.yml`

**Group:** **INT** — must land with 13 | **Depends on:** 13 | **State:** `done`

**Files:** `.github/workflows/ci.yml`

- Add `--ignore=tests/test_exasol.py` to the unit-test job's exclude list (after line 82,
  `--ignore=tests/test_clickhouse.py`).
- Add a `test-exasol` job modelled on `test-clickhouse` (line ~440):
  `uv sync --group test --no-dev --extra exasol`, start the container, poll until port 8563 accepts,
  then run `pytest tests/test_exasol.py`.

**Verify:** the unit-test command from `ci.yml:70-82` (now including the exasol ignore) collects and
passes locally:

```
uv run pytest tests/ -v --ignore=tests/test_sqlite.py --ignore=tests/test_mssql.py \
  --ignore=tests/test_postgresql.py --ignore=tests/test_mysql.py --ignore=tests/test_oracle.py \
  --ignore=tests/test_mariadb.py --ignore=tests/test_duckdb.py --ignore=tests/test_cockroachdb.py \
  --ignore=tests/test_turso.py --ignore=tests/test_firebird.py --ignore=tests/test_ssh.py \
  --ignore=tests/test_clickhouse.py --ignore=tests/test_exasol.py
```

---

## Step 15 — Docs: `CONTRIBUTING.md` + `README.md`

**Group:** — | **Depends on:** 7 | **State:** `todo`

**Files:** `CONTRIBUTING.md`, `README.md`

- `CONTRIBUTING.md` — add Exasol to the enterprise-profile list (line ~50) and an env-var table
  (`EXASOL_HOST` / `EXASOL_PORT` / `EXASOL_USER` / `EXASOL_PASSWORD` / `EXASOL_SCHEMA`).
- `README.md` — add Exasol to the database list (line 28) and a `pyexasol` row in the Driver
  Reference table (line ~286).

**Verify:** manual read-through; both tables list Exasol consistently with the neighbouring engines.

---

# Final verification (run once all steps are `done`)

1. `uv run pytest tests/connections/providers/exasol/ -v` -> new unit tests pass.
2. `uv run pytest tests/test_schema_capabilities.py -v` -> catalog/enum consistency holds.
3. The full step-14 unit-job command -> no regressions across the existing suite.
4. `uv run ruff check sqlit tests && uv run mypy sqlit` -> clean.
5. `uv run sqlit` -> Exasol appears in the connection picker; the auth dropdown shows/hides
   Password vs Access Token vs Refresh Token; the TLS tab is present.
6. Docker end-to-end:
   `docker compose -f infra/docker/docker-compose.test.yml --profile enterprise up -d exasol`,
   wait for readiness, then `uv run pytest tests/test_exasol.py -v`. Then connect interactively with
   `uv run sqlit` against `localhost:8563`, `sys`/`exasol`, TLS mode `require` — confirm schemas and
   tables list in the explorer, a `SELECT` returns rows, and an `INSERT` reports a row count.

---

# Risks / open items

- **`exasol/docker-db` in CI** (step 14): needs `--privileged` and at least 4 GB RAM, and boots in
  minutes rather than seconds. The job is isolated (`needs: build`, its own runner) so it will not
  slow the unit job, but expect the reviewer to question it. Fallback if pushed back on: keep the
  compose service and `tests/test_exasol.py` for local use and drop the CI job — mark step 14's job
  addition `skipped` and keep the `--ignore` line.
- **`ExaStatement` result detection** (step 4): `column_names()`-empty vs `stmt.result_type` — decide
  during step 4 against the installed pyexasol.
- **Patching the lazy driver import in unit tests** (step 10) — see the note in that step.
- **Context7 MCP was not connected when this plan was written**, so the pyexasol and Exasol
  system-table details above were verified against the published docs (`exasol.github.io/pyexasol`,
  `docs.exasol.com`) rather than through Context7. Re-check with Context7 if available.

---

# Session log

Append one line per session: date, steps touched, outcome, anything half-done.

| Date | Steps | Outcome / notes |
|---|---|---|
| 2026-08-27 | — | Plan restructured into 15 numbered steps with atomic groups `ACT` (5-7) and `INT` (13-14). No implementation yet. |
| 2026-08-27 | 1, 2, 3, 4 | All four `done`. **Step 4 open item resolved:** use `stmt.result_type` (plain attribute, values `resultSet` / `rowCount`) rather than empty `column_names()`, and test it **before** any fetch — `ExaStatement.__next__` raises `ExaRuntimeError` ("Attempt to fetch from statement without result set") and `fetchmany()` iterates, so reversing guard and fetch would turn every `INSERT` into an error. |
| 2026-08-27 | 3 | **Step 3 notation corrected:** `conn.meta.list_tables()` / `list_views()` / `list_columns()` return **already-fetched `list[dict]` with UPPERCASE keys**, not tuples — `execute_snapshot` hard-codes `fetch_dict=True`. Rows are read by key; positional indexing would raise `KeyError` at runtime and `mypy` would not catch it. `execute_snapshot` itself returns an `ExaStatement`, so it needs an explicit `.fetchall()`. Verified via Context7 + the pyexasol source (`meta.py`, `statement.py`, `formatter.py`). |
| 2026-08-27 | 1 | **Blocker found and fixed — the plan's isolation premise was wrong.** `catalog.py::_discover_providers` imports `<name>/provider.py` for **every** subpackage unconditionally (no existence check, no `except`), so an adapter-only package did not stay inert: it broke discovery app-wide (`get_supported_db_types()` raised `ModuleNotFoundError`; `test_schema_capabilities.py` went 9-passed -> 4-failed). Fixed by skipping subpackages whose `provider` module is absent, via `importlib.util.find_spec`, in `catalog.py`. **This adds a modified shared file the proposal did not anticipate** — carry it into the upstream PR as a small robustness fix. |
| 2026-08-27 | 2 | **Note on design D5:** pyexasol does **not** client-side reject `password` + `access_token`/`refresh_token`; `_login()` simply branches on token truthiness. The spec's "unused credentials absent, not present-and-empty" rule is still correct — and matters more than D5 implies, since a present-but-empty `access_token` is falsy and would silently fall back to password login. |
| 2026-08-27 | 3 | **Edge case left for step 11:** `default_schema` is `""`, so an unset `schema` passes an empty pattern to `list_columns` (pyexasol defaults to `"%"`), which matches nothing. Unreachable via the explorer — every Exasol table arrives from `get_tables()` as a populated `(TABLE_SCHEMA, TABLE_NAME)` pair — so left spec-faithful rather than adding a fallback. Worth a unit test. |
| 2026-08-27 | 5, 6, 7 | Group `ACT` complete — Exasol is registered and selectable. **Step 7 snippet corrected (design D6):** `DockerDetector.env_vars` is a **required** field with no default, so the plan's `DockerDetector(image_patterns=("exasol/docker-db",), default_user="sys")` would raise `TypeError` at import time *inside discovery*, breaking all 30 providers rather than just Exasol. Passed `env_vars={}` — semantically right too, since `exasol/docker-db` takes no credential env vars and `get_credentials({})` resolves to `default_user="sys"`. **Credential visibility (design D3):** `username`/`password` declared as explicit `SchemaField`s instead of reusing `_username_field()` / `_password_field()`, whose returned `SchemaField` is frozen with `visible_when=None` and so cannot be hidden under token auth. |
| 2026-08-27 | 5, 6, 7 | Gate green: `test_schema_capabilities.py` 9/9 at 30 providers; ruff 117 and mypy 430-in-44 both exactly at the pre-change baseline (3 `no-any-return` findings on the new visibility predicates fixed by wrapping the lookup in `str(...)`, matching `schema_helpers._tls_mode_is_custom`). The 21 wider-suite failures are pre-existing Windows-environment ones — confirmed identical with the change backed out. **Steps 9-11 (unit tests) are now unblocked:** step 9 (`test_schema.py`) depends only on 5 and 7 and can start immediately; steps 10 and 11 still need step 8 (the `exasol` extra) first. Step 4.9's interactive `uv run sqlit` check is the one item outstanding — verified headlessly instead through the same code paths (picker option after Teradata, port 8563, three auth methods, visibility swap, TLS tab). |
| 2026-08-27 | 8, 9, 10, 11 | All four `done` — 55 unit tests green, and green with `pyexasol` genuinely uninstalled (`uv sync --group test --no-dev`, zero skips), so the default CI job covers them. **Step 10's open item resolved (design D2):** the driver is faked with `patch.dict("sys.modules", {"pyexasol": MagicMock()})` — `importlib.import_module` returns an existing `sys.modules` entry without touching the filesystem, so `_import_driver_module` stays under test rather than being patched out. **`pyexasol` resolved: 2.3.2** — the exact version every API detail was verified against, so the loose `>=2.0.0` bound cost nothing here. **D6 escape hatch NOT needed:** `uv sync --extra exasol` resolved cleanly despite `pyexasol`'s `requires-python >=3.10,<3.15` against sqlit's unbounded `>=3.10` — but note D6 predicted the wrong mechanism: `uv` attached **no** `python_full_version < '3.15'` marker to the lock entry, only `extra == 'all'` / `extra == 'exasol'`. Resolution succeeds because no fork is required; the `<3.15` ceiling will surface at install time on 3.15+, not at lock time. **D4 confirmed inert:** the `pyexasol` mypy override changes nothing (mypy excludes `tests/`, `sqlit/` names the driver only in a string literal); `uv run python -c "import pyexasol"` is its real check, not a clean mypy run. **D5 lockfile drift to disclose in the PR:** `uv.lock` also drops the stale `mariadb` package entry (0 occurrences left), because `HEAD`'s `mariadb` extra already points at `PyMySQL`; not separable from a `uv lock` regenerate, not hand-edited. **No adapter bug surfaced (6.5) — and the tests are not vacuous:** nine mutations of `adapter.py` (inverted `result_type` guard, `rowcount` read as a property, index-based row reads, `fetchmany(max_rows)` instead of `+ 1`, PK lookup via `conn.execute`, token auth also sending `password`, `cert_reqs` dropped, `quote_identifier` escaping removed, `execute_test_query` via `cursor()`) were each caught by 1-6 failing tests; `adapter.py` restored byte-identical (sha256 verified). Gate: ruff 268-on-`sqlit tests` and mypy 430-in-44 both exactly at the pre-change baseline with the new files themselves clean; CI's unit command verbatim gave **21 failed, 1703 passed, 395 skipped** — the same 21 pre-existing Windows-environment failures, none Exasol — and collected all 55 new tests (22 adapter + 24 connect + 9 schema) with no `--ignore` entry. `--markers` lists `exasol`; `-m exasol` selects zero, as D7 intended. **Steps 12-15 (Docker integration, CI job, docs) remain.** |
| 2026-08-27 | 12, 13, 14 | Group `INT` complete — Exasol now runs the shared suite against a live server: **20 passed, 8 skipped, 0 failed** (`uv run pytest tests/test_exasol.py`, container up), and **3 passed / 25 skipped / 0 errors** with the container stopped, so a Docker-less laptop stays green. **O3 resolved:** `sys` / `exasol` confirmed by a real login; the image *does* accept a password override, but only as a `docker run` argument (`exadt init-sc --sys-passwd`), **never an environment variable** — which independently confirms the `env_vars={}` behind D9. **Boot measured (2.4):** port 8563 opened at **21s**, first successful login at **101s** — an 80-second window in which `is_port_open` is true and every login fails, exactly the false positive design D2 exists to kill. CI poll kept at 60 × 10s (10 min) per D7: generous headroom over 101s for a cold runner that must also pull ~4 GB. **D8 deviation from step 13's wording:** subclassed `BaseDatabaseTestsWithLimit`, not `BaseDatabaseTests` — Exasol supports `LIMIT`, and `test_query_limit` passes, so it was free coverage. **Two base tests overridden:** `test_docker_container_connection` skips unconditionally (D9 — no credentials through env vars, and a discovery-built config carries no `tls_mode`, so it would verify TLS against the image's self-signed certificate); `test_primary_key_detection` is re-issued through the app's call shape (D10). `test_docker_container_detection` was **not** overridden and passes. **O1 confirmed against the live server, and it is worse than `findings.md` predicted — the two causes are independently fatal:** `get_columns(conn, 'test_users')` → 0 columns; `('TEST_USERS', no schema)` → **0**; `('test_users', schema=…)` → **0**; only the app's `('TEST_USERS', schema=…)` → 3 columns with `ID` correctly flagged and nothing else. `conn.meta.list_columns('%', 'TEST_USERS')` → 3, so O1's proposed `'%'` default *does* fix the no-schema case — but only when the table name is already in server casing. Earmarked for the follow-up change; **no file under `sqlit/` touched**. **New finding, not anticipated by the design — Exasol folds `''` to NULL:** the task's literal view body `WHERE email != ''` matches **0 rows** on a live server (verified: with an empty-string row inserted, `email IS NULL` → 1 and `email != ''` → 0), so `test_user_emails` would have returned nothing and failed `test_query_view`. The fixture uses `WHERE email IS NOT NULL` instead. **Constraint 2 demonstrated by accident:** while taking the pre-change baseline the fixture module was moved aside with `tests/test_exasol.py` still present and un-ignored, and the driver-free unit run went to **42 failed / 2 errors** — all 23 of them in `test_exasol.py`. That is precisely the breakage the `INT` atomicity rule exists to prevent. **Gate:** the unit command with the new `--ignore` gives **21 failed, 1703 passed, 395 skipped, 0 errors** — the failure set is identical to the pre-change baseline once `test_exasol.py` is netted out, and identical to the step 8-11 session's numbers; `ruff check tests` is 152 exactly at baseline with both new files clean; collection succeeds with `pyexasol` genuinely uninstalled (`uv sync --group test --no-dev`). **Local environment note:** an unrelated `exasoldb` container (`exasol/docker-db:latest`, port 9563) runs on this machine and is what satisfies the two Docker-discovery tests locally; on a Docker-less machine both skip. **Steps 8-11's per-step `**State:**` prose lines are still stale at `todo`** (the Status table is the source of truth); left as found. **Step 15 (docs) remains.** |
| 2026-08-27 | 15 | Step 15 `done` — the docs land as **four insertions across two files, zero lines reflowed**. `README.md`: `Exasol` after `Teradata` in the supported-database sentence (D1 — `config.py:55-56` independently confirms `EXASOL` follows `TERADATA` in the picker display order), plus one Driver Reference row between `Spanner` and `Apache Arrow Flight SQL` (D2). **D6's reflow risk did not materialise:** the new row is 176 characters, identical in width to the Spanner row, because all four Exasol cells are shorter than the `snowflake-connector-python` cells that set the column widths. `CONTRIBUTING.md`: `Exasol` appended to the enterprise-container list at line 49, and an `**Exasol:**` env-var table plus readiness note placed **after the Oracle 11g table, before Flight SQL** — grouped with the enterprise cluster so the table order matches the container list this change just edited. **D3 verified mechanically, not by eye:** a script re-derived the six `os.environ.get` fallbacks from `tests/fixtures/exasol.py` and compared them against the table it had just written — set equality and character-identical defaults (`localhost` / `8563` / `sys` / `exasol` / `TEST_SQLIT` / `300`). **One deviation from this change's own task 4.1:** `git diff --stat` names **nine** files, not two, because steps 1-14 are still uncommitted in this tree; the checkable condition — that this change added exactly `README.md` and `CONTRIBUTING.md` to the pre-existing modified set — holds. **Style fix caught in review:** the readiness note's em dash became a semicolon once `grep` showed the em-dash count in both files was 1, i.e. only the one just added; both files are pure ASCII, as found. **Claims traced to runtime rather than to this plan:** `get_provider(DatabaseType.EXASOL)` returns a live provider whose `DriverDescriptor(package_name='pyexasol', extra_name='exasol')` is exactly what the README row promises, and the note's port-open-versus-login claim restates the fixture's own comment (`exasol.py:21-22`) and its retry-to-deadline loop. Nothing added mentions introspection, so **O1 stays undocumented and unimplied**. **Gate:** pre-commit `trailing-whitespace` and `end-of-file-fixer` pass on both files and modified neither; there is no markdown linter in this repo, so that is the whole automated gate (D7). **Plan complete: 15 / 15.** Follow-up O1 (`get_columns` casing/schema) and the plan's Final verification block remain out of scope by design. |
