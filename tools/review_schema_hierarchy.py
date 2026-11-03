#!/usr/bin/env python3
"""Capture and exercise schema hierarchy against the disposable PostgreSQL fixture.

Create a fresh database and apply tools/fixtures/schema_hierarchy.sql first.
This script never creates or modifies database objects. Output uses only the
fixture's synthetic data. Requires the repository development dependencies.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def arguments():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--worker", action="store_true", help="Exercise the process worker as well")
    return p.parse_args()


async def capture(args):
    with tempfile.TemporaryDirectory(prefix="sqlit-schema-review-") as temp:
        os.environ["SQLIT_CONFIG_DIR"] = temp
        os.environ.pop("NO_COLOR", None)
        os.environ["FORCE_COLOR"] = "1"
        from sqlit.domains.connections.domain.config import ConnectionConfig
        from sqlit.domains.explorer.domain.tree_nodes import ColumnNode, DatabaseNode, FolderNode, SchemaNode, SequenceNode, TableNode
        from sqlit.domains.shell.app.main import SSMSTUI
        from sqlit.domains.shell.store.settings import SettingsStore
        from sqlit.shared.app.runtime import RuntimeConfig
        from tests.ui.mocks import MockConnectionStore, build_test_services

        config = ConnectionConfig.from_dict(dict(name="Workbench", db_type="postgresql", server="127.0.0.1", port=str(args.port), database="workbench", username="postgres", password="demo"))
        settings = SettingsStore(file_path=Path(temp) / "settings.json")
        settings.save_all({"theme": "vesper", "explorer_hierarchy": "type"})
        services = build_test_services(
            runtime=RuntimeConfig(settings_path=Path(temp) / "settings.json", process_worker=args.worker, process_worker_warm_on_idle=False), connection_store=MockConnectionStore([config]), settings_store=settings
        )
        app = SSMSTUI(services=services)
        args.output.mkdir(parents=True, exist_ok=True)
        checks = []
        async with app.run_test(size=(140, 46)) as pilot:

            async def settle():
                for _ in range(4):
                    await pilot.pause(0.08)
                    await app.workers.wait_for_complete()

            def nodes():
                stack = [app.object_tree.root]
                found = []
                while stack:
                    node = stack.pop()
                    found.append(node)
                    stack.extend(reversed(node.children))
                return found

            def find(cls, **fields):
                return next(n for n in nodes() if isinstance(n.data, cls) and all(getattr(n.data, k) == v for k, v in fields.items()))

            async def expand(cls, **fields):
                node = find(cls, **fields)
                node.expand()
                await settle()
                return node

            async def shot(name):
                await settle()
                (args.output / (name + ".svg")).write_text(app.export_screenshot(title="sqlit · " + name[3:].replace("-", " ")))
                print(name, flush=True)

            await settle()
            app.connect_to_server(config)
            await settle()
            assert app.current_connection is not None, (app._last_notification, type(app.screen).__name__, getattr(app.screen, "message", None), getattr(app.screen, "error_message", None))
            await expand(FolderNode, folder_type="tables", schema=None)
            await expand(FolderNode, folder_type="views", schema=None)
            for n in nodes():
                if isinstance(n.data, SchemaNode) and n.data.schema == "billing":
                    n.expand()
            await settle()
            app.object_tree.focus()
            await shot("01-before-object-type")

            app._run_command("explorer")
            await settle()
            await pilot.press("down")
            await shot("02-layout-picker")
            await pilot.press("enter")
            await settle()
            assert settings.get("explorer_hierarchy") == "schema"
            billing = await expand(SchemaNode, schema="billing", folder_type="")
            assert {n.data.folder_type for n in billing.children if isinstance(n.data, FolderNode)} == {"tables", "views", "indexes", "triggers", "sequences", "procedures"}
            for kind in ["tables", "views", "procedures"]:
                await expand(FolderNode, folder_type=kind, schema="billing")
            app.object_tree.move_cursor(billing)
            await shot("03-after-schema-first")
            checks.append("Layout picker saves schema preference; all six object types are below billing")

            orders = await expand(TableNode, schema="billing", name="orders")
            assert any(isinstance(n.data, ColumnNode) and n.data.schema == "billing" for n in orders.children)
            app.object_tree.move_cursor(orders)
            app.action_select_table()
            await settle()
            assert '"billing"."orders"' in app.query_input.text, app.query_input.text
            assert app.results_table.row_count == 3
            await shot("04-select-billing-orders")
            checks.append("Expanding a table loads columns; selecting billing.orders executes schema-qualified SQL and returns three fixture rows")

            if args.worker:
                assert app._process_worker_client is not None
                checks.append("Actual process worker started and served schema-scoped catalog and query requests")
            query = app.query_input.text
            await expand(SchemaNode, schema="analytics", folder_type="")
            await expand(FolderNode, folder_type="tables", schema="analytics")
            table_names = {(n.data.schema, n.data.name) for n in nodes() if isinstance(n.data, TableNode)}
            assert ("billing", "orders") in table_names and ("analytics", "orders") in table_names
            app.object_tree.focus()
            app.object_tree.move_cursor(find(TableNode, schema="analytics", name="orders"))
            await shot("05-duplicate-names")
            checks.append("billing.orders and analytics.orders coexist with distinct schema identities")

            app.action_tree_filter()
            app._tree_filter_text = "orders"
            app._update_tree_filter()
            await settle()
            assert any(isinstance(n.data, TableNode) and n.data.schema == "analytics" for n in app._tree_filter_matches)
            app.action_tree_filter_close()
            await settle()
            app.object_tree.move_cursor(find(TableNode, schema="analytics", name="orders"))
            await settle()
            checks.append("Explorer filtering finds objects inside schema-first folders and restores the tree on close")

            app._refresh_tree_common(notify=False)
            await settle()
            assert app.query_input.text == query
            assert find(TableNode, schema="billing", name="orders")
            assert find(TableNode, schema="analytics", name="orders")
            assert isinstance(app.object_tree.cursor_node.data, TableNode) and app.object_tree.cursor_node.data.schema == "analytics"
            checks.append("Refresh restores expanded schemas, folders, columns and the selected analytics.orders; query remains intact")

            # Inspect duplicate ancillary names using schema-qualified metadata.
            for owner, expected in [("billing", "10000"), ("analytics", "90000")]:
                await expand(FolderNode, folder_type="sequences", schema=owner)
                seq = find(SequenceNode, schema=owner, name="invoice_number")
                info = await asyncio.to_thread(app._get_schema_service().get_sequence_definition, seq.data.database, seq.data.name, owner)
                assert info["start_value"] == expected
            checks.append("Same-named sequences resolve to the correct schema (10000 vs 90000)")

            # Empty schemas remain discoverable, and empty folders resolve once.
            for n in nodes():
                if isinstance(n.data, SchemaNode):
                    n.collapse()
            await expand(SchemaNode, schema="empty_lab", folder_type="")
            empty = await expand(FolderNode, folder_type="tables", schema="empty_lab")
            assert "(Empty)" in str(empty.children[0].label)
            app.object_tree.move_cursor(empty)
            await shot("06-empty-schema")
            checks.append("An empty schema is listed and its empty Tables folder displays an explicit empty state")

            app.action_tree_filter()
            app._tree_filter_text = "empty_lab"
            app._update_tree_filter()
            app._run_command("explorer type")
            assert not app._tree_filter_visible
            await settle()
            assert not any(isinstance(n.data, SchemaNode) and not n.data.folder_type for n in nodes())
            assert app.query_input.text == query
            app._run_command("explorer schema")
            await settle()
            assert find(SchemaNode, schema="empty_lab", folder_type="").is_expanded
            checks.append("Switching layouts preserves query text and each layout restores its own expanded branches")

        # A new app instance reads the setting from the persisted file.
        restarted = SSMSTUI(services=services)
        async with restarted.run_test(size=(140, 46)) as pilot:
            await pilot.pause()
            assert services.settings_store.get("explorer_hierarchy") == "schema"
            restarted.connect_to_server(config)
            for _ in range(4):
                await pilot.pause(0.1)
                await restarted.workers.wait_for_complete()
            connected = restarted.object_tree.root.children[0]
            assert any(isinstance(n.data, SchemaNode) for n in connected.children)
        checks.append("New app instance restores the persisted schema layout")

        # Browsing a server must not eagerly enumerate every database's schemas.
        multi_config = config.with_endpoint(database="")
        multi_services = build_test_services(runtime=RuntimeConfig(process_worker=args.worker, process_worker_warm_on_idle=False), connection_store=MockConnectionStore([multi_config]), settings_store=settings)
        multi = SSMSTUI(services=multi_services)
        async with multi.run_test(size=(140, 46)) as pilot:
            await pilot.pause()
            multi.connect_to_server(multi_config)
            for _ in range(5):
                await pilot.pause(0.1)
                await multi.workers.wait_for_complete()
            dbs = multi.object_tree.root.children[0].children[0]
            assert isinstance(dbs.data, FolderNode) and dbs.data.folder_type == "databases"
            assert all(not n.children for n in dbs.children if isinstance(n.data, DatabaseNode))
            workbench = next(n for n in dbs.children if isinstance(n.data, DatabaseNode) and n.data.name == "workbench")
            workbench.expand()
            for _ in range(5):
                await pilot.pause(0.1)
                await multi.workers.wait_for_complete()
            assert any(isinstance(n.data, SchemaNode) and n.data.schema == "billing" for n in workbench.children)
            for db in dbs.children:
                if isinstance(db.data, DatabaseNode) and db.data.name != "workbench":
                    assert not db.children
            billing = next(n for n in workbench.children if isinstance(n.data, SchemaNode) and n.data.schema == "billing")
            billing.expand()
            await pilot.pause()
            multi.object_tree.move_cursor(billing)
            await pilot.pause()
            (args.output / "07-multi-database.svg").write_text(multi.export_screenshot(title="sqlit · database → schema → object type"))
        checks.append("Multi-database browsing loads schemas only for the expanded database")

        (args.output / "manifest.json").write_text(
            json.dumps(
                {
                    "commit": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
                    "terminal": [140, 46],
                    "provider": "PostgreSQL 16 in disposable Docker container",
                    "process_worker": args.worker,
                    "data": "tools/fixtures/schema_hierarchy.sql",
                    "checks": checks,
                },
                indent=2,
            )
            + "\n"
        )
        print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    asyncio.run(capture(arguments()))
