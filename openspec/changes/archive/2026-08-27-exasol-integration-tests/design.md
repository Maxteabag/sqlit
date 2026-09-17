## Context

`ExasolAdapter` is registered, selectable and unit-tested — but only against `MagicMock`. The three
mocked test files pin the adapter's *intent*; nothing has checked that pyexasol agrees. Reading the
installed `pyexasol` 2.3.2 source while planning this change already surfaced one concrete
disagreement (design D10), which is the clearest possible argument for the change.

Four constraints shape it:

1. **The unit CI job installs no extras and imports `tests/conftest.py`.** `ci.yml:66` is
   `uv sync --group test --no-dev`. `conftest.py` star-imports every fixture module, so
   `tests/fixtures/exasol.py` must import with `pyexasol` absent. Driver imports go inside the
   fixture bodies, guarded by `pytest.skip` on `ImportError` — the pattern
   `tests/fixtures/clickhouse.py` uses for `clickhouse_connect`.
2. **The unit job's exclusion list is filename-based.** Adding `tests/test_exasol.py` without adding
   `--ignore=tests/test_exasol.py` makes the driver-free job collect a container test. Steps 13 and
   14 are therefore one commit.
3. **Exasol folds unquoted identifiers to uppercase, and `pyexasol.meta.*` filters are
   case-sensitive LIKE patterns.** This drives the seeding decision (D3) and the one adapter
   disagreement (D10).
4. **`exasol/docker-db` is a privileged multi-gigabyte image with a multi-minute cold boot and no
   shipped readiness probe.** It cannot be treated like the `postgres:16-alpine` of the default
   profile — hence the `enterprise` profile and the connect-based readiness gate (D1, D2).

## Goals / Non-Goals

**Goals:**

- One documented command brings up a local Exasol that `tests/test_exasol.py` runs against.
- The shared `BaseDatabaseTestsWithLimit` suite passes against a real Exasol 8 server, exercising
  the adapter's introspection, query execution, streaming output and TLS paths end to end.
- Every Exasol fixture **skips** — never errors — when the container or the driver is absent, so
  `uv run pytest tests/` stays green on a laptop with no Docker.
- A dedicated `test-exasol` CI job, shaped like every other integration job in `ci.yml`.
- Where the live server contradicts the adapter, the contradiction is **recorded**, not papered
  over silently.

**Non-Goals:**

- No change to any file under `sqlit/`. Findings from this change become a follow-up (D10, O1).
- No new capability in the shared test base. Where Exasol needs different behaviour, it overrides in
  its own subclass rather than adding an Exasol branch to `tests/test_database_base.py`.
- No SSH-tunnel, OpenID-token or multi-node coverage. `docker-db` authenticates with a password;
  the token branches stay unit-tested only.
- No documentation. That is plan.md step 15.

## Decisions

### D1 — Compose service goes under the `enterprise` profile, with no healthcheck

`exasol/docker-db:latest-8` needs `privileged: true` (it manages its own storage volumes and kernel
parameters) and a `stop_grace_period: 120s` (an abrupt kill leaves the data volume dirty and the
next boot slower). At several gigabytes it belongs with `db2` / `oracle11g` / `trino` in the opt-in
profile, not in the set that a plain `docker compose up` pulls.

No `healthcheck:` block. The image ships no lightweight probe, and the two other enterprise
databases (`db2`, `oracle11g`) declare none either — readiness is the fixture's job (D2).
*Alternative considered:* a `nc -z localhost 8563` healthcheck, like `firebird`. Rejected: it is the
same false positive that D2 exists to avoid, and would put a misleading `healthy` in
`docker compose ps`.

### D2 — Readiness is a real connect with a deadline, not `is_port_open`

Exasol binds 8563 well before it will accept a login. `tests/fixtures/clickhouse.py` gets away with
`is_port_open` plus `time.sleep(2)`; for Exasol that turns a normal slow boot into a hard
authentication failure. So `exasol_server_ready` keeps `is_port_open` as the cheap "is anything
there at all" gate — an immediate `False` (skip) when nothing is listening — and then retries
`pyexasol.connect(...)` with a short sleep until a deadline, returning `False` only if the deadline
passes. Absent container → skip; present-but-still-booting container → wait; present-and-broken →
skip with the driver error in the message. `pyexasol` is imported inside this fixture, never at
module level (constraint 1).

