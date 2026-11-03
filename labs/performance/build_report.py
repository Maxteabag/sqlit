#!/usr/bin/env python3
"""Build a standalone scientific HTML report and exportable SVG figures."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BLUE = "#245570"
GREEN = "#28725e"
ORANGE = "#b15f34"
GRAY = "#707678"
COLORS = {"baseline": BLUE, "candidate": GREEN, "bulk": ORANGE, "preview-thread": "#9e7040", "timer500": "#82718d", "row-backend": "#34494b"}
LABELS = {"baseline": "Baseline", "candidate": "Implemented changes", "bulk": "Bulk, UI thread", "preview-thread": "Preview + thread", "timer500": "500 rows / timer", "row-backend": "Sampled row backend"}


def fmt(value, decimals=1):
    if abs(value) < 0.1 and value:
        return f"{value:.3f}"
    return f"{value:,.{decimals}f}"


class Report:
    def __init__(self, data, output):
        self.data = data
        self.output = output
        self.figures = {}
        self.comparisons = {c["name"]: c for c in data["comparisons"]}
        plt.rcParams.update(
            {
                "font.family": "DejaVu Sans",
                "font.size": 10,
                "axes.titlesize": 12,
                "axes.labelsize": 10,
                "axes.spines.top": False,
                "axes.spines.right": False,
                "axes.edgecolor": "#b2b5b4",
                "axes.labelcolor": "#222b30",
                "text.color": "#222b30",
                "xtick.color": "#465159",
                "ytick.color": "#465159",
                "figure.facecolor": "white",
                "axes.facecolor": "white",
                "svg.fonttype": "none",
                "svg.hashsalt": "sqlit-performance-study",
                "savefig.bbox": "tight",
                "grid.color": "#dde1e1",
                "grid.linewidth": 0.6,
            }
        )

    def group(self, **criteria):
        values = [s for s in self.data["summaries"] if all(s.get(k) == v for k, v in criteria.items())]
        if len(values) != 1:
            raise ValueError((criteria, len(values)))
        return values[0]

    def stat(self, metric, **criteria):
        return self.group(**criteria)["metrics"][metric]

    def save(self, name, figure, caption):
        path = self.output / "figures" / f"{name}.svg"
        path.parent.mkdir(exist_ok=True)
        figure.savefig(path, metadata={"Date": None, "Creator": "sqlit performance laboratory"})
        plt.close(figure)
        svg = "\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n"
        path.write_text(svg)
        svg = svg[svg.index("<svg") :]
        ids = re.findall(r'id="([^"]+)"', svg)
        for ident in sorted(ids, key=len, reverse=True):
            svg = svg.replace(f'id="{ident}"', f'id="{name}-{ident}"').replace(f"#{ident})", f"#{name}-{ident})").replace(f'href="#{ident}"', f'href="#{name}-{ident}"')
        svg = svg.replace("<svg ", f'<svg role="img" aria-label="{html.escape(caption)}" ', 1)
        self.figures[name] = f'<figure id="fig-{name}">{svg}<figcaption>{caption} <a href="figures/{name}.svg" download>Download SVG</a></figcaption></figure>'

    def bars(self, axis, labels, stats, colors=None, horizontal=False, unit=1):
        x = np.arange(len(labels))
        med = np.array([s["median"] / unit for s in stats])
        error = np.array([[s["median"] - s["median_ci95"][0] for s in stats], [s["median_ci95"][1] - s["median"] for s in stats]]) / unit
        if horizontal:
            axis.barh(x, med, color=colors or BLUE, height=0.6, xerr=error, error_kw={"capsize": 3, "elinewidth": 1, "ecolor": "#283339"})
            axis.set_yticks(x, labels)
            axis.invert_yaxis()
            axis.grid(axis="x")
        else:
            axis.bar(x, med, color=colors or BLUE, width=0.6, yerr=error, error_kw={"capsize": 3, "elinewidth": 1, "ecolor": "#283339"})
            axis.set_xticks(x, labels)
            axis.grid(axis="y")
        axis.set_axisbelow(True)

    def plots(self):
        fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.9), layout="constrained")
        sizes = [100, 1000, 5000]
        for variant in ["baseline", "candidate"]:
            stats = [self.stat("wall_ms", suite="cpu", scenario="routine_completion", objects=n, variant=variant) for n in sizes]
            med = [s["median"] for s in stats]
            axes[0].plot(sizes, med, "o-", color=COLORS[variant], label=LABELS[variant], lw=2)
            axes[0].fill_between(sizes, [s["median_ci95"][0] for s in stats], [s["median_ci95"][1] for s in stats], color=COLORS[variant], alpha=0.12)
        axes[0].set(xscale="log", yscale="log", xlabel="Stored routines", ylabel="Completion function (ms)", title="Algorithm scaling; n = 9 per size")
        axes[0].set_xticks(sizes, [str(n) for n in sizes])
        axes[0].grid(which="major")
        axes[0].legend(frameon=False)
        stats = [self.stat("wall_ms", suite="completion", scenario="autocomplete_5000_routines", variant=v) for v in ["baseline", "candidate"]]
        self.bars(axes[1], ["Baseline", "Implemented"], stats, [BLUE, GREEN])
        axes[1].set(ylabel="App completion + dropdown refresh (ms)", title="Actual PTY app; 5,000 routines; n = 9")
        for i, s in enumerate(stats):
            axes[1].text(i, s["median"] + 45, f"{fmt(s['median'])} ms", ha="center")
        self.save(
            "completion",
            fig,
            "Figure 1. Catalog scaling and the actual app completion path. Shading and error bars show 95% bootstrap intervals for the median. Input transport and the existing 100 ms debounce are outside this timing boundary.",
        )

        fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.1), layout="constrained")
        labels = ["Default\nbaseline", "Default\nimplemented", "Disabled\nbaseline", "Disabled\nimplemented", "Empty .pyc\nimplemented"]
        criteria = [("default", "baseline"), ("default", "candidate"), ("disabled", "baseline"), ("disabled", "candidate"), ("no-pyc", "candidate")]
        stats = [self.stat("parent_ready_ms", suite="startup", scenario=s, variant=v) for s, v in criteria]
        self.bars(axes[0], labels, stats, [BLUE, GREEN, BLUE, GREEN, GRAY])
        axes[0].set(ylabel="Launch to observed first refresh (ms)", title="Cold processes; warm filesystem cache")
        cpu = [self.stat("process_cpu_ms", suite="startup", scenario=s, variant=v) for s, v in criteria[:4]]
        self.bars(axes[1], labels[:4], cpu, [BLUE, GREEN, BLUE, GREEN])
        axes[1].set(ylabel="Launch-and-exit process CPU (ms)", title="Respecting the disabled-worker setting")
        self.save(
            "startup",
            fig,
            "Figure 2. Startup wall time and consumed CPU. Normal conditions have 15 trials per source; empty bytecode has seven. "
            "Native timing still runs in these trials. CPU covers the first-refresh-and-exit process lifecycle, including reaped child work.",
        )

        fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.5), layout="constrained")
        for ax, scenario, title in zip(axes, ["idle_5s", "editor_idle_5s"], ["Explorer focus", "Editor focus; cursor blinking retained"]):
            stats = [self.stat("cpu_ms", suite="idle", scenario=scenario, variant=v) for v in ["baseline", "candidate"]]
            self.bars(ax, ["Baseline", "Implemented"], stats, [BLUE, GREEN])
            ax.set(ylabel="Process CPU over 5 seconds (ms)", title=title)
            for i, s in enumerate(stats):
                ax.text(i, s["median"] + 2, f"{fmt(s['median'])} ms", ha="center")
            ax.set_ylim(0, 60)
        self.save("idle", fig, "Figure 3. Empty-queue polling costs measurable CPU even when the UI is still. Nine trials per condition, no 5 ms heartbeat during idle windows. The requested final refresh is included in both versions.")

        fig, ax = plt.subplots(figsize=(10.8, 4.6), layout="constrained")
        for v in LABELS:
            x = self.stat("wall_ms", suite="render", scenario="render_50000_6_normal", variant=v)
            y = self.stat("max_loop_delay_ms", suite="render", scenario="render_50000_6_normal", variant=v)
            cpu = self.stat("cpu_ms", suite="render", scenario="render_50000_6_normal", variant=v)["median"]
            ax.errorbar(x["median"], y["median"], xerr=[[x["median"] - x["median_ci95"][0]], [x["median_ci95"][1] - x["median"]]], fmt="none", color=COLORS[v], capsize=3, alpha=0.7)
            ax.scatter(x["median"], y["median"], s=40 + cpu * 0.3, color=COLORS[v], label=f"{LABELS[v]} ({cpu:.0f} CPU ms)")
        ax.axhline(16.7, color="#b6b8b8", linestyle="--", lw=1)
        ax.text(160, 17.6, "16.7 ms excess-delay reference", color=GRAY, fontsize=9)
        ax.set(xscale="log", xlabel="Time until all 50,000 rows are available (ms)", ylabel="Median of per-trial maximum loop lateness (ms)", title="Rendering trade-offs; 50,000 × 6 cells; n = 5")
        ax.grid(axis="both", alpha=0.5)
        ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=9)
        self.save(
            "render-tradeoffs",
            fig,
            "Figure 4. Faster completion can create worse stutter. Marker area scales with CPU, and horizontal error bars show median time uncertainty. "
            "Lateness is excess beyond a 5 ms sleep; the dashed line is a diagnostic reference, not proof of physical 60 FPS.",
        )

        fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.8), layout="constrained")
        variants = ["baseline", "candidate", "bulk", "preview-thread", "timer500", "row-backend"]
        stats = [self.stat("terminal_bytes", suite="render", scenario="render_50000_6_normal", variant=v) for v in variants]
        self.bars(axes[0], [LABELS[v] for v in variants], stats, [COLORS[v] for v in variants], horizontal=True, unit=1000)
        axes[0].set(xlabel="Terminal payload (kB, decimal)", title="Result-loading output volume")
        stats = [self.stat("maxrss_kib", suite="render", scenario="render_50000_6_normal", variant=v) for v in variants]
        self.bars(axes[1], [LABELS[v] for v in variants], stats, [COLORS[v] for v in variants], horizontal=True, unit=1024)
        axes[1].set(xlabel="Process high-water RSS (MiB)", title="Memory by this point in the fixed sequence")
        self.save(
            "render-resources",
            fig,
            "Figure 5. Terminal bytes and cumulative peak RSS at the 50,000-row workload. RSS includes imports and earlier workloads; "
            "it is not an allocation measurement for this query. The sampled backend still runs inside the existing Arrow-dependent application.",
        )

        fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.5), layout="constrained")
        for axis, metric, title in zip(axes, ["cpu_ms", "wall_ms"], ["Consumed CPU", "Full result availability"]):
            stats = [self.stat(metric, suite="long-cells", scenario="render_1000_3_long", variant=v) for v in ["baseline", "candidate"]]
            self.bars(axis, ["Baseline", "Implemented"], stats, [BLUE, GREEN])
            axis.set(ylabel="Milliseconds", title=title)
        self.save(
            "long-cells",
            fig,
            "Figure 6. Isolated long-cell workload: 1,000 rows, three columns, 10,000-character text, five fresh processes per source. The wide uncertainty prevents a reliable end-to-end speedup claim for the clipping change.",
        )

        fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.0), layout="constrained")
        providers = ["postgresql", "mysql", "mariadb"]
        names = ["PostgreSQL", "MySQL", "MariaDB"]
        scenarios = ["buffered_cap_1000", "server_limit_1001", "stream_fetch_cleanup"]
        colors = [BLUE, GREEN, ORANGE]
        legend = ["Buffered cap: 1,000", "Explicit LIMIT 1,001", "Streaming + cleanup"]
        x = np.arange(3)
        for i, (scenario, color, label) in enumerate(zip(scenarios, colors, legend)):
            groups = [self.group(suite="network", scenario=scenario, provider=p, one_way_delay_ms=20) for p in providers]
            axes[0].bar(x + (i - 1) * 0.24, [g["metrics"]["rx_bytes"]["median"] / 1e6 for g in groups], width=0.22, color=color, label=label)
            axes[1].bar(x + (i - 1) * 0.24, [g["metrics"]["wall_ms"]["median"] for g in groups], width=0.22, color=color, label=label)
        for ax in axes:
            ax.set_xticks(x, names)
            ax.set_axisbelow(True)
            ax.grid(axis="y")
        axes[0].set(ylabel="Received protocol payload (MB, decimal)", title="A Python row cap is not a network cap")
        axes[1].set(ylabel="Operation wall time (ms)", title="40 ms injected round-trip latency")
        axes[0].legend(frameon=False, fontsize=8)
        self.save(
            "network-limits",
            fig,
            "Figure 7. All bounded result variants verify rows 1–1,000 and truncation. Streaming includes cursor cleanup and a subsequent SELECT 1. "
            "PostgreSQL named cursors avoid full transfer; MySQL/MariaDB SSCursor cleanup still consumes the remaining result. Nine trials per condition.",
        )

        fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.1), layout="constrained")
        x = np.arange(3)
        for i, (scenario, label, color) in enumerate(zip(["metadata_per_table", "metadata_one_query_per_table", "metadata_batch"], ["Two queries / table", "One query / table", "One batch / 20 tables"], [BLUE, ORANGE, GREEN])):
            for ax, delay in zip(axes, [0, 20]):
                values = [self.stat("wall_ms", suite="network", scenario=scenario, provider=p, one_way_delay_ms=delay)["median"] for p in providers]
                ax.bar(x + (i - 1) * 0.24, values, width=0.22, label=label, color=color)
        for ax, title in zip(axes, ["Loopback relay, no added delay", "40 ms injected round-trip latency"]):
            ax.set_xticks(x, names)
            ax.set(ylabel="20-table metadata time (ms)", title=title)
            ax.grid(axis="y")
            ax.set_axisbelow(True)
        axes[0].legend(frameon=False, fontsize=8)
        self.save(
            "network-metadata",
            fig,
            "Figure 8. Reducing metadata round trips dominates at latency. Every strategy returns the same 80 ordered columns and primary-key flags for 20 owned fixture tables. "
            "These are explicit catalog-scan experiments, not measurements of the default lazy connection flow.",
        )

        fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.8), layout="constrained")
        for i, (scenario, label, color) in enumerate([("connect_query_close", "Fresh connection + query", BLUE), ("reuse_query", "Reused connection + query", GREEN)]):
            for ax, delay in zip(axes, [0, 20]):
                values = [self.stat("wall_ms", suite="network", scenario=scenario, provider=p, one_way_delay_ms=delay)["median"] for p in providers]
                ax.bar(x + (i - 0.5) * 0.3, values, width=0.28, color=color, label=label)
        for ax, title in zip(axes, ["Loopback relay, no added delay", "40 ms injected round-trip latency"]):
            ax.set_xticks(x, names)
            ax.set(ylabel="SELECT 1 operation (ms)", title=title)
            ax.grid(axis="y")
            ax.set_axisbelow(True)
        axes[0].legend(frameon=False, fontsize=8)
        self.save(
            "connection-reuse",
            fig,
            "Figure 9. Measured connection reuse opportunity. These connections use local disposable credentials and no TLS. "
            "The current cancellable query path deliberately creates dedicated connections; safe pooling must preserve cancellation, transaction and session-state boundaries.",
        )

        fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.2), layout="constrained")
        local_scenarios = ["reuse_select1", "connect_select1_close", "cancellable_select1", "worker_warm_select1", "worker_cold_select1"]
        local_labels = ["Reuse", "Connect / query / close", "Cancellable query", "Warm worker", "Cold worker / shutdown"]
        for ax, provider in zip(axes, ["sqlite", "duckdb"]):
            stats = [self.stat("wall_ms", suite="local", scenario=s, provider=provider) for s in local_scenarios]
            self.bars(ax, local_labels, stats, [GREEN, GRAY, BLUE, ORANGE, "#7c5666"], horizontal=True)
            ax.set(xscale="log", xlabel="SELECT 1 operation (ms, log scale)", title=provider)
        self.save(
            "local-workers",
            fig,
            "Figure 10. Embedded database connections and actual process-worker costs; nine trials each. Cold worker includes creation, execution and shutdown. "
            "DuckDB worker runs are forced laboratory comparisons with read-only files; the adapter disables that route in the normal UI.",
        )

        fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.2), layout="constrained")
        ipc_scenarios = ["pickle_roundtrip", "arrow_python_roundtrip", "arrow_none_roundtrip", "arrow_lz4_roundtrip", "arrow_zstd_roundtrip"]
        ipc_labels = ["Pickle: Python → Python", "Arrow: Python → Python", "Arrow: prepared → prepared", "Arrow LZ4: prepared", "Arrow Zstd: prepared"]
        for ax, pattern in zip(axes, ["repeated", "varied"]):
            stats = [self.stat("wall_ms", suite="ipc", scenario=s, pattern=pattern) for s in ipc_scenarios]
            self.bars(ax, ipc_labels, stats, [BLUE, GREEN, GRAY, ORANGE, "#7c5666"], horizontal=True)
            ax.set(xlabel="Serialization + read-back (ms)", title=f"50,000 rows; {pattern} 256-character text")
        self.save(
            "ipc",
            fig,
            "Figure 11. Representation boundaries determine the result. The first two rows include Python-to-Python round trips; "
            "the last three start and end as Arrow tables and exclude conversion. Each decoded result is checked for equality. "
            "Repeated strings are independent objects, avoiding artificial pickle memoization.",
        )

    def comparison_table(self, names):
        rows = []
        for name in names:
            c = self.comparisons[name]
            ci = " to ".join(fmt(x) for x in c["reduction_ci95"])
            signal = "Interval crosses zero" if c["reduction_ci95"][0] <= 0 <= c["reduction_ci95"][1] else "Observed reduction" if c["reduction_percent"] > 0 else "Observed increase"
            before = c["before"]
            after = c["after"]
            metric = c["metric"]
            if before["suite"] == "completion":
                label = f"App completion · {before['scenario'].split('_')[1]} routines"
            elif before["suite"] == "startup":
                label = ("Launch CPU" if metric == "process_cpu_ms" else "First refresh") + " · worker " + before["scenario"]
            elif before["suite"] == "idle":
                label = "Idle CPU · " + ("editor" if before["scenario"].startswith("editor") else "explorer")
            elif before["suite"] == "long-cells":
                label = "Long cells · " + ("CPU" if metric == "cpu_ms" else "availability")
            elif before["suite"] == "render":
                label = LABELS[after["variant"]] + " · " + {"wall_ms": "availability", "cpu_ms": "CPU", "max_loop_delay_ms": "maximum loop lateness", "terminal_bytes": "terminal bytes"}[metric]
            else:
                label = (
                    before.get("provider", "").title()
                    + " · "
                    + {"server_limit_1001": "bounded query", "metadata_one_query_per_table": "one query / table", "metadata_batch": "metadata batch", "reuse_query": "connection reuse"}.get(after["scenario"], after["scenario"])
                )
            unit = "bytes" if metric.endswith("bytes") else "ms"
            rows.append(
                f'<tr><td title="{html.escape(name)}">{html.escape(label)} <small>({unit})</small></td>'
                f'<td>{fmt(c["before_median"])}</td><td>{fmt(c["after_median"])}</td><td>{fmt(c["saved"])}</td>'
                f'<td>{fmt(c["reduction_percent"])}%</td><td>{ci}%</td><td>{c["n_before"]}/{c["n_after"]}</td><td>{signal}</td></tr>'
            )
        return (
            '<div class="table-wrap"><table><thead><tr><th>Comparison</th><th>Before</th><th>After</th><th>Saved</th><th>Reduction</th><th>95% interval</th><th>n</th><th>Reading</th></tr></thead><tbody>'
            + "".join(rows)
            + "</tbody></table></div>"
        )

    def build(self, template):
        self.plots()
        contents = template.read_text()
        replacements = {f"@@figure-{k}@@": v for k, v in self.figures.items()}
        primary = ["completion-ui-1000", "completion-ui-5000", "startup-ready-disabled", "startup-cpu-disabled", "startup-ready-default", "startup-cpu-default", "idle-idle_5s", "idle-editor_idle_5s", "long-cells-cpu", "long-cells-wall"]
        replacements["@@primary-table@@"] = self.comparison_table(primary)
        replacements["@@network-table@@"] = self.comparison_table([f"{label}-{p}-20" for p in ["postgresql", "mysql", "mariadb"] for label in ["bounded-query", "metadata-one-query", "metadata-batch", "connection-reuse"]])
        replacements["@@render-table@@"] = self.comparison_table([f"render50k-{v}-{m}" for v in ["bulk", "preview-thread", "timer500", "row-backend"] for m in ["wall_ms", "cpu_ms", "max_loop_delay_ms", "terminal_bytes"]])
        replacements["@@record-count@@"] = str(self.data["record_count"])
        validation_path = self.output / "validation.json"
        validation = json.loads(validation_path.read_text()) if validation_path.exists() else {}
        if validation:
            reasons = "; ".join(f"{html.escape(reason)} ({count})" for reason, count in validation["skip_reasons"].items())
            replacements["@@validation@@"] = (
                f"<p><strong>{validation['passed']:,} tests passed; {validation['skipped']} skipped; "
                f"{validation['failed']} failed.</strong> The broader lane ran the unit, UI, CLI, SQLite and DuckDB suites. "
                f'The focused lanes are subsets and are not added to this total.</p><p class="small">Skip reasons: {reasons}. '
                "These skips do not stand in for live provider verification. Existing CLI lint findings were checked against the baseline; "
                "the touched production files introduce no new lint category in that comparison. "
                '<a href="validation.json">Download validation details</a>.</p>'
            )
            if validation.get("python310"):
                compatibility = validation["python310"]
                replacements["@@validation@@"] += (
                    f"<p>A separate Python 3.10 compatibility lane passed <strong>{compatibility['passed']} targeted tests</strong>, "
                    f"with {compatibility['failed']} failures and {compatibility['skipped']} skips. These tests overlap the main lane and are reported separately.</p>"
                )
        else:
            raise RuntimeError("Run export_evidence.py to attach final regression results before building the paper")
        replacements["@@trace-examples@@"] = (self.output / "trace-examples.json").read_text().replace("<", "\\u003c")
        browser_metrics = {
            "wall_ms",
            "cpu_ms",
            "process_cpu_ms",
            "parent_ready_ms",
            "max_loop_delay_ms",
            "terminal_bytes",
            "rx_bytes",
            "tx_bytes",
            "parent_cpu_ms",
            "client_cpu_ms",
            "maxrss_kib",
            "bytes",
            "first_result_refresh_ms",
            "worker_reported_ms",
        }
        browser_stats = {"n", "median", "median_ci95", "p95", "min", "max"}
        browser_data = {
            "summaries": [
                {**{k: v for k, v in s.items() if k != "metrics"}, "metrics": {k: {stat: value for stat, value in v.items() if stat in browser_stats} for k, v in s["metrics"].items() if k in browser_metrics}} for s in self.data["summaries"]
            ]
        }

        def compact_numbers(value):
            if isinstance(value, float):
                return float(f"{value:.8g}")
            if isinstance(value, list):
                return [compact_numbers(v) for v in value]
            if isinstance(value, dict):
                return {k: compact_numbers(v) for k, v in value.items()}
            return value

        replacements["@@data@@"] = json.dumps(compact_numbers(browser_data), separators=(",", ":")).replace("<", "\\u003c")
        manifest = json.loads((self.output / "raw" / "manifest.json").read_text())
        replacements["@@raw-links@@"] = " ".join(f'<a href="raw/{r["file"]}" download>{r["file"]}</a>' for r in manifest)
        for name, c in self.comparisons.items():
            for key in ["before_median", "after_median", "saved", "reduction_percent"]:
                replacements[f"@@{name}:{key}@@"] = fmt(c[key])
        for key, value in replacements.items():
            contents = contents.replace(key, value)
        if re.search(r"@@[^@]+@@", contents):
            raise RuntimeError("Unresolved template values: " + str(re.findall(r"@@[^@]+@@", contents)))
        (self.output / "report.html").write_text(contents)
        print(f"Wrote {self.output / 'report.html'}: {len(contents.encode()):,} bytes; {len(self.figures)} figures")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--template", default=str(Path(__file__).with_name("report.html.in")))
    args = parser.parse_args()
    path = Path(args.data)
    Report(json.loads(path.read_text()), path.parent).build(Path(args.template))


if __name__ == "__main__":
    main()
