#!/usr/bin/env python3
"""Measure sqlit against disposable local databases and a latency/byte relay.

Docker opt-in is explicit. Public lab credentials are never used elsewhere.
The relay counts protocol payload bytes, not Ethernet/TCP retransmissions. It
adds one-way delivery latency using pipelined queues, not sleeps per SQL call.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import multiprocessing as mp
import os
import random
import resource
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


async def _relay_server(target_port, delay_ms, counts, control):
    async def forward(reader, writer, direction):
        queue = asyncio.Queue(maxsize=64)
        async def receive():
            try:
                while data := await reader.read(65536):
                    await queue.put((asyncio.get_running_loop().time()+delay_ms/1000, data))
            finally:
                await queue.put((0, None))
        async def send():
            try:
                while True:
                    due, data = await queue.get()
                    if data is None:
                        break
                    await asyncio.sleep(max(0, due-asyncio.get_running_loop().time()))
                    writer.write(data)
                    await writer.drain()
                    with counts.get_lock():
                        counts[direction] += len(data)
            finally:
                writer.close()
        await asyncio.gather(receive(), send())
    async def connect(reader, writer):
        try:
            remote_reader, remote_writer = await asyncio.open_connection("127.0.0.1", target_port)
            await asyncio.gather(forward(reader, remote_writer, 0), forward(remote_reader, writer, 1))
        except (ConnectionError, OSError):
            writer.close()
    server = await asyncio.start_server(connect, "127.0.0.1", 0)
    control.send(server.sockets[0].getsockname()[1])
    async with server:
        await server.serve_forever()


def relay_main(target_port, delay_ms, counts, control):
    asyncio.run(_relay_server(target_port, delay_ms, counts, control))


@contextmanager
def relay(port: int, one_way_ms: float):
    context = mp.get_context("spawn")
    counts = context.Array("Q", [0,0])
    parent, child = context.Pipe()
    process = context.Process(target=relay_main, args=(port, one_way_ms, counts, child), daemon=True)
    process.start()
    try:
        if not parent.poll(10):
            raise TimeoutError("Relay did not start")
        yield parent.recv(), counts
    finally:
        process.terminate()
        process.join(10)
        parent.close()
        child.close()


@contextmanager
def disposable_database(provider: str):
    name = f"sqlit-perf-{provider}-{uuid.uuid4().hex[:8]}"
    image = {"postgresql":"postgres:16-alpine", "mysql":"mysql:8.0", "mariadb":"mariadb:11"}[provider]
    image_id = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", image], text=True).strip()
    database_port = "5432" if provider == "postgresql" else "3306"
    env = ["POSTGRES_USER=lab", "POSTGRES_PASSWORD=lab", "POSTGRES_DB=lab"] if provider == "postgresql" else [
        "MARIADB_ROOT_PASSWORD=lab", "MARIADB_DATABASE=lab", "MARIADB_USER=lab", "MARIADB_PASSWORD=lab"]
    if provider == "mysql":
        env = [value.replace("MARIADB_", "MYSQL_") for value in env]
    command = ["docker", "run", "--detach", "--pull=never", "--name", name,
               "--label", "sqlit.performance-lab=true", "--cpus=1", "--memory=512m",
               "--memory-swap=512m", "-p", f"127.0.0.1::{database_port}"]
    for entry in env:
        command += ["-e", entry]
    command += [image]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    try:
        port = int(subprocess.check_output(["docker", "port", name, f"{database_port}/tcp"], text=True).strip().rsplit(":",1)[1])
        yield port, {"container":name,"image":image,"image_id":image_id,"cpus":1,"memory_mib":512}
    finally:
        subprocess.run(["docker", "stop", "--time", "20", name], check=True, stdout=subprocess.DEVNULL)
        status = subprocess.check_output(["docker", "inspect", "--format", "{{json .State}}", name], text=True)
        print("container stopped", name, status.strip(), flush=True)
        subprocess.run(["docker", "rm", "-v", name], check=True, stdout=subprocess.DEVNULL)


def config_for(provider, port):
    from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint
    return ConnectionConfig(name="disposable-perf", db_type=provider,
                            endpoint=TcpEndpoint(host="127.0.0.1", port=str(port),
                                                 database="lab",username="lab",password="lab"),
                            options={"tls_mode":"disable"})


def connect_ready(provider, config):
    from sqlit.domains.connections.app.session import ConnectionSession
    deadline = time.monotonic()+90
    error = None
    while time.monotonic() < deadline:
        try:
            session = ConnectionSession.create(config)
            result = session.provider.query_executor.execute_query(session.connection,"SELECT 1",1)
            assert result[1] == [(1,)]
            return session
        except Exception as exc:
            error = exc
            time.sleep(.5)
    raise RuntimeError(f"Real {provider} SELECT 1 readiness failed: {error}")


def prepare_database(provider, session):
    connection = session.connection
    cursor = connection.cursor()
    for i in range(20):
        cursor.execute(f"CREATE TABLE lab_t_{i:02d} (id INTEGER PRIMARY KEY, name VARCHAR(120), amount DECIMAL(18,4), note TEXT)")
    cursor.execute("CREATE TABLE lab_rows (id INTEGER PRIMARY KEY, payload VARCHAR(300))")
    if provider == "postgresql":
        cursor.execute("INSERT INTO lab_rows SELECT i, repeat('x',256) FROM generate_series(1,50000) i")
    else:
        cursor.executemany("INSERT INTO lab_rows VALUES (%s,%s)", [(i,"x"*256) for i in range(1,50001)])
    connection.commit()
    cursor.close()


def run_network(provider, port, args, records):
    from sqlit.domains.connections.app.session import ConnectionSession
    from sqlit.domains.connections.providers.catalog import get_provider
    adapter = get_provider(provider).connection_factory
    with relay(port, args.one_way_ms) as (proxy_port, counts):
        config = config_for(provider, proxy_port)
        session = ConnectionSession.create(config)
        connection = session.connection
        def measured(name, callback, iteration):
            start_bytes = list(counts)
            before = time.perf_counter()
            cpu = time.process_time()
            result = callback()
            cpu_ms = (time.process_time()-cpu)*1000
            wall_ms = (time.perf_counter()-before)*1000
            # A final protocol QUIT may still be in the latency queue after
            # driver.close() returns. Attribute it here, not to the next case.
            time.sleep(max(.02,2*args.one_way_ms/1000+.01))
            end_bytes = list(counts)
            record = {"provider":provider,"scenario":name,"iteration":iteration,
                      "one_way_delay_ms":args.one_way_ms,"wall_ms":wall_ms,"client_cpu_ms":cpu_ms,
                      "tx_bytes":end_bytes[0]-start_bytes[0],"rx_bytes":end_bytes[1]-start_bytes[1],
                      "maxrss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      **(result or {})}
            records.append(record)
            print(json.dumps(record),flush=True)
        def new_connection():
            with ConnectionSession.create(config) as fresh:
                assert adapter.execute_query(fresh.connection,"SELECT 1",1)[1] == [(1,)]
        def reused_connection():
            assert adapter.execute_query(connection,"SELECT 1",1)[1] == [(1,)]
        def buffered():
            _,rows,truncated = adapter.execute_query(connection,"SELECT * FROM lab_rows ORDER BY id",1000)
            assert len(rows)==1000 and rows[0][0]==1 and rows[-1][0]==1000 and truncated
            return {"rows_returned":len(rows),"truncated":truncated}
        def server_limit():
            _,rows,truncated = adapter.execute_query(connection,"SELECT * FROM lab_rows ORDER BY id LIMIT 1001",1000)
            assert len(rows)==1000 and rows[-1][0]==1000 and truncated
            return {"rows_returned":len(rows),"truncated":truncated}
        expected_metadata = {}
        def per_table():
            for i in range(20):
                table = f"lab_t_{i:02d}"
                columns = adapter.get_columns(connection,table,"lab","public" if provider=="postgresql" else None)
                assert len(columns)==4 and columns[0].is_primary_key
                expected_metadata[table] = [(c.name,c.data_type,c.is_primary_key) for c in columns]
            return {"tables":20,"columns_returned":80}
        def bulk_metadata():
            cursor = connection.cursor()
            if provider == "postgresql":
                cursor.execute("""SELECT c.table_name,c.column_name,c.data_type,
                    EXISTS(SELECT 1 FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage k
                    ON k.constraint_catalog=tc.constraint_catalog AND k.constraint_schema=tc.constraint_schema
                    AND k.constraint_name=tc.constraint_name AND k.table_name=tc.table_name
                    WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema=c.table_schema
                    AND tc.table_name=c.table_name AND k.column_name=c.column_name)
                    FROM information_schema.columns c WHERE c.table_schema='public' AND c.table_name LIKE 'lab_t_%%'
                    ORDER BY c.table_name,c.ordinal_position""")
            else:
                cursor.execute("""SELECT table_name,column_name,data_type,column_key='PRI'
                    FROM information_schema.columns WHERE table_schema='lab' AND table_name LIKE 'lab_t_%%'
                    ORDER BY table_name,ordinal_position""")
            actual = {}
            for table,name,kind,pk in cursor.fetchall():
                actual.setdefault(table,[]).append((name,kind,bool(pk)))
            cursor.close()
            assert actual == expected_metadata, (actual,expected_metadata)
            return {"tables":len(actual),"columns_returned":sum(map(len,actual.values()))}
        def one_query_metadata():
            cursor = connection.cursor()
            for table, expected in expected_metadata.items():
                if provider == "postgresql":
                    cursor.execute("""SELECT c.column_name,c.data_type,
                        EXISTS(SELECT 1 FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage k
                        ON k.constraint_catalog=tc.constraint_catalog AND k.constraint_schema=tc.constraint_schema
                        AND k.constraint_name=tc.constraint_name AND k.table_name=tc.table_name
                        WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema=c.table_schema
                        AND tc.table_name=c.table_name AND k.column_name=c.column_name)
                        FROM information_schema.columns c WHERE c.table_schema=%s AND c.table_name=%s
                        ORDER BY c.ordinal_position""", ("public",table))
                else:
                    cursor.execute("""SELECT column_name,data_type,column_key='PRI'
                        FROM information_schema.columns WHERE table_schema=%s AND table_name=%s
                        ORDER BY ordinal_position""", ("lab",table))
                assert [(n,t,bool(p)) for n,t,p in cursor.fetchall()] == expected
            cursor.close()
            return {"tables":20,"columns_returned":80}
        def streaming():
            start = time.perf_counter()
            before = list(counts)
            if provider=="postgresql":
                connection.autocommit=False
                cursor = connection.cursor(name="sqlit_perf_cursor")
            else:
                from pymysql.cursors import SSCursor
                cursor = connection.cursor(SSCursor)
            cursor.execute("SELECT * FROM lab_rows ORDER BY id")
            rows = cursor.fetchmany(1001)
            first_fetch_ms=(time.perf_counter()-start)*1000
            first_fetch_rx=list(counts)[1]-before[1]
            assert len(rows)==1001 and rows[-1][0]==1001
            cursor.close()  # MySQL must drain unread rows to preserve this session.
            if provider=="postgresql":
                connection.rollback()
                connection.autocommit=True
            assert adapter.execute_query(connection,"SELECT 1",1)[1] == [(1,)]
            return {"first_fetch_ms":first_fetch_ms,"first_fetch_rx_bytes":first_fetch_rx,"rows_returned":1000,"truncated":True}
        try:
            # Characterization/validation precedes all timed metadata comparisons.
            per_table()
            bulk_metadata()
            cases={"connect_query_close":new_connection,"reuse_query":reused_connection,
                   "buffered_cap_1000":buffered,"server_limit_1001":server_limit,
                   "metadata_per_table":per_table,"metadata_batch":bulk_metadata,
                   "metadata_one_query_per_table":one_query_metadata,
                   "stream_fetch_cleanup":streaming}
            rng=random.Random(73)
            for iteration in range(args.repeat):
                names=list(cases)
                rng.shuffle(names)
                for name in names:
                    measured(name,cases[name],iteration)
        finally:
            session.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker",action="store_true",help="Authorize creation/removal of labeled local PostgreSQL/MariaDB containers")
    parser.add_argument("--provider",choices=["postgresql","mysql","mariadb"],required=True)
    parser.add_argument("--repeat",type=int,default=7)
    parser.add_argument("--one-way-ms",type=float,default=0)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    if not args.docker:
        parser.error("--docker is required; no external database endpoints are accepted")
    output=Path(args.output).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    records=[]
    with tempfile.TemporaryDirectory(prefix="sqlit-db-perf-") as temp:
        os.environ["SQLIT_CONFIG_DIR"]=temp
        os.environ["SQLIT_WORKER_LOG"]=str(Path(temp)/"worker.log")
        with disposable_database(args.provider) as (port,metadata):
            session=connect_ready(args.provider,config_for(args.provider,port))
            try:
                prepare_database(args.provider,session)
            finally:
                session.close()
            try:
                run_network(args.provider,port,args,records)
            finally:
                output.write_text(json.dumps({"metadata":metadata,"records":records},indent=2))


if __name__=="__main__":
    main()
