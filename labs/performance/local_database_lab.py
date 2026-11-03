#!/usr/bin/env python3
"""Local SQLite/DuckDB connection, process-isolation and IPC experiments."""
from __future__ import annotations

import argparse
import json
import os
import pickle
import random
import resource
import sqlite3
import tempfile
import time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat",type=int,default=9)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    output=Path(args.output).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    records=[]
    with tempfile.TemporaryDirectory(prefix="sqlit-local-db-lab-") as temp:
        os.environ["SQLIT_CONFIG_DIR"]=temp
        os.environ["SQLIT_WORKER_LOG"]=str(Path(temp)/"worker.log")
        from sqlit.domains.connections.domain.config import ConnectionConfig, FileEndpoint
        from sqlit.domains.connections.providers.catalog import get_provider
        from sqlit.domains.process_worker.app.process_worker_client import ProcessWorkerClient
        from sqlit.domains.query.app.cancellable import CancellableQuery

        def measure(provider,name,iteration,callback):
            start, cpu=time.perf_counter(),time.process_time()
            extra=callback() or {}
            record={"provider":provider,"scenario":name,"iteration":iteration,
                    "wall_ms":(time.perf_counter()-start)*1000,
                    "parent_cpu_ms":(time.process_time()-cpu)*1000,
                    "maxrss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,**extra}
            records.append(record)
            print(json.dumps(record),flush=True)

        for name in ["sqlite","duckdb"]:
            path=Path(temp)/f"{name}.db"
            if name=="sqlite":
                conn=sqlite3.connect(path)
                conn.execute("CREATE TABLE lab_rows (id INTEGER PRIMARY KEY,payload TEXT)")
                conn.executemany("INSERT INTO lab_rows VALUES (?,?)",[(i,"x"*256) for i in range(1,50001)])
                conn.commit()
            else:
                import duckdb
                conn=duckdb.connect(str(path),config={"threads":"1"})
                conn.execute("CREATE TABLE lab_rows AS SELECT i AS id, repeat('x',256) AS payload FROM range(1,50001) t(i)")
            conn.close()
            config=ConnectionConfig(name="disposable-local-perf",db_type=name,endpoint=FileEndpoint(path=str(path)))
            if name=="duckdb":
                config.extra_options={"read_only":True,"config":{"threads":"1"}}
            provider=get_provider(name)
            adapter=provider.connection_factory
            conn=adapter.connect(config)
            client=ProcessWorkerClient()
            try:
                warmup=client.execute("SELECT 1",config,1000)
                assert not warmup.error and warmup.result.rows==[(1,)]
                def reuse():
                    assert adapter.execute_query(conn,"SELECT 1",1)[1]==[(1,)]
                def reconnect():
                    connection=adapter.connect(config)
                    try:
                        assert adapter.execute_query(connection,"SELECT 1",1)[1]==[(1,)]
                    finally:
                        connection.close()
                def cancellable():
                    result=CancellableQuery(sql="SELECT 1",config=config,provider=provider).execute(1000)
                    assert result.rows==[(1,)]
                def query(limit):
                    _,rows,truncated=adapter.execute_query(conn,"SELECT * FROM lab_rows ORDER BY id",limit)
                    expected=50000 if limit is None else limit
                    assert len(rows)==expected and rows[-1][0]==expected
                    assert truncated==(limit is not None)
                    return {"rows":len(rows)}
                def worker(limit,sql="SELECT * FROM lab_rows ORDER BY id"):
                    outcome=client.execute(sql,config,limit)
                    assert not outcome.error,outcome.error
                    expected=1 if sql=="SELECT 1" else (50000 if limit is None else limit)
                    assert outcome.result.row_count==expected
                    return {"rows":expected,"worker_reported_ms":outcome.elapsed_ms}
                def cold():
                    fresh=ProcessWorkerClient()
                    try:
                        outcome=fresh.execute("SELECT 1",config,1000)
                        assert not outcome.error and outcome.result.rows==[(1,)]
                        return {"worker_reported_ms":outcome.elapsed_ms}
                    finally:
                        fresh.close()
                cases={"reuse_select1":reuse,"connect_select1_close":reconnect,
                       "cancellable_select1":cancellable,"worker_warm_select1":lambda:worker(1000,"SELECT 1"),
                       "worker_cold_select1":cold,"direct_1000":lambda:query(1000),
                       "direct_50000":lambda:query(None),"worker_1000":lambda:worker(1000),
                       "worker_50000":lambda:worker(None)}
                rng=random.Random(91)
                for iteration in range(args.repeat):
                    names=list(cases)
                    rng.shuffle(names)
                    for scenario in names:
                        measure(name,scenario,iteration,cases[scenario])
            finally:
                client.close()
                conn.close()
                output.write_text(json.dumps(records,indent=2))

        # Serialization is isolated from driver and rendering measurements.
        from multiprocessing.reduction import ForkingPickler

        import pyarrow as pa
        for pattern in ["repeated","varied"]:
            import hashlib
            rows=[(i,(("x"*256).encode().decode() if pattern=="repeated" else "".join(hashlib.sha256(f"{i}-{j}".encode()).hexdigest() for j in range(4)))) for i in range(50000)]
            assert rows[0][1] is not rows[1][1]  # match independent driver-returned strings
            table=pa.table({"id":[r[0] for r in rows],"payload":[r[1] for r in rows]})
            for iteration in range(args.repeat):
                def pickle_roundtrip():
                    encoded=ForkingPickler.dumps(rows)
                    decoded=pickle.loads(encoded)
                    assert decoded==rows
                    return {"bytes":len(encoded),"rows":50000,"pattern":pattern}
                measure("ipc","pickle_roundtrip",iteration,pickle_roundtrip)
                for compression in [None,"lz4","zstd"]:
                    def arrow_roundtrip():
                        sink=pa.BufferOutputStream()
                        options=pa.ipc.IpcWriteOptions(compression=compression)
                        with pa.ipc.new_stream(sink,table.schema,options=options) as writer:
                            writer.write_table(table)
                        encoded=sink.getvalue()
                        decoded=pa.ipc.open_stream(encoded).read_all()
                        assert decoded.equals(table)
                        return {"bytes":len(encoded),"rows":50000,"pattern":pattern,
                                "boundary":"Arrow table to Arrow table; conversion from Python rows excluded"}
                    measure("ipc",f"arrow_{compression or 'none'}_roundtrip",iteration,arrow_roundtrip)
                def arrow_python_roundtrip():
                    input_table=pa.table({"id":[r[0] for r in rows],"payload":[r[1] for r in rows]})
                    sink=pa.BufferOutputStream()
                    with pa.ipc.new_stream(sink,input_table.schema) as writer:
                        writer.write_table(input_table)
                    encoded=sink.getvalue()
                    decoded=pa.ipc.open_stream(encoded).read_all()
                    result=list(zip(decoded.column(0).to_pylist(),decoded.column(1).to_pylist()))
                    assert result==rows
                    return {"bytes":len(encoded),"rows":50000,"pattern":pattern,
                            "boundary":"Python rows to Python rows including both Arrow conversions"}
                measure("ipc","arrow_python_roundtrip",iteration,arrow_python_roundtrip)
        output.write_text(json.dumps(records,indent=2))


if __name__=="__main__":
    main()