### D3 — Seed with unquoted identifiers

The shared suite issues `SELECT * FROM test_users`. Unquoted, Exasol folds that to `TEST_USERS`, so
the DDL must also be unquoted (`CREATE TABLE test_users (...)` → `TEST_USERS`) and the two agree.
*Rejected alternative:* quoted lowercase DDL (`CREATE TABLE "test_users"`), which would create an
object the suite's own unquoted queries can never find.

Column names come back uppercase. The base suite already tolerates that everywhere it matters
(`data[0].get("name") or data[0].get("NAME")`, `"id,name" in result.stdout.lower()`), so no
override is needed for the query tests.

Seed exactly what the suite consumes: `test_users` (`id` PRIMARY KEY, `name`, `email`, three rows —
Alice / Bob / Charlie), `test_products`, and the view `test_user_emails`. **No** index, trigger or
sequence: `ExasolAdapter` reports `supports_indexes` / `supports_triggers` / `supports_sequences`
as `False`, so those six base tests self-skip, and seeding objects that exist only to be ignored
would be misleading.

### D4 — The connection fixture passes `--tls-mode require`

`docker-db` presents a self-signed certificate. `require` maps to `encryption=True` plus
`websocket_sslopt={"cert_reqs": ssl.CERT_NONE}`; the `default` mode also encrypts but leaves
websocket-client's verification on, which fails the handshake. This is not a workaround —
`--tls-mode require` makes the integration suite the first thing to exercise the `tls_mode` →
`websocket_sslopt` mapping against a real TLS negotiation. *Rejected alternative:* extract the
container's certificate and use `verify-ca`; more moving parts, no additional adapter coverage.

### D5 — `exasol_db` is function-scoped and recreates the schema per test

`test_query_insert` adds a fourth row to `test_users`; `test_query_select` asserts
`3 row(s) returned`. A session-scoped seed makes that pair order-dependent. So `exasol_db` does
`DROP SCHEMA TEST_SQLIT CASCADE` / `CREATE SCHEMA` / seed on every test, matching
`tests/fixtures/clickhouse.py`'s function scope. Only `exasol_server_ready` — the expensive part —
is session-scoped.

### D6 — No `@pytest.mark.exasol` on the new test file

`exasol-driver-packaging` registered the marker, but **no test file in this repo uses any of the
per-database markers** — `clickhouse`, `oracle`, `mssql` are all registered and unused, and both
`ci.yml` and the plan's verify commands select by filename. Marking Exasol alone would be an
inconsistency dressed as an improvement. The marker stays registered and inert.

### D7 — The CI job mirrors `test-clickhouse`, with a longer boot poll

Shape copied from `ci.yml:440`: `needs: build`, Python 3.12, `uv sync --group test --no-dev --extra
exasol`, a bare `docker run -d` (no CI job in this repo uses compose), a poll loop, then
`pytest tests/test_exasol.py`. Three deviations, all boot-time driven:

- `docker run --privileged -p 8563:8563` — required by the image.
- Poll `60 × 10s` (10 minutes) instead of ClickHouse's `30 × 2s`. The fixture's own connect-retry
  (D2) absorbs the remaining gap between "port open" and "accepts logins".
- `--timeout=300` rather than the ClickHouse job's `120`, because the first query against a cold
  Exasol is slow.

Gated exactly like every other integration job — on push and PR. Per the decision recorded with the
user: `workflow_dispatch`-gating would diverge from `ci.yml`'s convention on the PR being
upstreamed, and `continue-on-error` would hide regressions.

### D8 — `BaseDatabaseTestsWithLimit`, not `BaseDatabaseTests`

Exasol supports `LIMIT`. `BaseDatabaseTestsWithLimit` is a strict superset that adds
`test_query_limit`. plan.md step 13 says `BaseDatabaseTests`, written before the base-class split
was checked; taking the superset is free coverage.

### D9 — `test_docker_container_connection` is overridden with a documented skip

`DockerDiscoveryTests.test_docker_container_connection` builds a `ConnectionConfig` from the detected
container and connects with it. For Exasol that config cannot work, for two independent reasons:

