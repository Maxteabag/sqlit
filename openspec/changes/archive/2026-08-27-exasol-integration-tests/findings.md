# Pre-implementation findings

Three things surfaced while reading the code to plan this change that `plan.md` steps 12-14 did not
anticipate. All three are *predictions* made by reading source, not observed test failures — no
Exasol container has been started yet. Each is handled by a decision in `design.md`; this file is the
evidence behind those decisions.

Verified against the working tree at the time of writing: `pyexasol` 2.3.2 installed in `.venv`,
`ExasolAdapter` as committed by the `exasol-adapter` change.

---

## 1. `test_primary_key_detection` will fail against a live server

The inherited test from `BaseDatabaseTests` calls `get_columns` in a shape the application never
uses, and Exasol's metadata views will return nothing for it.

**Evidence**

- `tests/test_database_base.py:361-397` — the base test calls
  `session.adapter.get_columns(session.connection, "test_users", database=...)`: lowercase table
  name, **no schema argument**. It then asserts `len(columns) >= 3`.
- `sqlit/domains/connections/providers/exasol/adapter.py:161-183` — `get_columns` does
  `schema = schema or ""` and passes that as the first positional argument to
  `conn.meta.list_columns(schema, table)`.
- `.venv/Lib/site-packages/pyexasol/meta.py:276-306` — that first parameter is
  `column_schema_pattern`, whose **default is `'%'`**, and it lands in the query as
  `WHERE column_schema LIKE {column_schema_pattern}`. `LIKE ''` matches nothing. Passing `""` is
  strictly narrower than passing nothing.
- `.venv/Lib/site-packages/pyexasol/meta.py:303-304` — the docstring states plainly:
  *"Patterns are case-sensitive."* `EXA_ALL_COLUMNS` stores the folded, uppercase `TEST_USERS`, so
  `column_table_pattern="test_users"` matches nothing either.
- The primary-key lookup in the same method has the same problem with exact equality:
  `WHERE ... CONSTRAINT_SCHEMA = {schema!s} AND CONSTRAINT_TABLE = {table!s}`.

So there are two independent reasons the call returns `[]`: the empty schema pattern and the
identifier casing. Fixing only one of them still yields zero columns.

**Why the application is unaffected**

Both real callers pass an explicit schema and a name that came from the server:

- `sqlit/domains/explorer/app/schema_service.py:86` — `inspector.get_columns(conn, name, db_arg, schema)`
- `sqlit/domains/process_worker/app/process_worker.py:333` — same shape

`name` and `schema` originate in `get_tables()`, which reads `TABLE_SCHEMA` / `TABLE_NAME` from
`EXA_ALL_TABLES` — already uppercase. The failure is confined to the base suite's call shape.

**How this change handles it**

`design.md` **D10**: `TestExasolIntegration` overrides `test_primary_key_detection` to call
`get_columns` with `schema=TEST_SQLIT` and the uppercase table name — the app's shape — while still
asserting the full contract (`ID` flagged primary key, nothing else flagged). Task 5.4.

`design.md` **O1** records the underlying weakness as a follow-up: for a provider that declares
`supports_multiple_databases=False`, defaulting the schema pattern to `""` rather than `"%"` means
"no schema given" silently returns nothing instead of searching everywhere. That fix touches
`sqlit/` and wants its own unit test, which this change's Non-Goals exclude.

**Note on the mocked suite.** `tests/connections/providers/exasol/test_adapter.py` asserts that
`schema=None` passes `""` to `list_columns` — it pins the current behaviour deliberately (recorded as
D8 of the `exasol-unit-tests` change). A `MagicMock` returns rows for any argument, so no mocked test
can distinguish `""` from `"%"`. This is the change's premise in miniature.

---

## 2. `test_docker_container_connection` will fail while the container is running

`DockerDiscoveryTests` builds a `ConnectionConfig` from the detected container and opens a real
connection with it. For Exasol that configuration cannot work — for two reasons, neither of which is
a bug in the adapter and neither of which is fixable from `tests/`.

**Evidence**

- `tests/test_database_docker.py:108-176` — the test skips only when Docker is unavailable, no
  container matches, or the container is not connectable. With the container up it proceeds to
  `adapter.connect(config)` and `adapter.execute_query(conn, "SELECT 1")`.
- `sqlit/domains/connections/providers/exasol/provider.py` — `SPEC.docker_detector` is
  `DockerDetector(image_patterns=("exasol/docker-db",), env_vars={}, default_user="sys")`. The empty
  `env_vars` is correct: `exasol/docker-db` publishes no credential through an environment variable.
- `sqlit/domains/connections/discovery/docker_detector.py:384-419` —
  `container_to_connection_config` sets `password=container.password`, which is `None` when no env
  var supplied one.
- `sqlit/domains/connections/providers/exasol/adapter.py:139` — the password branch passes
  `endpoint.password` straight through to `pyexasol.connect`.
