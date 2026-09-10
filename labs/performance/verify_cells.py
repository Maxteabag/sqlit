#!/usr/bin/env python3
"""Capture long literal/Unicode cells while checking complete backend values."""
from __future__ import annotations

import argparse
import asyncio
import os
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Textual SVG screenshot path")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sqlit-cell-display-") as temp:
        os.environ["SQLIT_CONFIG_DIR"] = temp
        os.environ["SQLIT_SKIP_KEYRING_PROBE"] = "1"
        from textual.coordinate import Coordinate

        from sqlit.domains.shell.app.main import SSMSTUI
        from sqlit.shared.app.runtime import RuntimeConfig
        from tests.ui.mocks import MockConnectionStore, MockSettingsStore, build_test_services

        async def capture():
            services = build_test_services(
                runtime=RuntimeConfig(process_worker=False, process_worker_warm_on_idle=False),
                connection_store=MockConnectionStore(), settings_store=MockSettingsStore({"theme": "tokyo-night"}),
            )
            app = SSMSTUI(services=services)
            rows = [(i, "[bold]literal[/bold] " + "abcdef " * 1000 if i % 2 else "界e\u0301🙂 " * 1000) for i in range(1, 49)]
            async with app.run_test(size=(160, 40)) as pilot:
                # Lazy result widgets mount after the initial app refresh.
                await pilot.pause(.1)
                await app._display_query_results(["id", "complete_source_value"], rows, len(rows), False, 0)
                await pilot.pause(.1)
                app.results_table.focus()
                app.query_input.text = "-- Oversized values are clipped only for display.\nSELECT id, complete_source_value FROM lab_values;"
                await pilot.pause(.1)
                assert app.results_table.row_count == len(rows)
                for i, row in enumerate(rows):
                    assert app.results_table.get_cell_at(Coordinate(i, 1)) == row[1]
                output.write_text(app.export_screenshot(title="sqlit: bounded literal cell display"))
        asyncio.run(capture())
    print(f"Verified 48 complete long/Unicode values; screenshot: {output}")


if __name__ == "__main__":
    main()