- `SPEC.docker_detector` declares `env_vars={}` because `exasol/docker-db` exposes its credentials
  through no environment variable, so `container.password` is `None`.
- A discovery-built config carries no `tls_mode`, so the adapter negotiates verified TLS against a
  self-signed certificate.

Both are true properties of the image, not bugs in the adapter, and neither is fixable from
`tests/`. The subclass therefore overrides that one method with an unconditional `pytest.skip` whose
message states both reasons. `test_docker_container_detection` and
`test_docker_container_no_password_prompt_when_not_needed` are **not** overridden — the first passes
(the container is detected and its port mapped), and the second is a no-op for a `requires_auth`
provider.

### D10 — `test_primary_key_detection` is overridden to call `get_columns` the way the app does

The base version calls `get_columns(conn, "test_users", database=None)` — lowercase name, no schema.
Against a live server that returns zero columns, twice over:

- `ExasolAdapter.get_columns` does `schema = schema or ""` and passes it as pyexasol's
  `column_schema_pattern`. In `pyexasol/meta.py` that becomes `WHERE column_schema LIKE ''`, which
  matches nothing. pyexasol's own pattern default is `'%'`, not `''`.
- pyexasol's meta patterns are case-sensitive, and `EXA_ALL_COLUMNS` stores `TEST_USERS`. The
  primary-key snapshot query has the same problem with `CONSTRAINT_TABLE = 'test_users'`.

The app never makes that call: `schema_service.py:86` and `process_worker.py:333` both pass the name
and schema straight through from `get_tables()`, which returns them uppercase. So the override passes
`schema=TEST_SQLIT` and the uppercase table name, and still asserts the whole contract — `id` is
flagged primary key, nothing else is. The `LIKE ''` weakness is recorded as a finding for a follow-up
change (O1); patching `sqlit/` is out of scope here.

## Risks / Trade-offs

- **[Cold boot exceeds the CI poll]** → 10-minute poll plus the fixture's connect-retry. If the
  image regresses past that, the job fails loudly with the poll's own log lines rather than an
  opaque authentication error.
- **[GitHub runner resources]** `docker-db` wants several GB of RAM and roughly 10 GB of disk; a
  standard `ubuntu-latest` runner has both, with little headroom. → If the job proves flaky on
  resources, the fallback is a pre-run `docker image prune -af`, recorded before reaching for
  `continue-on-error`.
- **[Default credentials assumed]** The fixture defaults to `sys` / `exasol`. → Both the compose
  service and the CI job read `EXASOL_USER` / `EXASOL_PASSWORD`, and a task verifies the defaults
  against a running container before the suite is trusted.
- **[Two overridden base tests could mask a regression]** → Each is narrow, carries a comment naming
  the reason, and D10's override still asserts the full primary-key contract. Neither weakens what
  the other twenty-odd inherited tests check.
- **[`latest-8` is a floating tag]** A new Exasol 8 patch can change behaviour with no repo change.
  → Accepted, matching the repo's convention (`clickhouse-server:latest`, `surrealdb:latest`;
  `firebird` is the sole pinned exception).
- **[Per-test schema recreation]** D5 pays a `DROP` / `CREATE` / seed cycle roughly twenty times.
  → Exasol schema DDL is fast next to the container boot this job already pays for; correctness wins.

## Open Questions

- **O1 — Should `get_columns`'s schema default be `"%"` instead of `""`?** For a schema-only
  provider, "no schema given" plausibly means "search everywhere", which is what pyexasol's own
  default expresses. **Recommendation:** yes, but in a separate change — this one adds no `sqlit/`
  edits, and the fix wants its own unit test alongside the existing mocked assertion that currently
  pins `""`.
- **O2 — `timezone_datetime_type` stays `None`,** so `test_timezone_aware_datetime` skips. Exasol has
  `TIMESTAMP WITH LOCAL TIME ZONE`, but enabling the test needs an Exasol branch inside
  `tests/test_database_base.py`, which Non-Goals excludes. Left as a known gap.
- **O3 — Confirm `exasol/docker-db:latest-8`'s default SYS credentials and whether the image accepts
  a password override,** before treating the `EXASOL_PASSWORD` default as documented behaviour.
