## Context

Steps 1-14 of plan.md are `done`: Exasol has a provider package, a schema, a registered
`DatabaseType`, 55 unit tests, a compose service, an integration suite that passes 20/8-skipped
against a live server, and a CI job. Step 15 — the documentation — is the last `todo`, and it is
the first thing an upstream reviewer of `Maxteabag/sqlit` will read.

The two target files have different audiences and different failure modes:

- `README.md` is read by **users**. Its supported-database sentence (line 28) is a marketing
  surface; its Driver Reference table (lines 277-297) is operational — a user reaches it because
  sqlit just told them a driver is missing.
- `CONTRIBUTING.md` is read by **contributors** who are about to run the test suite. Line 49 lists
  the enterprise-profile containers; lines 82-186 document per-engine environment variables.

The binding constraint is that everything written here is a claim about code that already exists.
The env-var table in particular is a restatement of `tests/fixtures/exasol.py:15-24`, and the two
can silently diverge. This design treats each documented value as sourced from a specific line
rather than from memory of the implementation sessions.

A second constraint is that both files are top-level documents in someone else's repository. Every
line of the diff is reviewed. Anything beyond the four insertions is noise the maintainer must read
and decide about.

## Goals / Non-Goals

**Goals:**

- A user can discover Exasol support and get a working driver install command from `README.md`
  alone.
- A contributor can bring up the Exasol container, know it will take minutes, and know which
  variables repoint the tests, from `CONTRIBUTING.md` alone.
- Every documented default matches the code that reads it, verified by comparison rather than
  recall.
- The diff is minimal and additive — a reviewer can approve it by reading four insertions.

**Non-Goals:**

- **No "adding a new provider" guide.** plan.md's Context section observes the repo has no such
  documentation and that the convention had to be read off the code. Writing that guide is real
  value, but it is a different change with a different reviewer conversation, and inventing repo
  conventions inside a provider PR invites rejection of both.
- **No documentation of the `exasol` extra beyond the Driver Reference row.** The README documents
  extras in prose for `ssh` only; no per-database extra has its own section. Adding one for Exasol
  would make it the most-documented engine in the file.
- **No fixing of pre-existing gaps.** The Driver Reference table omits Db2, SAP HANA, Teradata,
  Trino, Presto and RedShift. That is a real defect. It is not this change's defect.
