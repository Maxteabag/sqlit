## Context

sqlit auto-discovers providers: `providers/catalog.py::_discover_providers` walks every
subpackage of `sqlit/domains/connections/providers/` and imports `<name>/provider.py`.

**Correction (found in implementation, see D8):** that import was unconditional, so a
subpackage *without* `provider.py` broke discovery entirely instead of being ignored.

The moment `provider.py` exists, the provider is live — and `tests/test_schema_capabilities.py`
asserts `{t.value for t in DatabaseType} == set(get_supported_db_types())` as an **exact set
equality**. That makes registration an all-or-nothing step involving three files at once
(`schema.py`, the `DatabaseType` enum, `provider.py`).

This change deliberately sits *below* that line. It adds only the adapter, which nothing
imports until registration lands, so the repo cannot enter a state where Exasol is selectable
but broken. It corresponds to plan.md steps 1-4.

Exasol's driver, `pyexasol`, is not DB-API 2.0 — it is a WebSocket client with no `.cursor()`.
That single fact drives most of the decisions below.

**Constraint: `pyexasol` is not installed.** The `exasol` extra is plan.md step 8, a separate
change. Everything here was therefore verified against the published pyexasol source and the
Exasol system-table documentation rather than a live interpreter. The gate for this change is
static only: `uv run ruff check sqlit && uv run mypy sqlit`.

**Reference implementations read for house style:** `providers/hana/adapter.py` (single
database, many schemas, `get_databases()` returning empty, doubled-double-quote quoting) and
`providers/clickhouse/adapter.py` (a `DatabaseAdapter` subclass that hand-rolls
`execute_query` and consumes the shared `providers/tls.py` helpers).

## Goals / Non-Goals

**Goals:**

- A complete, concrete `ExasolAdapter` — every abstract member of `DatabaseAdapter`
  implemented, so `mypy` accepts instantiation.
- Correct mapping of Exasol's three auth methods and sqlit's five `tls_mode` values onto
  pyexasol's kwargs.
- Introspection that cannot deadlock against metadata locks.
- Query execution that reports truncation and survives statements with no result set.
- Zero change in behaviour for every existing provider and test.

**Non-Goals:**

- Registering the provider (`provider.py`, `schema.py`, `DatabaseType.EXASOL`) — plan.md
  steps 5-7, the atomic `ACT` group.
- Declaring the `exasol` extra, the mypy override, or the pytest marker — plan.md step 8.
- Any test file. Behaviour is covered by plan.md steps 9-11; this change is statically gated.
- Docker/integration plumbing and docs — plan.md steps 12-15.

## Decisions

### D1 — Subclass `DatabaseAdapter`, not `CursorBasedAdapter`

`CursorBasedAdapter` implements `execute_query`/`execute_non_query` in terms of
`conn.cursor()`. pyexasol has no `cursor()`; it returns an `ExaStatement` from
`conn.execute()`. Inheriting the cursor base would mean overriding both methods anyway plus
inheriting a misleading contract.

*Alternative considered:* write a thin DB-API shim over pyexasol so `CursorBasedAdapter` could
be reused. Rejected — an adapter layer over an adapter layer, to save two short methods, and
it would hide the truncation and result-type handling that D3 needs to be explicit about.
`ClickHouseAdapter` sets the precedent for subclassing `DatabaseAdapter` directly.

### D2 — Introspect through `conn.meta.*`, and read rows **by key**

pyexasol's `ExaMetaData` prefixes every query with Exasol's snapshot-execution hint, so
metadata reads cannot be blocked by metadata locks. This is the driver-recommended path and
strictly better than hand-rolled `SELECT`s against `SYS.*`.

**This corrects plan.md step 3.** The plan's notation — `conn.meta.list_tables()` yielding
`(TABLE_SCHEMA, TABLE_NAME)` — reads as tuple indexing. It is not. pyexasol's
`execute_snapshot` hard-codes `options = {"fetch_dict": True}`, with the explicit rationale
*"fetch_dict=True is enforced to prevent users from relying on order of columns"*. So:

| Call | Returns |
|---|---|
| `conn.meta.list_tables(schema_pat, name_pat)` | `list[dict]` — already `.fetchall()`-ed |
| `conn.meta.list_views(schema_pat, name_pat)` | `list[dict]` — already `.fetchall()`-ed |
| `conn.meta.list_columns(schema_pat, table_pat, ...)` | `list[dict]` — already `.fetchall()`-ed |
| `conn.meta.execute_snapshot(query, params)` | an `ExaStatement` — needs an explicit `.fetchall()` |

