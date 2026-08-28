## Context

`ExasolAdapter` (change `exasol-adapter`) and its registration (change
`exasol-provider-registration`) are both complete in the working tree. Exasol appears in the
connection picker, resolves through `get_supported_db_types()`, and passes
`tests/test_schema_capabilities.py`. What it does **not** have is an installable driver or a single
behavioural test.

Three constraints shape this change:

1. **The default CI unit job installs no extras.** `.github/workflows/ci.yml:66` is
   `uv sync --group test --no-dev`. Every test added here is collected by that job — nothing under
   `tests/connections/` is in its `--ignore` list — so **no test may require `pyexasol` to be
   importable**. This is the hardest constraint and it drives D2.
2. **The adapter imports its driver lazily.** `connect()` calls
   `self._import_driver_module("pyexasol", ...)`, which routes through
   `providers/driver.py::import_driver_module` to `importlib.import_module`. The driver name only
   ever exists as a *string* in `sqlit/`; there is no `import pyexasol` statement anywhere. This is
   what makes the driver fakeable (D2) and what makes the mypy override inert (D4).
3. **The behaviour being pinned is already decided.** Both prior changes recorded their reasoning in
   design documents and in plan.md's session log. This change adds no behaviour; it converts those
   recorded decisions into assertions. Where a test and a recorded decision disagree, the recorded
   decision wins and the test is wrong.

## Goals / Non-Goals

**Goals:**

- `pip install sqlit-tui[exasol]` and `uv sync --extra exasol` install a working `pyexasol`.
- Every behavioural decision from the two prior changes has at least one assertion that fails if the
  decision is reverted.
- All new tests pass with `pyexasol` **absent**, so the default unit job covers them on every push.
- The `exasol` pytest marker is registered, so plan step 13's integration test can use it without a
  `PytestUnknownMarkWarning`.

**Non-Goals:**

- Testing `pyexasol` itself, or that its kwargs are spelled the way its 2.x API expects. Mocked
  tests pin *sqlit's call shape*, not the driver's contract — that is the integration test's job
  (plan step 13). See the first risk below.
- Any Docker service, integration test, CI workflow edit, or documentation (plan steps 12-15).
- Any change to `sqlit/` source. If a test reveals an adapter bug, that is a finding to record, not
  a licence to broaden this change.
- Coverage thresholds or a coverage gate.

## Decisions

### D1 — Tests live in `tests/connections/providers/exasol/`, not `tests/unit/providers/`

Both directories exist and both hold adapter tests. `tests/connections/providers/` is the
per-provider tree (`hana/`, `oracle/`), each a package with an empty `__init__.py`;
`tests/unit/providers/` holds standalone cross-cutting files such as `test_osquery_adapter.py`.
Exasol is a provider with three test files, so it takes the per-provider tree, matching plan.md and
giving `uv run pytest tests/connections/providers/exasol/ -v` as a single natural gate.

*Alternative rejected:* one flat `tests/unit/test_exasol_adapter.py`. It would work, but it splits
Exasol away from the convention its two nearest templates already follow.

### D2 — Fake the driver with `patch.dict("sys.modules", {"pyexasol": MagicMock()})`

**This resolves plan.md step 10's open item.** `importlib.import_module` returns an existing
`sys.modules` entry without touching the filesystem, so seeding that dict makes
`_import_driver_module("pyexasol", ...)` hand back the mock. `adapter.connect(config)` then runs end
to end, and `mock.connect.call_args` holds the real kwargs.

This is the established house pattern — `tests/unit/test_extra_options_passthrough.py:26` for
Snowflake, psycopg2 and PyMySQL, and `tests/unit/test_flight_adapter.py:15`. Using it keeps the
Exasol tests recognisable to a reviewer and satisfies constraint 1.

*Alternatives rejected:*

- **Patch `ExasolAdapter._import_driver_module`.** Shorter, but it stubs out the call site under
  test: the `driver_name` / `extra_name` / `package_name` plumbing that produces sqlit's "install the
  extra" prompt would stop being exercised, and a typo in the module name would pass.
- **Install the extra and monkeypatch `pyexasol.connect`.** This would make the tests depend on
  `uv sync --extra exasol`, breaking them in the default unit job. Directly violates constraint 1.

### D3 — Assert the *absence* of unused credential keys, not their emptiness

For `authenticator == "password"`, the assertion is `"access_token" not in kwargs`, never
`kwargs.get("access_token") == ""`. This is the whole point of the branch: as recorded in plan.md's
session log, pyexasol's `_login()` branches on token *truthiness*, so a present-but-empty
`access_token` is falsy and silently falls back to password login — precisely the bug an
emptiness-tolerant assertion would let through. The same holds symmetrically: under token auth,
`"user"` and `"password"` must both be absent from the kwargs.

### D4 — Add the `pyexasol` mypy override even though it is inert, and do not treat `mypy` as its verification

`[tool.mypy]` sets `exclude = ["tests/"]`, and `sqlit/` never names `pyexasol` outside a string
literal, so mypy has no `pyexasol` import to resolve and the `ignore_missing_imports` entry changes
nothing today. It is added anyway because `hdbcli` and `teradatasql` — the two providers built the
same lazy way — are already in that list, so omitting `pyexasol` would make Exasol the inconsistent
entry, and because the override becomes load-bearing the moment anyone adds a `TYPE_CHECKING` import
of the driver.

The consequence matters for the tasks: **`uv run mypy sqlit` passing does not verify this edit.** Its
verification is `uv sync --extra exasol` followed by `uv run python -c "import pyexasol"`.
(`clickhouse_connect` is the contrast: `clickhouse/adapter.py:98` has a real in-function
`import clickhouse_connect`, which mypy does analyse, so *that* override is genuinely required.)

