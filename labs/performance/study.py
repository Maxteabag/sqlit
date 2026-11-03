#!/usr/bin/env python3
"""Run the measured study sequentially, with paired order and resumable receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline",required=True)
    parser.add_argument("--candidate",required=True)
    parser.add_argument("--python",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--phases",default="startup,cpu,completion,render,idle,network,local")
    parser.add_argument("--docker",action="store_true")
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--quick",action="store_true",help="One trial per condition; smoke validation only")
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    output=Path(args.output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    phases=set(args.phases.split(','))
    allowed={"startup","cpu","completion","render","idle","network","local"}
    if phases-allowed:
        parser.error(f"Unknown phases: {phases-allowed}")
    if "network" in phases and not (args.docker or args.dry_run):
        parser.error("Network phase needs --docker for disposable local containers")
    repos={"baseline":Path(args.baseline).resolve(),"candidate":Path(args.candidate).resolve()}
    def git(repo,*argv):
        return subprocess.check_output(["git",*argv],cwd=repo,text=True).strip()
    shas={key:git(repo,"rev-parse","HEAD") for key,repo in repos.items()}
    if any(git(repo,"diff","HEAD","--","sqlit") for repo in repos.values()):
        parser.error("Commit production source before the study; code under test must stay fixed")
    measurement_files = ["run.py", "variants.py", "row_backend.py", "cpu_lab.py", "database_lab.py", "local_database_lab.py", "study.py"]
    inventory={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in measurement_files}
    host={"date_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"platform":platform.platform(),
          "cpu_count":os.cpu_count(),"loadavg":os.getloadavg(),"source_commits":shas,
          "lab_files_sha256":inventory,"argv":sys.argv,"measurement_python":args.python,
          "cpuinfo":Path('/proc/cpuinfo').read_text().split('\n\n')[0],
          "meminfo":Path('/proc/meminfo').read_text(),
          "governors":{str(p):p.read_text().strip() for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*/scaling_governor')}}
    host["packages"]=json.loads(subprocess.check_output([args.python,"-c",
        "import importlib.metadata as m,json,sys; print(json.dumps({'python':sys.version,'packages':{d.metadata['Name']:d.version for d in m.distributions()}}))"],text=True))
    (output/f"environment-{'-'.join(sorted(phases))}.json").write_text(json.dumps(host,indent=2))
    jobs=[]
    rng=random.Random(90210)
    def ui_job(label,source,mode,variant="stock",extra=()):
        command=[sys.executable,str(root/'run.py'),'--repo',str(repos[source]),'--python',args.python,
                 '--mode',mode,'--variant',variant,'--label',source,'--output',str(output/label),*extra]
        jobs.append((label,source,command))
    for phase in ["startup","completion","render","idle"]:
        if phase not in phases:
            continue
        repeats=1 if args.quick else (15 if phase=="startup" else (9 if phase in {"completion","idle"} else 5))
        for index in range(repeats):
            sources=list(repos)
            rng.shuffle(sources)
            if phase=="startup":
                for condition,extra in [("disabled",[]),("default",["--worker-default"])]:
                    for source in sources:
                        ui_job(f"startup-{condition}/{index:02d}-{source}",source,"startup",extra=extra)
                if index < (1 if args.quick else 7):
                    ui_job(f"startup-no-pyc/{index:02d}-candidate","candidate","startup",extra=["--no-bytecode-cache"])
            elif phase=="render":
                variants=[("baseline","stock"),("candidate","stock"),("baseline","bulk"),
                          ("baseline","preview-thread"),("baseline","timer500"),("baseline","row-backend")]
                rng.shuffle(variants)
                for source,variant in variants:
                    ui_job(f"render/{index:02d}-{source}-{variant}",source,"ui",variant)
                for source in sources:
                    ui_job(f"long-cells/{index:02d}-{source}",source,"ui",extra=["--workload","render_1000_3_long"])
            else:
                for source in sources:
                    ui_job(f"{phase}/{index:02d}-{source}",source,phase)
    if "cpu" in phases:
        for source in repos:
            jobs.append((f"cpu-{source}",source,[args.python,str(root/'cpu_lab.py'),'--repeat','1' if args.quick else '9',
                                               '--output',str(output/f'cpu-{source}.json')]))
    if "network" in phases:
        for provider in ["postgresql","mysql","mariadb"]:
            for delay in [0,20]:
                label=f"network-{provider}-{delay}"
                jobs.append((label,"baseline",[args.python,str(root/'database_lab.py'),'--docker','--provider',provider,
                                                '--repeat','1' if args.quick else '9','--one-way-ms',str(delay),
                                                '--output',str(output/f'{label}.json')]))
    if "local" in phases:
        jobs.append(("local-databases","baseline",[args.python,str(root/'local_database_lab.py'),'--repeat','1' if args.quick else '9',
                                                    '--output',str(output/'local-databases.json')]))
    plan=[{"label":label,"source":source,"command":cmd} for label,source,cmd in jobs]
    (output/f"plan-{'-'.join(sorted(phases))}.json").write_text(json.dumps(plan,indent=2))
    print(f"{len(jobs)} sequential jobs; source SHAs {shas}",flush=True)
    if args.dry_run:
        for item in plan:
            print(json.dumps(item))
        return
    receipts=output/'receipts'
    receipts.mkdir(exist_ok=True)
    for index,(label,source,command) in enumerate(jobs):
        key=label.replace('/','_')
        signature=hashlib.sha256(json.dumps([command,shas,inventory],sort_keys=True).encode()).hexdigest()
        receipt=receipts/f'{key}.json'
        if receipt.exists() and json.loads(receipt.read_text()).get('signature')==signature:
            print(f"{index+1}/{len(jobs)} already verified: {label}",flush=True)
            continue
        if git(repos[source],"rev-parse","HEAD")!=shas[source] or git(repos[source],"diff","HEAD","--","sqlit"):
            raise RuntimeError("Code changed during measurement")
        start=time.perf_counter()
        print(f"{index+1}/{len(jobs)} running: {label}",flush=True)
        with tempfile.TemporaryDirectory(prefix='sqlit-study-control-') as temp:
            env=os.environ.copy()
            env.update(PYTHONPATH=str(repos[source]),SQLIT_CONFIG_DIR=temp,
                       SQLIT_WORKER_LOG=str(Path(temp)/'worker.log'),PYTHONHASHSEED='0',
                       OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
            with (receipts/f'{key}.log').open('w') as log:
                proc=subprocess.run(command,env=env,cwd=root.parent.parent,stdout=log,stderr=subprocess.STDOUT,timeout=600)
        if proc.returncode:
            raise RuntimeError(f"Study failed at {label}; inspect {receipts/key}.log")
        receipt.write_text(json.dumps({"signature":signature,"source_sha":shas[source],"label":label,
                                      "wall_s":time.perf_counter()-start,"loadavg_after":os.getloadavg(),
                                      "finished_utc":time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())},indent=2))
    print("Requested study phases complete.",flush=True)


if __name__=='__main__':
    main()