Note the asymmetry in that last row: the three `list_*` helpers materialise their rows, while
`execute_snapshot` does not. Indexing a row positionally would raise `KeyError` at runtime and
would not be caught by `mypy`, so this is the highest-value correction in this document.

Keys are UPPERCASE, since Exasol upper-cases unquoted identifiers and the `list_*` helpers all
issue `SELECT *`. Column names used, all verified against docs.exasol.com:

- `EXA_ALL_TABLES` → `TABLE_SCHEMA`, `TABLE_NAME`
- `EXA_ALL_VIEWS` → `VIEW_SCHEMA`, `VIEW_NAME`
- `EXA_ALL_COLUMNS` → `COLUMN_NAME`, `COLUMN_TYPE`, `COLUMN_ORDINAL_POSITION`
- `EXA_ALL_CONSTRAINT_COLUMNS` → `CONSTRAINT_SCHEMA`, `CONSTRAINT_TABLE`, `CONSTRAINT_TYPE`,
  `COLUMN_NAME`; `CONSTRAINT_TYPE` is the literal string `PRIMARY KEY`
- `EXA_ALL_SCRIPTS` → `SCRIPT_SCHEMA`, `SCRIPT_NAME`, `SCRIPT_TYPE`

### D3 — Discriminate result sets on `stmt.result_type`, and check it *before* fetching

**This resolves plan.md's open item for step 4** (`column_names()`-empty vs
`stmt.result_type`). Verified against `pyexasol/statement.py`:

- `result_type` is a plain public attribute, assigned `self.result_type = res["resultType"]`,
  with exactly two values: `"resultSet"` and `"rowCount"`.
- `column_names()` is a method returning `self.col_names`, which stays `[]` for a `rowCount`
  statement.
- `rowcount()` is a **method**, not a property, returning `num_rows_total` for a result set and
  `row_count` otherwise.

Both discriminators work, but `result_type` is chosen: it is the driver's own explicit signal,
whereas an empty `column_names()` is a side effect of that signal. `result_type` also states
the intent in one readable comparison.

The ordering matters more than the choice. `ExaStatement.__next__` raises:

```python
if self.result_type != "resultSet":
    raise ExaRuntimeError(
        self.connection, "Attempt to fetch from statement without result set"
    )
```

`fetchmany()` iterates, so it inherits that raise. The guard must therefore come **before** any
fetch. The plan's snippet happens to satisfy this by returning early, but the reason was not
recorded — it is now, because reordering those two blocks during a later refactor would turn
every `INSERT` into an `ExaRuntimeError`.

Truncation uses the house pattern from `CursorBasedAdapter.execute_query`: fetch `max_rows + 1`,
compare, trim.

### D4 — Default port via `get_default_port("exasol")`, matching every other adapter

Every TCP adapter in the repo writes `int(endpoint.port or get_default_port("<db_type>"))` —
hana, db2, mysql, oracle, postgresql, presto, impala, cockroachdb, mariadb, surrealdb. This
adapter follows suit for consistency in an upstream PR.

**Known wrinkle, accepted:** `metadata.py::get_default_port` returns `provider.metadata.default_port`
if the provider resolves and otherwise falls back to `"1433"` (MSSQL). Until plan.md step 7
registers `SPEC` with `default_port="8563"`, an Exasol config with a blank port would resolve to
1433. This is inert in practice — `DatabaseType.EXASOL` does not exist yet, so no Exasol config
can be constructed — and it becomes correct the moment step 7 lands.

*Alternative considered:* a module-level `DEFAULT_PORT = "8563"` in `adapter.py`, correct at
every point in time. Rejected: it deviates from a ten-adapter-strong convention and duplicates
a literal that `SPEC` must declare anyway, to fix a hazard that is unreachable.

### D5 — Auth kwargs are added, never blanked

pyexasol rejects `password` combined with `access_token` or `refresh_token`. So the three
branches must *add* their own key rather than set all three with empty defaults. Passing
`access_token=None` alongside a password is a connection failure, not a no-op — hence the
spec's insistence that the unused keys be *absent*, and the unit test in plan.md step 10 that
asserts absence rather than emptiness.