- **No changes under `sqlit/`, `tests/`, `infra/`, `.github/` or `pyproject.toml`.**
- **Not the follow-up `get_columns` fix** (`O1` in plan.md's session log) and not plan.md's Final
  verification block. Both were scoped out of this change deliberately.

## Decisions

### D1 — Exasol goes after Teradata in the supported-database sentence

The sentence at `README.md:28` is neither alphabetical nor grouped by category; its order is
historical. That leaves two candidate rules: append at the end, or mirror the connection picker.

Mirroring the picker wins. plan.md step 6 placed Exasol after Teradata in the `DatabaseType` display
order, and the step 5-7 session verified that position headlessly ("picker option after Teradata").
A reader who scans the README list and then opens the picker sees the same neighbours. Appending
after `osquery` would put an enterprise analytical database at the end of a list that closes with
`SurrealDB and osquery`, and would require rewriting the `and osquery.` clause — a larger diff for a
worse result.

*Alternative considered:* alphabetical insertion (after `DuckDB`). Rejected — the list is not
alphabetical, so this imposes a rule the file does not follow anywhere else.

### D2 — The Driver Reference row goes between Spanner and Apache Arrow Flight SQL

The table's row order roughly tracks the prose list, with omissions. Exasol's prose neighbours —
Teradata before it, Trino and Presto after it — are all absent from the table, so its position
cannot be read off directly. Walking outward from Exasol's prose position to the nearest engines
that *are* in the table gives `Spanner` before and `Apache Arrow Flight SQL` after. Inserting there
keeps the table's relative order consistent with the prose list it shadows.

*Alternatives considered:* appending after `osquery` — simplest diff, but makes the table's ordering
rule strictly worse for the next person; grouping next to `Snowflake` as "the other analytical
warehouse" — rejected because every engine in this repo ships behind a named extra, so there is no
"extras-gated" grouping to join, and Snowflake's neighbours (`Cloudflare D1`, `Firebird`) show the
table is not grouped by engine category either.

This is a low-stakes call. It is recorded because "why is the row here?" is otherwise unanswerable
in review, and an unanswerable question costs a round trip.

### D3 — Every documented default is read out of the code, not recalled

The six defaults come from `tests/fixtures/exasol.py`, which reads them via `os.environ.get` with
literal fallbacks. The implementation task extracts them by grepping that module and comparing
against the table, rather than transcribing from the proposal or from the session log.

This matters because `EXASOL_PASSWORD` is `exasol` and `EXASOL_USER` is `sys` — the `docker-db`
defaults, values a reader has no independent way to check. A wrong value here is undetectable by
review and produces a failed login for the contributor who trusts it.

### D4 — `EXASOL_READY_TIMEOUT` is documented despite having no analogue elsewhere

No other engine's table has a timeout row, so including one is a visible asymmetry a reviewer may
question. It earns its place: the step 12-14 session measured port 8563 open at 21s and the first
successful login at 101s, and the fixture's readiness gate is a real connect retried to a deadline
precisely because of that gap. On a cold ~4 GB pull, or slower hardware, 300 seconds is reachable.
A contributor who hits the deadline needs to know the knob exists; nothing else in the repo tells
them.

*Alternative considered:* documenting the five connection variables only and leaving the timeout to
be discovered from the source. Rejected — a contributor debugging a timeout is exactly the reader
who will not think to open a fixture module.

### D5 — The boot-time warning is placed with the Exasol material, not by editing line 54

`CONTRIBUTING.md:54` says "Wait for the databases to be ready (about 30-45 seconds)". That sentence
is correct for the default profile, which is what most contributors run. Rewriting it to
accommodate Exasol would degrade accurate guidance for the common case in service of an opt-in
profile.

The warning therefore attaches to the Exasol material, where the reader who started the enterprise
profile will be. The distinction it must draw is port-open versus login-accepted, because that is
the shape of the confusion — `is_port_open` returning true is exactly what makes the container look
ready when it is not.

### D6 — Diff minimalism is a design constraint, not a style preference

The intended diff is four insertions: one clause on `README.md:28`, one table row in the Driver
Reference, one clause on `CONTRIBUTING.md:49`, and one block (table plus warning) in the Environment
Variables section. No reflow of the line-28 paragraph, no realignment of the Driver Reference
table's column padding, no reordering of the env-var sections, no fixing of adjacent typos.

The Driver Reference table's cells are space-padded to a common width. A new row whose content
exceeds the current column width would, under any auto-formatter, reflow every row in the table and
turn a 1-line diff into a 20-line one. `Exasol` / `pyexasol` / `pipx inject sqlit-tui pyexasol` /
`python -m pip install pyexasol` are all shorter than the widest existing cells
(`snowflake-connector-python` and its commands), so the new row pads into the existing widths and no
other row moves. This is a fact to verify in the diff, not to assume.

### D7 — Verification is comparison against code plus a diff read

There is no test to run: no Python changes, and pre-commit carries no markdown linter — only
`trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-toml`, `check-added-large-files`
and `check-merge-conflict`. Of those, `trailing-whitespace` is the one these edits can trip, since
markdown table rows are easy to leave padded.

Verification is therefore mechanical where it can be: grep the fixture for `EXASOL_` and diff that
set against the table; grep `pyproject.toml` for the `exasol` extra and check the package name;
`git diff --stat` to confirm exactly two files; and read the rendered diff to confirm no
neighbouring row moved.

## Risks / Trade-offs

- **A documented default drifts from the fixture later** → The spec states the equality as a
  testable scenario, and D3 makes the initial values code-derived. Nothing enforces it at CI time;
  this is accepted, and matches how every other engine's table in the file already works.
- **The reviewer objects to `EXASOL_READY_TIMEOUT` as asymmetric** → D4 records the measured
  21s/101s figures as the justification. If pushed back on, dropping that one row costs nothing else
  in the change.
- **The reviewer prefers a different row position in the Driver Reference** → D2 records the rule
  used, so the discussion is about the rule rather than about taste. Moving the row is a one-line
  change either way.
- **An editor auto-formats the markdown tables on save** → D6 identifies this as the main way a
  4-line diff becomes a 40-line one. The mitigation is checking `git diff` before committing, which
  the tasks make an explicit step rather than an assumed habit.
- **Documentation claims something the code does not do** → The spec's final requirement makes
  "every claim traces to existing code" a checkable condition. The nearest live example is the
  `get_columns` casing defect the step 12-14 session found: the docs must not imply Exasol
  introspection works in cases where it is known not to.
- **Trailing whitespace in new table rows trips pre-commit** → Caught by the hook itself if
  pre-commit runs; the tasks include running it against the two files so it is caught before the
  commit rather than during it.
