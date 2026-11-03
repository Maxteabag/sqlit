#!/usr/bin/env python3
"""Attach regression counts and selected diagnostic recordings to the paper."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


def passed_in(path):
    match = re.search(r"(\d+) passed", path.read_text())
    return int(match.group(1)) if match else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root, out = Path(args.evidence), Path(args.output)
    diag = out / "diagnostics"
    diag.mkdir(exist_ok=True)
    tree = ET.parse(root / "regression-candidate.xml").getroot()
    suites = list(tree.iter("testsuite"))
    total = sum(int(s.attrib["tests"]) for s in suites)
    skipped = sum(int(s.attrib["skipped"]) for s in suites)
    failed = sum(int(s.attrib["failures"]) for s in suites)
    errors = sum(int(s.attrib["errors"]) for s in suites)
    data = json.loads((out / "data.json").read_text())
    validation = {
        "source_sha": data["environments"][0]["source_commits"]["candidate"],
        "suite": "tests/unit tests/ui tests/cli tests/test_sqlite.py tests/test_duckdb.py",
        "passed": total - skipped - failed - errors,
        "skipped": skipped,
        "failed": failed,
        "errors": errors,
        "duration_s": sum(float(s.attrib["time"]) for s in suites),
        "skip_reasons": dict(Counter(x.attrib.get("message", "") for x in tree.iter("skipped"))),
        "formal_study_jobs": len(list((root / "study" / "receipts").glob("*.json"))),
        "formal_observations": data["record_count"],
        "focused_completion_tests": passed_in(root / "completion-green.txt"),
        "focused_scheduler_startup_tests": passed_in(root / "idle-startup-tests.txt"),
        "focused_display_tests": passed_in(root / "display-tests.txt"),
        "release_state": "Measured source branch; no release or deployment performed",
    }
    if failed or errors:
        raise RuntimeError("Resolve or explicitly document regression failures before publishing the report")
    if (root / "regression-python310.xml").exists():
        compatible = ET.parse(root / "regression-python310.xml").getroot()
        compatible_suites = list(compatible.iter("testsuite"))
        ct = sum(int(s.attrib["tests"]) for s in compatible_suites)
        cs = sum(int(s.attrib["skipped"]) for s in compatible_suites)
        cf = sum(int(s.attrib["failures"]) + int(s.attrib["errors"]) for s in compatible_suites)
        validation["python310"] = {"passed": ct - cs - cf, "skipped": cs, "failed": cf}
        if cf:
            raise RuntimeError("Compatibility lane has failures")
    (out / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    examples = {}
    for name in ["baseline", "candidate"]:
        path = root / f"probe-completion-ui-{name}" / "run-000" / "ui.trace.json"
        raw = json.loads(path.read_text())
        examples[name] = {
            "spans": [[round(e["ts"], 2), round(e["dur"], 2), e["name"]] for e in raw["traceEvents"] if e["ph"] == "X"],
            "delays": [[round(e["ts"], 2), round(e["args"]["delay_ms"], 4)] for e in raw["traceEvents"] if e["ph"] == "C"],
        }
        (diag / f"completion-{name}.trace.json").write_text(path.read_text().rstrip() + "\n")
    examples["note"] = "Dedicated diagnostics-enabled pilots; separate from formal low-overhead trials."
    (out / "trace-examples.json").write_text(json.dumps(examples, separators=(",", ":")) + "\n")
    files = [
        root / "completion-baseline.speedscope.json",
        root / "probe-ui" / "run-000" / "ui.pstats",
        root / "probe-ui" / "run-000" / "ui.watchdog.txt",
        root / "probe-ui" / "run-000" / "ui.debug.jsonl",
        root / "probe-startup" / "run-000" / "imports.txt",
        root / "probe-startup" / "run-000" / "startup.txt",
        root / "regression-candidate.xml",
        root / "regression-candidate.log",
        root / "completion-red.txt",
        root / "completion-green.txt",
        root / "idle-startup-tests.txt",
        root / "display-tests.txt",
    ]
    files.extend(p for p in [root / "regression-python310.xml", root / "regression-python310.log"] if p.exists())
    if (root / "cells-visual" / "artifact.png").exists():
        shutil.copy2(root / "cells-visual" / "artifact.png", diag / "cells.png")
    with zipfile.ZipFile(diag / "diagnostics.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in files:
            archive.write(file, arcname=str(file.relative_to(root)))
    checks = [{"file": str(p.relative_to(out)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in sorted(diag.iterdir()) if p.name != "manifest.json"]
    (diag / "manifest.json").write_text(json.dumps(checks, indent=2) + "\n")
    environment = data["environments"][0]
    lab_snapshot = None
    revisions = subprocess.check_output(["git", "log", "--format=%H", "--", "labs/performance/run.py"], text=True).splitlines()
    for revision in revisions:
        matches = True
        for name, expected in environment["lab_files_sha256"].items():
            candidate = subprocess.run(["git", "show", f"{revision}:labs/performance/{name}"], capture_output=True)
            if candidate.returncode or hashlib.sha256(candidate.stdout).hexdigest() != expected:
                matches = False
                break
        if matches:
            lab_snapshot = revision
            break
    if lab_snapshot is None:
        raise RuntimeError("Commit a snapshot matching the measured lab files before exporting provenance")
    provenance = {
        "baseline_source": environment["source_commits"]["baseline"],
        "measured_candidate_source": environment["source_commits"]["candidate"],
        "measured_lab_snapshot": lab_snapshot,
        "measurement_file_hashes_verified_against_git": True,
        "csv_sha256": hashlib.sha256((out / "measurements.csv").read_bytes()).hexdigest(),
    }
    if (root / "lint-baseline.json").exists() and (root / "lint-candidate.json").exists():
        base = json.loads((root / "lint-baseline.json").read_text())
        current = json.loads((root / "lint-candidate.json").read_text())
        introduced = Counter((r["code"], r["message"]) for r in current) - Counter((r["code"], r["message"]) for r in base)
        provenance.update(baseline_cli_lint_findings=len(base), candidate_cli_lint_findings=len(current), introduced_cli_lint_findings=sum(introduced.values()))
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Attached {validation['passed']} passes, {skipped} skips and {len(checks)} diagnostic files")


if __name__ == "__main__":
    main()
