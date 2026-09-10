#!/usr/bin/env python3
"""Run the opt-in provider lane; reject skipped/missing provider evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("postgresql", "mssql", "snowflake", "supabase", "sqlite")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    junit = output / "junit.xml"
    with tempfile.TemporaryDirectory(prefix="sqlit-schema-config-") as config:
        env = os.environ.copy()
        env.pop("NO_COLOR", None)
        env.update(SQLIT_SCHEMA_INTEGRATION="1", SQLIT_SCHEMA_PROVIDERS=",".join(PROVIDERS), SQLIT_CONFIG_DIR=config, SQLIT_SCHEMA_CAPTURE_DIR=str(output / "screenshots"))
        command = [sys.executable, "-m", "pytest", "tests/integration/schema_hierarchy", "-q", "--tb=short", "--timeout=180", "--junitxml=" + str(junit)]
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (output / "pytest.log").write_text(result.stdout)
        print(result.stdout)
    if not junit.exists():
        raise SystemExit(result.returncode or "No JUnit results produced")
    cases = ET.parse(junit).findall(".//testcase")  # noqa: S314 - generated locally by pytest above
    summary = {"tests": len(cases), "failures": sum(c.find("failure") is not None for c in cases), "errors": sum(c.find("error") is not None for c in cases), "skips": sum(c.find("skipped") is not None for c in cases)}
    names = [case.attrib["name"] for case in cases if "test_provider_contract" in case.attrib.get("classname", "")]
    counts = {provider: sum("[" + provider + "]" in name or "[" + provider + "-" in name for name in names) for provider in PROVIDERS}
    summary["provider_tests"] = counts
    summary["registry_contract_tests"] = sum("test_registry_fallback" in c.attrib.get("classname", "") for c in cases)
    summary["head"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    summary["evidence"] = {
        "postgresql": "live PostgreSQL 16 container",
        "mssql": "live SQL Server 2022 container",
        "snowflake": "fakesnow emulation; not live Snowflake",
        "supabase": "real adapter with local PostgreSQL transport; not live Supabase",
        "sqlite": "local SQLite file",
    }
    (output / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    screenshots = output / "screenshots"
    screenshots.mkdir(exist_ok=True)
    (screenshots / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    missing = [p for p in PROVIDERS if counts[p] < 5 or not (screenshots / f"{p}.svg").exists()]
    if result.returncode or summary["failures"] or summary["errors"] or summary["skips"] or missing:
        raise SystemExit(f"Provider lane incomplete: returncode={result.returncode}, missing={missing}, results={summary}")


if __name__ == "__main__":
    main()
