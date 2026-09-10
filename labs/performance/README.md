# sqlit performance laboratory

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
