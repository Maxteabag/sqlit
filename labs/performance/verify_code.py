#!/usr/bin/env python3
"""Run isolated regression or compatibility lanes and retain code provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--output", required=True, help="Output prefix for .log, .xml and .meta.json")
    parser.add_argument("--compatibility", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    def git(*argv):
        return subprocess.check_output(["git", *argv], cwd=repo, text=True).strip()
    if git("diff", "HEAD", "--", "sqlit", "tests"):
        raise RuntimeError("Commit the source and regression tests before recording a verification lane")
    source_sha, code_tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD:sqlit")
    paths = ["tests/unit", "tests/ui", "tests/cli", "tests/test_sqlite.py", "tests/test_duckdb.py"]
    if args.compatibility:
        paths = [
            "tests/unit/test_completion_scaling.py", "tests/unit/test_mssql_routine_completion.py", "tests/unit/sql_completion",
            "tests/unit/test_autocomplete_multidb.py", "tests/unit/test_autocomplete_alias_multi_db.py", "tests/unit/test_autocomplete_cr_line_endings.py",
            "tests/unit/test_autocomplete_cursor_positions.py", "tests/unit/test_idle_scheduler_demand.py", "tests/unit/test_cli_prewarm.py",
            "tests/unit/test_project_dir_routing.py", "tests/cli/test_cli_main.py", "tests/unit/test_table_display_bounds.py",
            "tests/ui/test_results_incremental_rendering.py", "tests/unit/test_incremental_rendering_numeric_range.py",
        ]
    command = [args.python, "-m", "pytest", *paths, "--timeout=45", "-q", "--tb=short", f"--junitxml={output}.xml"]
    if args.dry_run:
        print(json.dumps({"source_sha": source_sha, "code_tree": code_tree, "command": command}))
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sqlit-regression-") as temp:
        env = os.environ.copy()
        env.update(PYTHONPATH=str(repo), SQLIT_CONFIG_DIR=temp, TMPDIR=temp,
                   SQLIT_SKIP_KEYRING_PROBE="1", PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
        with Path(f"{output}.log").open("w") as log:
            result = subprocess.run(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
    if git("rev-parse", "HEAD:sqlit") != code_tree or git("diff", "HEAD", "--", "sqlit", "tests"):
        raise RuntimeError("Code changed during verification")
    metadata = {"source_sha": source_sha, "code_tree": code_tree, "command": command, "exit_code": result.returncode,
                "junit_sha256": hashlib.sha256(Path(f"{output}.xml").read_bytes()).hexdigest()}
    Path(f"{output}.meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
