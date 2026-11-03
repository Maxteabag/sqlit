#!/usr/bin/env python3
"""Normalize observations and compute descriptive, reproducible bootstrap CIs."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import random
import statistics
from pathlib import Path


def quantile(values, fraction):
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * fraction
    left = math.floor(index)
    right = math.ceil(index)
    return ordered[left] + (ordered[right] - ordered[left]) * (index - left)


def describe(values):
    values = list(values)
    rng = random.Random(43319)
    draws = [statistics.median(rng.choices(values, k=len(values))) for _ in range(2000)]
    return {
        "n": len(values),
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "min": min(values),
        "max": max(values),
        "p95": quantile(values, 0.95),
        "q25": quantile(values, 0.25),
        "q75": quantile(values, 0.75),
        "sd": statistics.stdev(values) if len(values) > 1 else 0,
        "median_ci95": [quantile(draws, 0.025), quantile(draws, 0.975)],
    }


def load_records(root):
    records = []
    for path in sorted(root.glob("startup-*/*/run-000/result.json")):
        raw = json.loads(path.read_text())
        records.append(
            {
                "suite": "startup",
                "scenario": path.parents[2].name.removeprefix("startup-"),
                "variant": raw["label"],
                "trial": int(path.parents[1].name.split("-")[0]),
                "source_sha": raw["sha"],
                **{k: raw[k] for k in ["parent_ready_ms", "cli_first_refresh_ms", "process_cpu_ms", "pty_bytes"]},
            }
        )
    for suite in ["completion", "render", "idle", "long-cells"]:
        for path in sorted((root / suite).glob("*/run-000/result.json")):
            raw = json.loads(path.read_text())
            variant = raw["label"] if raw["variant"] == "stock" else raw["variant"]
            for item in raw["workloads"]:
                delays = item["loop_delays_ms"]
                records.append(
                    {
                        "suite": suite,
                        "scenario": item["name"],
                        "variant": variant,
                        "trial": int(path.parents[1].name.split("-")[0]),
                        "source_sha": raw["sha"],
                        **{k: v for k, v in item.items() if k != "name"},
                        "max_loop_delay_ms": max(delays, default=0),
                        "p95_loop_delay_ms": quantile(delays, 0.95) if delays else 0,
                        "loop_delays_over_16_7_ms": sum(x > 16.7 for x in delays),
                        "loop_delays_over_50_ms": sum(x > 50 for x in delays),
                        "one_core_cpu_percent": 100 * item["cpu_ms"] / item["wall_ms"],
                    }
                )
    for variant in ["baseline", "candidate"]:
        path = root / f"cpu-{variant}.json"
        if path.exists():
            for item in json.loads(path.read_text()):
                records.append({"suite": "cpu", "variant": variant, "trial": item["iteration"], **item})
    for path in sorted(root.glob("network-*.json")):
        raw = json.loads(path.read_text())
        for item in raw["records"]:
            records.append({"suite": "network", "variant": "baseline", "trial": item["iteration"], "image": raw["metadata"]["image"], "image_id": raw["metadata"]["image_id"], **item})
    path = root / "local-databases.json"
    if path.exists():
        for item in json.loads(path.read_text()):
            records.append({"suite": "ipc" if item["provider"] == "ipc" else "local", "variant": "baseline", "trial": item["iteration"], **item})
    return records


DIMENSIONS = ["suite", "scenario", "variant", "provider", "one_way_delay_ms", "objects", "pattern"]
METRICS = [
    "wall_ms",
    "cpu_ms",
    "parent_cpu_ms",
    "client_cpu_ms",
    "parent_ready_ms",
    "cli_first_refresh_ms",
    "process_cpu_ms",
    "pty_bytes",
    "terminal_bytes",
    "frames",
    "first_result_refresh_ms",
    "max_loop_delay_ms",
    "p95_loop_delay_ms",
    "loop_delays_over_16_7_ms",
    "loop_delays_over_50_ms",
    "one_core_cpu_percent",
    "maxrss_kib",
    "rx_bytes",
    "tx_bytes",
    "first_fetch_ms",
    "first_fetch_rx_bytes",
    "worker_reported_ms",
    "bytes",
]


def summarize(records):
    # Timings are useful only when the observed completion output is unchanged.
    for count in {r.get("objects") for r in records if r["suite"] == "cpu"}:
        for scenario in {r["scenario"] for r in records if r["suite"] == "cpu"}:
            outputs = {variant: {r["digest"] for r in records if r["suite"] == "cpu" and r["variant"] == variant and r.get("objects") == count and r["scenario"] == scenario} for variant in ["baseline", "candidate"]}
            if outputs["baseline"] and outputs["candidate"] and outputs["baseline"] != outputs["candidate"]:
                raise AssertionError(f"Completion output changed: {count}, {scenario}")
    groups = {}
    for record in records:
        key = tuple(record.get(k) for k in DIMENSIONS)
        groups.setdefault(key, []).append(record)
    summaries = []
    for key, rows in groups.items():
        summary = {k: v for k, v in zip(DIMENSIONS, key) if v is not None}
        summary["metrics"] = {metric: describe(row[metric] for row in rows if row.get(metric) is not None) for metric in METRICS if any(row.get(metric) is not None for row in rows)}
        summaries.append(summary)
    return summaries


def select(records, **criteria):
    return [r for r in records if all(r.get(k) == v for k, v in criteria.items())]


def comparison(records, name, before, after, metric, paired=True):
    a = select(records, **before)
    b = select(records, **after)
    if not a or not b:
        return None
    xs, ys = [r[metric] for r in a], [r[metric] for r in b]
    am, bm = statistics.median(xs), statistics.median(ys)
    pairs = []
    if paired:
        left = {r["trial"]: r[metric] for r in a}
        right = {r["trial"]: r[metric] for r in b}
        pairs = [(left[t], right[t]) for t in sorted(left.keys() & right.keys())]
        paired = len(pairs) == len(a) == len(b)
    rng = random.Random(12479)
    reductions = []
    differences = []
    for _ in range(5000):
        if paired:
            draw = rng.choices(pairs, k=len(pairs))
            ax = statistics.median(x for x, y in draw)
            by = statistics.median(y for x, y in draw)
        else:
            ax = statistics.median(rng.choices(xs, k=len(xs)))
            by = statistics.median(rng.choices(ys, k=len(ys)))
        differences.append(ax - by)
        reductions.append(100 * (ax - by) / ax if ax else 0)
    return {
        "name": name,
        "before": before,
        "after": after,
        "metric": metric,
        "n_before": len(a),
        "n_after": len(b),
        "paired_bootstrap": paired,
        "before_median": am,
        "after_median": bm,
        "saved": am - bm,
        "reduction_percent": 100 * (am - bm) / am if am else 0,
        "saved_ci95": [quantile(differences, 0.025), quantile(differences, 0.975)],
        "reduction_ci95": [quantile(reductions, 0.025), quantile(reductions, 0.975)],
    }


def build_comparisons(records):
    results = []

    def add(name, suite, scenario, metric, **extra):
        common = {"suite": suite, "scenario": scenario, **extra}
        result = comparison(records, name, {**common, "variant": "baseline"}, {**common, "variant": "candidate"}, metric, paired=suite != "cpu")
        if result:
            results.append(result)

    for n in [1000, 5000]:
        add(f"completion-ui-{n}", "completion", f"autocomplete_{n}_routines", "wall_ms")
        add(f"completion-ui-cpu-{n}", "completion", f"autocomplete_{n}_routines", "cpu_ms")
    for condition in ["disabled", "default"]:
        add(f"startup-ready-{condition}", "startup", condition, "parent_ready_ms")
        add(f"startup-cpu-{condition}", "startup", condition, "process_cpu_ms")
    for scenario in ["idle_5s", "editor_idle_5s"]:
        add(f"idle-{scenario}", "idle", scenario, "cpu_ms")
    add("long-cells-cpu", "long-cells", "render_1000_3_long", "cpu_ms")
    add("long-cells-wall", "long-cells", "render_1000_3_long", "wall_ms")
    add("algorithm-5000", "cpu", "routine_completion", "wall_ms", objects=5000)
    for variant in ["candidate", "bulk", "preview-thread", "timer500", "row-backend"]:
        common = {"suite": "render", "scenario": "render_50000_6_normal"}
        for metric in ["wall_ms", "cpu_ms", "max_loop_delay_ms", "terminal_bytes"]:
            result = comparison(records, f"render50k-{variant}-{metric}", {**common, "variant": "baseline"}, {**common, "variant": variant}, metric)
            if result:
                results.append(result)
    for provider in ["postgresql", "mysql", "mariadb"]:
        for delay in [0, 20]:
            common = {"suite": "network", "provider": provider, "one_way_delay_ms": delay}
            for before, after, metric, label in [
                ("buffered_cap_1000", "server_limit_1001", "rx_bytes", "bandwidth"),
                ("buffered_cap_1000", "server_limit_1001", "wall_ms", "bounded-query"),
                ("metadata_per_table", "metadata_one_query_per_table", "wall_ms", "metadata-one-query"),
                ("metadata_per_table", "metadata_batch", "wall_ms", "metadata-batch"),
                ("connect_query_close", "reuse_query", "wall_ms", "connection-reuse"),
            ]:
                result = comparison(records, f"{label}-{provider}-{delay}", {**common, "scenario": before}, {**common, "scenario": after}, metric)
                if result:
                    results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.input)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    records = load_records(root)
    summaries = summarize(records)
    comparisons = build_comparisons(records)
    environments = [json.loads(p.read_text()) for p in sorted(root.glob("environment-*.json"))]
    data = {
        "record_count": len(records),
        "summaries": summaries,
        "comparisons": comparisons,
        "environments": environments,
        "method": {
            "median_bootstrap_draws": 2000,
            "effect_bootstrap_draws": 5000,
            "ci": 0.95,
            "tails": "p95 is descriptive; small samples do not establish an SLO",
            "multiplicity": "Exploratory intervals; no adjustment for multiple comparisons",
        },
    }
    (output / "data.json").write_text(json.dumps(data, separators=(",", ":")) + "\n")
    scalar_keys = sorted({k for record in records for k, v in record.items() if not isinstance(v, (list, dict))})
    with (output / "measurements.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=scalar_keys, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({k: v for k, v in record.items() if k in scalar_keys})
    raw = output / "raw"
    raw.mkdir(exist_ok=True)
    manifest = []
    for index in range(0, len(records), 60):
        name = f"observations-{index // 60:03d}.json.gz"
        payload = gzip.compress(json.dumps(records[index : index + 60], separators=(",", ":")).encode(), mtime=0)
        (raw / name).write_bytes(payload)
        manifest.append({"file": name, "records": len(records[index : index + 60]), "sha256": hashlib.sha256(payload).hexdigest()})
    (raw / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{len(records)} observations, {len(summaries)} groups, {len(comparisons)} comparisons")
    for result in comparisons:
        if result["name"].startswith(("completion-ui", "startup", "idle", "long-cells", "algorithm")):
            print(result["name"], round(result["before_median"], 3), "->", round(result["after_median"], 3), f"{result['reduction_percent']:.1f}%", "CI", *[round(n, 1) for n in result["reduction_ci95"]])


if __name__ == "__main__":
    main()
