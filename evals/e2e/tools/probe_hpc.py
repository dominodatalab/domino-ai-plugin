#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Live probe of the HPC/Slurm surface on a deployment (no Claude involved). Creates one scratch DFS project,
records discovery, submit-supported, list, a start attempt and a Slurm Workspace attach attempt, then cleans up.
Prints shapes only; never prints tokens. usage: probe_hpc.py CONFIG"""
import json, sys, time, urllib.request, urllib.error
from pathlib import Path
import yaml
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from e2elib.domino import Domino

cfg = yaml.safe_load(open(sys.argv[1])); d = Domino(cfg["domino"])
me = d.whoami()["userName"]
LOCAL = "000000000000000000000000"
def show(label, code, txt, n=600): print(f"{label}: HTTP {code} {txt[:n]}", flush=True)

name = f"{cfg['projects']['name_prefix']}-hpcprobe-{time.strftime('%m%d%H%M')}"
p = d.post("/api/projects/v2/projects", {"name": name, "description": "e2e probe: HPC/Slurm surface. Safe to delete.", "visibility": "Private"})
p = p.get("project", p); pid = p["id"]; print("project", name, pid, flush=True)
created = {"project": pid, "workspaces": []}
try:
    code, txt = d.request("GET", "/v4/dataplanes/dataplanes", ok=None, raw=True)
    try:
        planes = json.loads(txt)
        print("dataplanes:", [(x.get("id"), x.get("name"), x.get("isLocal"), (x.get("status") or {}).get("supportsSlurm"), (x.get("status") or {}).get("state")) for x in planes])
    except Exception: show("dataplanes", code, txt)
    show("submit-supported local", *d.request("GET", "/api/hpc/v1/jobs/submit-supported", params={"projectId": pid, "dataPlaneId": LOCAL}, ok=None, raw=True))
    show("submit-supported no plane", *d.request("GET", "/api/hpc/v1/jobs/submit-supported", params={"projectId": pid}, ok=None, raw=True))
    show("hpc list (empty project)", *d.request("GET", "/api/hpc/v1/jobs", params={"projectId": pid}, ok=None, raw=True))
    envs = []
    off = 0
    while True:
        r = d.get("/api/environments/beta/environments", params={"offset": off, "limit": 100}, ok=None)
        page = (r or {}).get("environments", []); envs += page
        if len(page) < 100: break
        off += 100
    print("envs with supportedClusters Slurm:", [(e["id"], e["name"]) for e in envs if "slurm" in [c.lower() for c in e.get("supportedClusters") or []]])
    print("envs named Slurm*:", [(e["id"], e["name"], e.get("supportedClusters")) for e in envs if "slurm" in e["name"].lower()])
    tiers = d.get("/api/hardwaretiers/v1/hardwaretiers", params={"limit": 100}).get("hardwareTiers", [])
    print("tiers restrictToSlurm:", [t["id"] for t in tiers if (t.get("computeClusterRestrictions") or {}).get("restrictToSlurm")])
    show("defaultComputeClusterSettings", *d.request("GET", f"/v4/workspace/{pid}/Slurm/defaultComputeClusterSettings", ok=None, raw=True))
    # upload a script, then try an HPC start on the Local plane
    script = b"#!/bin/bash\n#SBATCH --array=0-1\numask 077\necho task $SLURM_ARRAY_TASK_ID\n"
    rq = urllib.request.Request(f"{d.host}/v1/projects/{me}/{name}/hpc/sweep.sh", data=script, method="PUT",
                                headers={"Authorization": f"Bearer {d._token()}", "Content-Type": "application/octet-stream"})
    print("upload hpc/sweep.sh:", urllib.request.urlopen(rq, timeout=60).status, flush=True)
    time.sleep(25)
    show("POST hpc job (local plane)", *d.request("POST", "/api/hpc/v1/jobs", body={"projectId": pid, "filePath": "hpc/sweep.sh", "dataPlaneId": LOCAL,
         "title": "probe", "config": {"cpu": 4, "walltime": "02:00:00"}}, ok=None, raw=True))
    show("POST hpc job (missing file)", *d.request("POST", "/api/hpc/v1/jobs", body={"projectId": pid, "filePath": "hpc/nope.sh", "dataPlaneId": LOCAL}, ok=None, raw=True))
    time.sleep(5)
    show("hpc list after attempts", *d.request("GET", "/api/hpc/v1/jobs", params={"projectId": pid}, ok=None, raw=True))
    print("standard jobs in project:", len(d.jobs(pid, 50)))
    # Workspace with a Slurm cluster on the Local plane
    client = next((e["id"] for e in envs if e["name"].lower().startswith("slurm client")), cfg["workspace"]["environment_id"])
    worker = next((e["id"] for e in envs if e["name"].lower().startswith("slurm worker")), None)
    body = {"name": "e2e-slurm-probe", "environmentId": client, "hardwareTierId": {"value": "small-k8s"}, "tools": ["vscode"],
            "externalVolumeMounts": [], "persistence": {"persistPackages": False, "persistHomeDirectory": False},
            "computeClusterConfig": {"clusterType": "Slurm", "computeEnvironmentId": worker, "computeEnvironmentRevisionSpec": "ActiveRevision",
                                     "workerCount": 1, "maxWorkerCount": 2, "workerHardwareTierId": {"value": "small-k8s"}}}
    code, txt = d.request("POST", f"/v4/workspace/project/{pid}/workspace", body=body, ok=None, raw=True)
    show("POST workspace with Slurm cluster", code, txt, 900)
    if code in (200, 201):
        wid = json.loads(txt).get("id"); created["workspaces"].append(wid)
        time.sleep(30)
        w = d.get(f"/v4/workspace/project/{pid}/workspace/{wid}")
        s = w.get("mostRecentSession") or {}
        print("slurm workspace status:", (s.get("sessionStatusInfo") or {}).get("rawExecutionDisplayStatus"), "| cluster:", json.dumps(s.get("config", {}).get("computeClusterConfig") or w.get("configTemplate", {}).get("computeClusterConfig"))[:300])
finally:
    for wid in created["workspaces"]:
        d.request("POST", f"/v4/workspace/project/{pid}/workspace/{wid}/stop", body={}, ok=None)
        for _ in range(20):
            c, _t = d.request("DELETE", f"/v4/workspace/project/{pid}/workspace/{wid}", ok=None, raw=True)
            if c == 200: break
            time.sleep(15)
        print("workspace", wid, "delete", c)
    for ds in d.datasets(pid):
        print("dataset", ds["name"], "delete", d.request("DELETE", f"/api/datasetrw/v1/datasets/{ds['id']}", ok=None, raw=True)[0])
    print("project archive", d.request("DELETE", f"/api/projects/beta/projects/{pid}", ok=None, raw=True)[0])