### D5 — Let `uv sync` fold in the pre-existing `uv.lock` drift rather than fighting it

`uv.lock` is already modified on this branch, unrelated to Exasol: it drops the stale `mariadb`
package entry, because `pyproject.toml` in `HEAD` already points the `mariadb` extra at `PyMySQL` and
the lockfile had not caught up. `uv lock` regenerates the whole file, so that refresh cannot be
separated from the `pyexasol` addition — and reverting `uv.lock` first would simply re-drop
`mariadb` on the next resolve.

Decision: accept both in one lockfile diff and call it out in the upstream PR description, so the
reviewer is not surprised by a `mariadb` deletion inside an Exasol PR. Hand-editing `uv.lock` to
isolate the change is not an option; a hand-edited lockfile is worse than an explained one.

### D6 — Plain `pyexasol>=2.0.0` with no environment marker; let `uv` place the marker

`pyexasol` declares `requires-python >=3.10,<3.15`; sqlit declares `>=3.10` with no ceiling. `uv`
resolves across the full declared range and attaches a `python_full_version < '3.15'` marker to the
locked entry itself, so `uv lock` succeeds and per-interpreter installs stay correct. No extra in
`pyproject.toml` carries an inline marker today, so adding one here would be the odd entry out.

**Verification during implementation:** `uv lock` (or `uv sync --extra exasol`) must succeed without
a resolution error naming Python 3.15. If it fails, the escape hatch is
`"pyexasol>=2.0.0; python_version < '3.15'"` **in the `all` extra only**, leaving the dedicated
`exasol` extra unmarked so an explicit opt-in still fails loudly on an unsupported interpreter
rather than silently installing nothing.

### D7 — Register the `exasol` marker now, apply it to nothing

The three new test files are plain driver-free unit tests and carry no marker, matching
`tests/connections/providers/hana/test_get_columns.py`, which has no marker either (and there is no
`hana` marker). The registered `exasol` marker is therefore unused until plan step 13. That is
deliberate: registering it here keeps step 8 self-contained as "everything `pyproject.toml` needs for
Exasol", and an unused-but-registered marker is inert. Expect `-m exasol` to select zero tests after
this change.

### D8 — Pin the empty-schema `get_columns` behaviour as-is; do not add a fallback

plan.md's session log flags it: `default_schema` is `""`, so `get_columns(conn, table)` with no
schema passes an empty pattern to `conn.meta.list_columns`, which pyexasol turns into a pattern
matching nothing. It is unreachable through the UI — every Exasol table arrives from `get_tables()`
as a populated `(TABLE_SCHEMA, TABLE_NAME)` pair — and the prior change deliberately left it
spec-faithful rather than inventing a fallback.

The test asserts the current behaviour (`list_columns` receives `""`), with a comment saying it
documents a deliberate choice rather than a desirable one. This is the honest option: a test that
pins the decision makes a future reversal visible, whereas no test at all leaves the next reader
guessing whether it was ever considered.

## Risks / Trade-offs

- **Mocked tests cannot catch a pyexasol API mismatch.** `MagicMock` accepts any kwarg, so if
  `websocket_sslopt`, `access_token` or `refresh_token` were misspelled — or renamed in pyexasol 2.x
  — every test here still passes while a live connect fails. → *Mitigation:* accept this explicitly.
  These tests pin sqlit's intent; plan step 13's Docker integration test is the only thing that can
  validate the driver contract. Keep the kwarg names as literal strings in the assertions so a
  rename surfaces as a visible diff in the test file rather than passing silently.

- **`MagicMock` makes the `result_type` guard pass for the wrong reason.** On a bare `MagicMock()`
  statement, `stmt.result_type != "resultSet"` evaluates `True`, so `execute_query` returns
  `([], [], False)` and a sloppy result-set test goes green while asserting nothing. → *Mitigation:*
  set `result_type` explicitly on every statement mock, and add the inverse test — a `rowCount`
  statement must leave `fetchall` / `fetchmany` **uncalled**
  (`stmt.fetchall.assert_not_called()`), which is the actual invariant the guard protects.

- **Unrelated `mariadb` deletion in the lockfile diff.** → *Mitigation:* D5; call it out in the PR
  body.

- **`pyexasol`'s `<3.15` ceiling constrains the `all` extra on future interpreters.** →
  *Mitigation:* D6, with the marker escape hatch scoped to `all`.

- **Bundling packaging with three test files makes the change wider than the plan's step
  granularity.** → *Mitigation:* the tasks keep each plan step as its own numbered group with its own
  verify command, and groups 2-4 are independently revertible. Only group 1 (packaging) unblocks the
  others.

## Migration Plan

No migration. Additive `pyproject.toml` metadata plus new test files; no existing behaviour changes.
Rollback is a `git revert` of the commit — the `exasol` extra disappearing cannot break an existing
install, because no default dependency references `pyexasol`.

## Open Questions

- **Lower bound `>=2.0.0` or `>=2.3.2`?** plan.md specifies `>=2.0.0` and this change follows it;
  every API detail was in fact verified against 2.3.2. The loose bound matches house style
  (`hdbcli>=2.20.0`, `teradatasql>=20.0.0` are all loose lower bounds) and `uv.lock` pins the real
  resolved version, so the exposure is limited to someone installing an old pyexasol outside the
  lock. Raise it to `>=2.3.2` only if the upstream reviewer asks.
- **Does the maintainer want `pyexasol` in the `all` extra at all?** `all` is already 28 packages and
  this makes 29. plan.md step 8 says add it and every other provider is in there, so this change
  adds it. Flagged because it is the one line here a reviewer might ask to drop — and dropping it is
  a one-line change with no test consequences.
