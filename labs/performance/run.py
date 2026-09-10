#!/usr/bin/env python3
"""Reproducible sqlit PTY startup and UI experiments (synthetic data only).

The controller uses only the standard library. --python selects the pinned
sqlit environment; --repo selects the code under test, independently of this
lab's location. No user configuration or database credentials are loaded.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import platform
import pty
import re
import resource
import select
import struct
import subprocess
import sys
import tempfile
import termios
import time
from pathlib import Path


def isolated_env(repo: Path, state: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("SQLIT_", "PYTHONPROFILE", "TEXTUAL_")):
            env.pop(key)
    env.update(
        PYTHONPATH=str(repo), SQLIT_CONFIG_DIR=str(state / "config"),
        TMPDIR=str(state / "tmp"), TERM="xterm-256color", COLORTERM="truecolor",
        PYTHONHASHSEED="0", PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring",
        OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
    )
    (state / "config").mkdir()
    (state / "tmp").mkdir()
    # Public synthetic settings: disable external discovery and eager workers.
    (state / "config" / "settings.json").write_text(json.dumps({
        "theme": "tokyo-night", "process_worker": False,
        "process_worker_warm_on_idle": False,
        "docker_auto_detect": False, "cloud_auto_detect": False,
    }))
    return env


def pty_run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: float,
            startup_log: Path | None = None) -> dict:
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.perf_counter()
    proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=slave, stdout=slave,
                            stderr=slave, start_new_session=True)
    os.close(slave)
    received = bytearray()
    ready_ms = None
    timed_out = False
    try:
        while True:
            if time.perf_counter() - start > timeout:
                timed_out = True
                import signal
                os.killpg(proc.pid, signal.SIGKILL)
                break
            readable, _, _ = select.select([master], [], [], .005)
            if readable:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                received.extend(chunk)
            if ready_ms is None and startup_log and startup_log.exists():
                if "start_to_first_refresh_ms=" in startup_log.read_text():
                    ready_ms = (time.perf_counter() - start) * 1000
            if proc.poll() is not None and not readable:
                break
    finally:
        proc.wait()
        os.close(master)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    elapsed = (time.perf_counter() - start) * 1000
    if timed_out or proc.returncode:
        raise RuntimeError(f"child failed: rc={proc.returncode}, timeout={timed_out}\n"
                           + received[-5000:].decode(errors="replace"))
    return {
        "process_wall_ms": elapsed, "parent_ready_ms": ready_ms,
        "process_cpu_ms": ((after.ru_utime-before.ru_utime)+(after.ru_stime-before.ru_stime))*1000,
        "pty_bytes": len(received), "output_tail": received[-3000:].decode(errors="replace"),
    }


def controller(args: argparse.Namespace) -> None:
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    meta = {"sha": sha, "repo": str(repo), "python": args.python,
            "label": args.label, "variant": args.variant,
            "mode": args.mode, "platform": platform.platform(), "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "loadavg": os.getloadavg(), "viewport": [120, 40],
            "settings": "isolated; eager worker off; null keyring; synthetic stores for UI"}
    diff = subprocess.check_output(["git", "diff", "HEAD", "--", "sqlit"], cwd=repo)
    meta.update(source_diff_sha256=hashlib.sha256(diff).hexdigest(), source_dirty=bool(diff),
                worker_default=args.worker_default, no_bytecode_cache=args.no_bytecode_cache,
                workload=args.workload, diagnostics=args.diagnostics, profile=args.profile)
    (output / "metadata.json").write_text(json.dumps(meta, indent=2))
    for index in range(args.repeat):
        run_dir = output / f"run-{index:03d}"
        run_dir.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="sqlit-perf-") as temp:
            state = Path(temp)
            env = isolated_env(repo, state)
            if args.worker_default:
                settings_path=state / "config" / "settings.json"
                settings=json.loads(settings_path.read_text())
                settings.pop("process_worker")
                settings.pop("process_worker_warm_on_idle")
                settings_path.write_text(json.dumps(settings))
            if args.no_bytecode_cache:
                env["PYTHONPYCACHEPREFIX"]=str(state / "fresh-pycache")
                env["PYTHONDONTWRITEBYTECODE"]= "1"
            if args.mode == "startup":
                log = run_dir / "startup.txt"
                command = [args.python, "-c", "from sqlit.cli import main; raise SystemExit(main())",
                           "--profile-startup-exit", f"--profile-startup-file={log}"]
                if args.imports:
                    command += [f"--profile-startup-imports-file={run_dir / 'imports.txt'}"]
                    env["PYTHONPROFILEIMPORTTIME"] = "1"
                result = pty_run(command, cwd=state, env=env, timeout=30, startup_log=log)
                content = log.read_text()
                match = re.search(r"start_to_first_refresh_ms=([\d.]+)", content)
                assert match, "Native first-refresh marker missing"
                result["cli_first_refresh_ms"] = float(match.group(1))
            else:
                result_path = run_dir / "ui.json"
                command = [args.python, str(Path(__file__).resolve()), "--child", "--mode", args.mode,
                           "--variant", args.variant, "--output", str(result_path)]
                if args.profile:
                    command += ["--profile"]
                if args.headless:
                    command += ["--headless"]
                if args.diagnostics:
                    command += ["--diagnostics"]
                if args.workload:
                    command += ["--workload",args.workload]
                result = pty_run(command, cwd=state, env=env, timeout=180)
                result["workloads"] = json.loads(result_path.read_text())
            result.update(index=index, label=args.label, variant=args.variant, sha=sha)
            (run_dir / "result.json").write_text(json.dumps(result, indent=2))
            print(json.dumps({k:v for k,v in result.items() if k not in {"output_tail", "workloads"}}), flush=True)


def child(args: argparse.Namespace) -> None:
    import asyncio
    import cProfile
    from decimal import Decimal

    from variants import install_variant

    from sqlit.domains.shell.app.main import SSMSTUI
    from sqlit.shared.app.runtime import RuntimeConfig
    from tests.ui.mocks import MockConnectionStore, MockSettingsStore, build_test_services
    install_variant(args.variant)

    output = Path(args.output)
    runtime = RuntimeConfig(process_worker=False, process_worker_warm_on_idle=False,
                            ui_stall_watchdog_ms=50 if args.diagnostics else 0)
    services = build_test_services(runtime=runtime, connection_store=MockConnectionStore(),
                                  settings_store=MockSettingsStore({"theme": "tokyo-night"}),
                                  docker_detector=lambda: (None, []))
    app = SSMSTUI(services=services)
    trace: list[dict] = []
    records: list[dict] = []
    gaps: list[tuple[float, float]] = []
    frames: list[float] = []
    terminal_bytes = 0
    start = time.perf_counter()
    app._debug_event_log_path = output.with_suffix(".debug.jsonl")
    app._ui_stall_watchdog_log_path = output.with_suffix(".watchdog.txt")
    profile = cProfile.Profile() if args.profile else None
    original_display = app._display

    def measured_display(*a, **kw):
        frames.append(time.perf_counter())
        return original_display(*a, **kw)

    app._display = measured_display

    async def heartbeat():
        while True:
            before = time.perf_counter()
            await asyncio.sleep(.005)
            now = time.perf_counter()
            gaps.append((now, max(0, (now-before-.005)*1000)))

    async def refresh():
        fut = asyncio.get_running_loop().create_future()
        app.call_after_refresh(lambda: fut.set_result(None) if not fut.done() else None)
        app.refresh()
        await asyncio.wait_for(fut, 15)

    async def measure(name, operation):
        await asyncio.sleep(.08)
        cpu, wall = time.process_time(), time.perf_counter()
        frame_start = len(frames)
        byte_start = terminal_bytes
        watchdog_start = len(app._ui_stall_watchdog_events)
        app.emit_debug_event("lab.begin", category="performance", workload=name)
        if profile:
            profile.enable()
        extra = await operation()
        if profile:
            profile.disable()
        await refresh()
        end = time.perf_counter()
        cpu_ms = (time.process_time()-cpu)*1000
        await asyncio.sleep(.02)  # include the heartbeat delayed by the operation
        selected = [g for t,g in gaps if wall <= t <= end+.02]
        record = {"name": name, "wall_ms": (end-wall)*1000, "cpu_ms": cpu_ms,
                  "loop_delays_ms": selected, "frames": len(frames)-frame_start,
                  "terminal_bytes": terminal_bytes-byte_start,
                  "frame_times_ms": [(t-wall)*1000 for t in frames[frame_start:] if t <= end],
                  "watchdog_events": len(app._ui_stall_watchdog_events)-watchdog_start,
                  "maxrss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  **(extra or {})}
        records.append(record)
        trace.append({"name":name, "ph":"X", "pid":1, "tid":1,
                      "ts":(wall-start)*1e6, "dur":(end-wall)*1e6,
                      "args":{k:v for k,v in record.items() if k not in {"loop_delays_ms", "frame_times_ms"}}})
        app.emit_debug_event("lab.end", category="performance", workload=name,
                             wall_ms=record["wall_ms"], cpu_ms=cpu_ms)

    async def pilot_work(pilot):
        nonlocal terminal_bytes
        original_write = app._driver.write
        def measured_write(data):
            nonlocal terminal_bytes
            terminal_bytes += len(data.encode("utf-8")) if isinstance(data, str) else len(data)
            return original_write(data)
        app._driver.write = measured_write
        # Idle CPU has no high-frequency sampler. UI responsiveness runs do.
        beat = asyncio.create_task(heartbeat()) if args.mode != "idle" else None
        try:
            app._set_debug_events_enabled(args.diagnostics)
            await asyncio.sleep(.8)
            if args.mode == "idle":
                async def idle():
                    await asyncio.sleep(5)
                await measure("idle_5s", idle)
                app.query_input.focus()
                await asyncio.sleep(.3)
                await measure("editor_idle_5s", idle)
            elif args.mode == "completion":
                from sqlit.domains.connections.providers.adapters.base import RoutineInfo
                for count in [1000,5000]:
                    app._schema_cache = {"tables":[],"columns":{},"procedures":[
                        RoutineInfo(f"proc_{i:05d}",schema="dbo",database="lab") for i in range(count)]}
                    async def complete():
                        sql="EXEC proc_"
                        values=app._get_autocomplete_suggestions(sql,len(sql))
                        assert len(values)==min(count,50) and "proc_00000" in values
                        app._show_autocomplete(values,"proc_")
                        return {"routines":count,"suggestions":len(values)}
                    await measure(f"autocomplete_{count}_routines",complete)
                    app._hide_autocomplete()
            else:
                for count, width, kind in [(1000,6,"normal"), (10000,6,"normal"),
                                           (50000,6,"normal"), (5000,40,"wide"),
                                           (1000,3,"long"), (10000,6,"decimal")]:
                    if args.workload and args.workload != f"render_{count}_{width}_{kind}":
                        continue
                    columns = [f"column_{i}" for i in range(width)]
                    if kind == "decimal":
                        rows = [(i, Decimal(f"{i}.12345"), *[f"value-{i}-{j}" for j in range(width-2)]) for i in range(count)]
                    else:
                        length = 10000 if kind == "long" else 24
                        rows = [(i, *[f"value-{i}-{j}:"+"x"*length for j in range(width-1)]) for i in range(count)]

                    async def render():
                        render_start = time.perf_counter()
                        if args.variant in {"bulk", "row-backend"}:
                            app._last_result_columns = columns
                            app._last_result_rows = rows
                            app._last_result_row_count = count
                            if args.variant == "row-backend":
                                from row_backend import RowBackend
                                app._cancel_results_render()
                                table = app._build_results_table(columns,[],escape=True,backend=RowBackend(rows,columns))
                                app._replace_results_table_with_table(table)
                            else:
                                app._replace_results_table(columns, rows)
                        else:
                            await app._display_query_results(columns, rows, count, False, 0)
                        await refresh()
                        first_ms = (time.perf_counter()-render_start)*1000
                        deadline = time.perf_counter()+60
                        while app.results_table.row_count != min(count, 50000):
                            if time.perf_counter() > deadline:
                                raise TimeoutError(f"Rows {app.results_table.row_count}/{count}")
                            await asyncio.sleep(.01)
                        assert len(app._last_result_rows) == count
                        assert app.results_table.get_cell_at(__import__("textual.coordinate", fromlist=["Coordinate"]).Coordinate(0,0)) == 0
                        from textual.coordinate import Coordinate
                        for row_index in [0,count//2,count-1]:
                            assert app.results_table.get_cell_at(Coordinate(row_index,1)) == rows[row_index][1]
                        return {"first_result_refresh_ms":first_ms, "rows":count, "columns":width}
                    await measure(f"render_{count}_{width}_{kind}", render)
                    if kind == "normal" and count == 10000:
                        app.results_table.focus()
                        async def scroll():
                            for i in range(30):
                                app.results_table.move_cursor(row=i*10, column=0)
                                await refresh()
                            return {"actions":30}
                        await measure("scroll_30", scroll)
                        async def filter_open():
                            app.action_results_filter()
                        await measure("filter_open_10000", filter_open)
                        async def filter_apply():
                            app._results_filter_text = "value-999"
                            app._update_results_filter()
                            assert len(app._results_filter_matching_rows) == 11
                        await measure("filter_search_10000", filter_apply)
                        async def filter_close():
                            app.action_results_filter_close()
                        await measure("filter_close_10000", filter_close)
                async def stall_control():
                    time.sleep(.12)
                    await asyncio.sleep(.1)
                if args.diagnostics:
                    await measure("injected_120ms_stall_control", stall_control)
        finally:
            if beat:
                beat.cancel()
            output.write_text(json.dumps(records, indent=2))
            for t, delay in gaps:
                trace.append({"name":"event_loop_delay_ms", "ph":"C", "pid":1,"tid":2,
                              "ts":(t-start)*1e6,"args":{"delay_ms":delay}})
            output.with_suffix(".trace.json").write_text(json.dumps({"traceEvents":trace}))
            if profile:
                profile.dump_stats(str(output.with_suffix(".pstats")))
            app.exit()

    if args.headless:
        async def run_headless():
            async with app.run_test(size=(120,40)) as pilot:
                await pilot_work(pilot)
        asyncio.run(run_headless())
    else:
        app.run(auto_pilot=pilot_work, size=(120,40))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", required=True)
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--mode", choices=["startup", "ui", "idle", "completion"], default="startup")
    parser.add_argument("--variant", choices=["stock", "bulk", "chunk1000", "chunk2000", "widthcache", "preview-thread", "idle-demand", "no-blink", "timer200", "timer500", "row-backend", "clipcells"], default="stock")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--imports", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--workload")
    parser.add_argument("--worker-default", action="store_true")
    parser.add_argument("--no-bytecode-cache", action="store_true")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    child(args) if args.child else controller(args)


if __name__ == "__main__":
    main()
