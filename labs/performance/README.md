# sqlit performance laboratory

[Read the rendered performance paper](https://maxteabag.github.io/sqlit/performance/pr-331/).

The lab runs the real Textual app in an isolated 120 × 40 pseudo-terminal,
executes the sqlit database adapters against disposable databases, and preserves
raw observations. It never opens saved user connections. The default application
settings and the explicitly disabled process-worker setting are separate startup
conditions. Ordinary UI workload runs use synthetic stores and no query worker.

## Reproduce

Create baseline and candidate worktrees and install the same locked dependencies:

```bash
uv sync --frozen --group dev --extra postgres --extra mysql --extra duckdb
python labs/performance/study.py --baseline /absolute/baseline \
  --candidate /absolute/candidate --python /absolute/candidate/.venv/bin/python \
  --output /absolute/evidence --docker --dry-run
```

Remove `--dry-run` to run the study. `--quick` is a smoke run, not a statistical
study. Select `--phases startup,cpu,completion,render,idle` to run without Docker.
The network phase requires the cached `postgres:16-alpine`, `mysql:8.0`, and
`mariadb:11` images. It binds random loopback ports, limits each owned container
to one CPU and 512 MiB, and stops/removes it in `finally`. No external database
endpoint is accepted. Image content hashes are recorded.

Jobs run sequentially to avoid competing benchmarks. Baseline/candidate order is
randomized with a fixed seed within trial blocks. Receipts allow rerunning the
same command to resume verified jobs. The helper refuses dirty production source
and checks its commit before each job. Re-run a phase into a new output directory
when changing the source or measurement code.

## Individual experiments

- `run.py --mode startup`: native startup profiler, external ready observation,
  process CPU and terminal bytes. `--imports` enables the existing import tracer
  as a diagnostic run, separate from ordinary timing samples.
- `run.py --mode ui`: actual result loading, scrolling and filtering, with 1,000
  to 50,000 rows, wide rows, 10,000-character strings and decimals.
- `run.py --mode completion`: actual application completion/dropdown path with
  1,000 and 5,000 stored routines.
- `run.py --mode idle`: two 5-second steady-state CPU windows. No high-frequency
  heartbeat runs during this measurement. The final requested refresh is included.
- `run.py --diagnostics --profile`: native debug event log and 50 ms watchdog,
  Chrome trace, cProfile and a known 120 ms blocking control in the UI workload.
- `run.py --workload render_1000_3_long`: run one dataset in a fresh process.
- `cpu_lab.py`: deterministic completion scaling with excluded warmups and output
  hashes. Select code with `PYTHONPATH=/absolute/worktree`.
- `database_lab.py --docker --provider postgresql --one-way-ms 20`: actual SQL
  through a pipelined TCP relay adding 20 ms in each direction. Counts protocol
  bytes in each direction, not packet headers or retransmissions.
- `local_database_lab.py`: SQLite/DuckDB fresh/reused connections, actual
  cancellable queries and cold/warm process workers, plus explicit IPC boundaries.

Every helper accepts `--output`; use `--help` for the remaining arguments. The
database and CPU helpers run with the selected worktree's Python and PYTHONPATH.
The `variants.py` interventions are experimental, loaded only by the lab. The
read-only row backend samples column widths and does not implement production
export/mutation contracts. Do not install it as a production backend.

## Interpretation

- Cold process does not mean cold filesystem cache. The separate empty-bytecode
  condition redirects Python's bytecode lookup, without dropping host caches.
- First UI refresh, full dataset availability and event-loop delay are distinct.
  CPU time is consumed processor time; idle CPU percent is relative to one core.
- The UI sampler observes lateness beyond a 5 ms asyncio sleep. It cannot measure
  the terminal emulator's GPU, physical display FPS or battery consumption.
  Frame counts are application display calls, not physical screen presentations.
- RSS is process high-water memory where labeled `maxrss_kib`; values from later
  workloads in the same process are cumulative. Do not subtract them as per-query
  allocations. Process-worker parent CPU excludes the worker's CPU.
- Ordinary result caps can limit Python rows while buffered drivers still receive
  all database rows. Explicit LIMIT, PostgreSQL named cursors, and MySQL streaming
  cleanup have different semantics; these experiments do not authorize arbitrary
  SQL rewriting or removal of cancellation isolation.
- Compare the same workload, boundary and environment. Profilers and synthetic
  stall controls are diagnostic evidence, excluded from timing summaries.

The retained report and machine-readable observations are under
`docs/performance/`. Raw local runs remain under the ignored `evidence/` directory.

## Statistics, paper and browser verification

`summarize.py --input EVIDENCE/study --output docs/performance` reads completed
runs, verifies completion-output hashes, calculates descriptive statistics and
paired/independent bootstrap intervals, and emits CSV plus lossless gzip chunks.
`export_evidence.py --evidence EVIDENCE --output docs/performance` packages the
selected named diagnostic pilots and `regression-candidate.xml` from the broader
test lane. It optionally includes `regression-python310.xml`. These diagnostics
and test results are separate prerequisites, not generated by the timed study.

To rebuild the checked-in paper from its retained data:

```bash
# Keep plotting dependencies out of the measured app environment.
uv venv /tmp/sqlit-report-env
uv pip install --python /tmp/sqlit-report-env/bin/python \
  -r labs/performance/requirements-report.txt
/tmp/sqlit-report-env/bin/python labs/performance/build_report.py \
  --data docs/performance/data.json

node labs/performance/verify_report.cjs \
  docs/performance/report.html /absolute/browser-qa \
  /absolute/node_modules/playwright /absolute/chromium
```

The browser verifier checks desktop/mobile overflow, all local links, figures,
filtered CSV export, built-in traces, local trace uploads, page errors and
unexpected network requests. Inspect its screenshots as well as the JSON result.
The paper template describes the retained study: after new experiments, review
the narrative, source revisions, population, sample counts and qualifications
before publishing another report. Do not reuse historical prose as fresh evidence.

For new verification lanes, `verify_code.py --repo REPO --python PYTHON --output
EVIDENCE/regression-candidate` records the isolated broad suite, JUnit and code
provenance. Add `--compatibility` with the older interpreter and output prefix
`EVIDENCE/regression-python310` for the focused compatibility lane. `--dry-run`
inspects either command without executing tests. The published study's original
test logs are retained separately from subsequent reproductions.

`verify_cells.py --output EVIDENCE/cells-qa.svg` waits for the lazy results widget,
checks 48 complete long/Unicode values and captures a headless 160 × 40 display
fixture. It is visual regression evidence, not a timed database query. Render an
SVG through `verify_report.cjs` using the same browser/module arguments; its SVG
mode uses a fresh headless browser and writes `artifact.png`.

## Publish a browser-readable report

Publishing requires the user's authorization. A GitHub `blob` or raw-source URL
does not deliver a rendered interactive page. The current public paper is hosted
under `performance/pr-331/` on this repository's `gh-pages` branch.

```bash
# Inspect the target and existing Pages configuration first.
python labs/performance/publish_pages.py --repo OWNER/REPO \
  --source docs/performance --path performance/REPORT_NAME

# Publish the already-reviewed report and adjacent public assets.
python labs/performance/publish_pages.py --repo OWNER/REPO \
  --source docs/performance --path performance/REPORT_NAME --publish

# Verify the actual anonymous HTTPS page, controls and relative downloads.
node labs/performance/verify_report.cjs https://OWNER.github.io/REPO/performance/REPORT_NAME/ \
  /absolute/live-qa /absolute/node_modules/playwright /absolute/chromium
```

The publisher uses a temporary checkout, preserves other Pages paths, and refuses
to replace an existing publishing source or change a Jekyll site's semantics. It
copies the report as both `report.html` and `index.html`, preserves its assets,
fixes the repository-source README link, and writes a source/hash receipt.
Pages can already be correctly configured when a creation call returns an error;
reconcile the actual configuration rather than repeating an external effect.
A build being queued is not delivery:
require the deployed HTML to return 200 with `text/html`, check its content hash,
and run the headless verifier before posting the reading link.