### D6 — `extra_options` applied last

`connect_args.update(config.extra_options)` goes after the TLS kwargs, so a user can override
`encryption` or `websocket_sslopt` wholesale for an installation this mapping does not
anticipate. Matches `hana/adapter.py` and `clickhouse/adapter.py`.

### D8 — Make provider discovery tolerant of a subpackage with no `provider.py`

The premise of splitting steps 1-4 from the `ACT` group is that an adapter-only package is
inert. It was not: `_discover_providers` called
`import_module(f"{__package__}.{name}.provider")` for every subpackage with no existence check
and no `except`, so adding `providers/exasol/` without `provider.py` raised
`ModuleNotFoundError` and took down discovery for all 29 other providers -
`get_supported_db_types()` raised, and `tests/test_schema_capabilities.py` went from 9 passed
to 4 failed.

Fixed by skipping the subpackage when `importlib.util.find_spec(...)` finds no `provider`
module. `find_spec` is used rather than `try`/`except ImportError` deliberately: catching
`ImportError` would also swallow a genuine broken-import bug inside a real `provider.py`,
whereas `find_spec` distinguishes "not present" from "present but failing".

*Alternatives considered:* absorbing the `ACT` group into this change (larger scope, and this
change's spec forbids `provider.py`); or parking the adapter outside `providers/` until
registration (unidiomatic, needs a second move). The five-line fix keeps the staging strategy
the whole plan is built on, and is a defensible robustness fix upstream.

### D7 — Do not override `supports_process_worker`

`process_worker.py` calls `provider.connection_factory.connect(...)` *inside* the child
process — it opens a fresh connection rather than pickling one — so the WebSocket never
crosses the process boundary, and pyexasol yields plain tuples, which pickle fine.
`SurrealDBAdapter` disables the worker, but its reasoning does not transfer.

## Risks / Trade-offs

- **Positional access to `conn.meta.*` rows** → `KeyError` at runtime, invisible to `mypy`
  because the rows are `dict[str, Any]`. Mitigated by D2 stating the return shapes explicitly
  and by the spec scenario "Metadata rows are read by key", which the step-11 unit tests
  should implement with deliberately reordered dict keys.
- **Guard/fetch ordering in `execute_query`** → reversing them makes every non-`SELECT` raise
  `ExaRuntimeError`. Mitigated by D3 recording the raise, and by the spec scenario "Statement
  with no result set" asserting no fetch method is called.
- **No runtime verification in this change** → `pyexasol` is absent, so nothing here is
  executed end-to-end; a wrong kwarg name would pass `ruff` and `mypy` silently. Mitigated by
  verifying every kwarg and system-table column against the driver source and Exasol docs
  (cited in D2/D3), and accepted because plan.md steps 10-11 add mocked unit tests and step 13
  adds a Docker integration test.
- **Facts sourced from published docs, not Context7** → Context7 MCP was not connected in this
  session (it exposes no tools), so pyexasol and Exasol details were read from
  `raw.githubusercontent.com/exasol/pyexasol` (driver source) and `docs.exasol.com` (system
  tables). These are the same upstream sources Context7 indexes, but the verification path
  differs from the repo's usual convention.
- **`DatabaseAdapter` gains a subclass that cannot be smoke-tested by the suite** → the package
  is unreachable from the registry, so a broken adapter is caught only at step 7. Accepted:
  that isolation is the entire point of splitting steps 1-4 from the `ACT` group.

## Migration Plan

No migration, no rollback plan needed. The change is purely additive and unreachable: two new
files in a package nothing imports. Reverting is deleting the directory.

Sequencing note for whoever picks up the next change: this must land before plan.md step 7,
because `provider.py`'s `provider_factory` imports `ExasolAdapter`.

## Open Questions

None blocking. Both items plan.md flagged for this step are now resolved:

1. **`ExaStatement` result detection** — resolved in D3: use `stmt.result_type`, checked before
   fetching.
2. **pyexasol / system-table details unverified through Context7** — re-verified in D2 and D3
   against the driver source and Exasol docs. Context7 is unavailable in this session; if it
   comes online, D2's column lists and D3's `result_type` values are the things worth
   re-confirming.

Deferred to their own steps, not this one: how to patch the lazy driver import in unit tests
(step 10) and whether `exasol/docker-db` is acceptable in CI (step 14).