- The discovery-built config carries no `tls_mode` option, so `_tls_args` takes the default path:
  `encryption=True` with **no** `websocket_sslopt`, leaving websocket-client's certificate
  verification enabled — against the self-signed certificate `docker-db` presents. The handshake
  fails before authentication is even reached.

**How this change handles it**

`design.md` **D9**: override that one method with an unconditional `pytest.skip` whose message states
both reasons. Task 5.3.

The other two `DockerDiscoveryTests` methods are deliberately **not** overridden:

- `test_docker_container_detection` (`tests/test_database_docker.py:11-53`) only asserts that a
  matching, connectable container has a detected port — that passes.
- `test_docker_container_no_password_prompt_when_not_needed` asserts only for providers where
  `requires_auth(db_type)` is false. `SPEC.requires_auth` is `True`, so it is a no-op.

---

## 3. `is_port_open` is not a readiness check for Exasol

The fixture pattern this change copies is not safe for this image.

**Evidence**

- `tests/fixtures/clickhouse.py:26-33` — `clickhouse_server_ready` returns `is_port_open(...)`
  followed by `time.sleep(2)`. That is adequate for a container that is serving within seconds.
- `exasol/docker-db` binds 8563 during startup and refuses logins for minutes afterwards. A bare
  port check therefore reports "ready" during a window where every connection attempt fails, turning
  a normal slow boot into a hard authentication error instead of a wait.

**How this change handles it**

`design.md` **D2**: `exasol_server_ready` keeps `is_port_open` as the cheap "is anything there at
all" gate — an immediate `False`, and therefore a skip, when nothing is listening — then retries a
real `pyexasol.connect` with a sleep until a deadline. Absent container → skip; still booting →
wait; present but broken → skip with the driver's error in the message. Task 3.3.

The same distinction drives the CI poll in **D7**: 60 attempts × 10 s on the port, with the
fixture's connect-retry absorbing the remaining gap between "port open" and "accepts logins"
(tasks 6.3, 2.4).

---

## Smaller observations

These did not change the shape of the work but are worth having written down.

- **Quoted lowercase seed DDL would break the whole suite.** The shared tests issue
  `SELECT * FROM test_users` unquoted, which Exasol folds to `TEST_USERS`. Seeding
  `CREATE TABLE "test_users"` would create an object those queries can never find. The seed DDL
  must stay unquoted so both sides fold identically — `design.md` **D3**, task 3.5.
- **The `exasol` pytest marker stays unused, and that is consistent.** `pyproject.toml:201`
  registers it, but **no test file in this repo uses any per-database marker** — `clickhouse`,
  `oracle` and `mssql` are all registered and unused; `ci.yml` and the plan's verify commands select
  by filename. Marking Exasol alone would be an inconsistency, not an improvement —
  `design.md` **D6**.
- **`BaseDatabaseTestsWithLimit` exists and is a free superset.** `tests/test_database_base.py:783`
  adds `test_query_limit` on top of `BaseDatabaseTests`. Exasol supports `LIMIT`, so the subclass
  costs nothing. `plan.md` step 13 names `BaseDatabaseTests`, written before the split was checked —
  `design.md` **D8**.
- **Six inherited tests will skip on adapter capability flags.** `supports_indexes`,
  `supports_triggers` and `supports_sequences` are all `False`
  (`adapter.py:66-80`), which self-skips `test_get_indexes`, `test_get_triggers`,
  `test_get_sequences` and the three `*_definition` tests. The fixture therefore seeds no index,
  trigger or sequence — seeding objects that exist only to be ignored would mislead a reader.
  Task 5.8 verifies that every skip in the run has a cause on this list.
- **`test_timezone_aware_datetime` will skip.** `DatabaseTestConfig.timezone_datetime_type` stays
  `None`. Exasol has `TIMESTAMP WITH LOCAL TIME ZONE`, but the base test body branches per database
  (`tests/test_database_base.py:687-729`), so enabling it means editing shared test code — excluded
  by Non-Goals. Recorded as `design.md` **O2**.
- **The unit job's exclusion list is filename-based** (`ci.yml:70-82`), which is why tasks 5.1 and
  6.1 must land in the same commit. This one *was* in the plan, as the rationale for the `INT` atomic
  group; repeated here because it is the single most likely way to leave the branch red.

---

## Finding → decision → task

| Finding | Decision | Task | Follow-up |
|---|---|---|---|
| `get_columns` empty schema pattern + case-sensitive matching | D10 | 5.4 | O1 — separate change, touches `sqlit/` |
| Docker discovery cannot build a working Exasol config | D9 | 5.3 | none — property of the image |
| Open port is not readiness | D2, D7 | 3.3, 6.3 | none |
| Uppercase folding in seed DDL | D3 | 3.5 | none |
| Per-database markers unused repo-wide | D6 | 5.1 | none |
| `WithLimit` base class available | D8 | 5.1 | none |
| Timezone test not applicable without shared-code edits | O2 | 5.2 | deferred |

Anything the live container contradicts during implementation goes in `plan.md`'s Session log
(task 5.10) — not into a `sqlit/` edit inside this change.
