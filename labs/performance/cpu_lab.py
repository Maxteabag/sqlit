#!/usr/bin/env python3
"""CPU scaling and allocation probes with deterministic synthetic SQL metadata."""
from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import os
import resource
import time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes",default="100,1000,5000")
    parser.add_argument("--repeat",type=int,default=7)
    parser.add_argument("--output",required=True)
    parser.add_argument("--profile",action="store_true")
    args=parser.parse_args()
    from sqlit.domains.connections.providers.adapters.base import RoutineInfo
    from sqlit.domains.query.completion import get_completions
    records=[]
    for count in map(int,args.sizes.split(',')):
        routines=[RoutineInfo(f"proc_{i:05d}",schema="dbo",database="lab") for i in range(count)]
        tables=[f"public.table_{i:05d}" for i in range(count)]
        workloads=[("routine_completion","EXEC proc_",[],routines),
                   ("table_completion","SELECT * FROM public.table_",tables,[]),
                   ("unrelated_completion","SELECT ",[],routines),
                   ("blank_completion","",[],routines)]
        for name,sql,table_input,routine_input in workloads:
            expected=None
            get_completions(sql,len(sql),table_input,{},routine_input)  # excluded warmup
            for iteration in range(args.repeat):
                profiler=cProfile.Profile() if args.profile else None
                if profiler:
                    profiler.enable()
                cpu,wall=time.process_time(),time.perf_counter()
                values=get_completions(sql,len(sql),table_input,{},routine_input)
                wall_ms=(time.perf_counter()-wall)*1000
                cpu_ms=(time.process_time()-cpu)*1000
                if profiler:
                    profiler.disable()
                digest=hashlib.sha256(json.dumps(values).encode()).hexdigest()
                if expected is None:
                    expected=digest
                assert digest==expected
                if name=="blank_completion":
                    assert values==[]
                if name=="routine_completion":
                    assert len(values)==min(count,50) and "proc_00000" in values
                record={"scenario":name,"objects":count,"iteration":iteration,
                        "wall_ms":wall_ms,"cpu_ms":cpu_ms,"suggestions":len(values),
                        "digest":digest,"maxrss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        "loadavg":os.getloadavg()}
                records.append(record)
                print(json.dumps(record),flush=True)
                if profiler:
                    profiler.dump_stats(f"{args.output}.{name}-{count}-{iteration}.pstats")
    Path(args.output).write_text(json.dumps(records,indent=2))


if __name__=="__main__":
    main()
