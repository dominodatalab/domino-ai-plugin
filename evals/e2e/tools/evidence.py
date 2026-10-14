"""Per-run evidence for write-path behaviour, extracted from redacted transcripts: Jobs, App and Model API
creates and whether they pinned a commit, commit ids seen, Model API log queries, local port collisions and
`pkill -f` self-kills. Use it to say whether a fixed defect stayed fixed. usage: evidence.py RUN_DIR [--json OUT]"""
import json, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from e2elib import transcript as trx

rd = Path(sys.argv[1])
rows = []
for res_p in sorted(rd.glob("*/*/result.json")):
    res = json.loads(res_p.read_text())
    tx = trx.parse((res_p.parent / "transcript.jsonl").read_text().splitlines())
    io = tx["tool_io"]
    allout = "\n".join(x["output"] for x in io)
    r = {"scenario": res["scenario"], "variant": res["variant"], "pass": res.get("pass"), "turns": res.get("num_turns"),
         "cost": round(res.get("cost_usd") or 0, 2), "skills": res.get("skills")}
    # commit ids, pinning, first-attempt outcome of each start or create
    r["commit_ids_seen"] = sorted(set(re.findall(r'\\?"(?:commit_id|commitId|dfsCommitId)\\?"\s*:\s*\\?"([0-9a-f]{7,40})', allout)))[:8]
    jobs = [x for x in io if x["name"].endswith("run_domino_job") or re.search(r"/api/jobs/v1/jobs\b", x["input"]) and re.search(r"POST|requests\.post|-d ", x["input"])]
    r["job_starts"] = [(re.search(r'"status":"(\w+)"', x["output"]) or [None, None])[1] if x["name"].endswith("run_domino_job") else "rest" for x in jobs]
    r["job_pinned"] = [bool(re.search(r'commit_?[iI]d', x["output"] + x["input"])) for x in jobs]
    app_create = [x for x in io if re.search(r"/api/apps/v1/apps(?![/\w])", x["input"]) and re.search(r"POST|requests\.post|--data|-d ", x["input"])]
    app_vers = [x for x in io if re.search(r"/api/apps/v1/apps/[^/\s\"']+/versions(/createAndStart)?(?![/\w])", x["input"]) and re.search(r"POST|requests\.post|--data|-d ", x["input"])]
    r["app_creates"] = len(app_create); r["app_create_pinned"] = [("dfsCommitId" in x["input"]) for x in app_create]
    r["app_extra_versions"] = len(app_vers)
    mapi_create = [x for x in io if re.search(r"/api/modelServing/v1/modelApis(?![/\w])", x["input"]) and re.search(r"POST|requests\.post|--data|-d ", x["input"])]
    mapi_vers = [x for x in io if re.search(r"/api/modelServing/v1/modelApis/[^/\s\"']+/versions(?![/\w])", x["input"]) and re.search(r"POST|requests\.post|--data|-d ", x["input"])]
    r["model_api_creates"] = len(mapi_create); r["model_api_create_pinned"] = [("commitId" in x["input"]) for x in mapi_create]
    r["model_api_extra_versions"] = len(mapi_vers)
    r["stale_commit_signs"] = len(re.findall(r"can't open file|not found in the root directory|No such file or directory: '/mnt/[^']*(model|app)", allout))
    # Model API instance-log queries
    logs = [x["input"] for x in io if "instanceLogs" in x["input"]]
    r["instance_log_calls"] = len(logs)
    r["log_tail_used"] = any("tail=true" in x for x in logs)
    r["log_max3000"] = any("maxResults=3000" in x or "'maxResults': 3000" in x or '"maxResults": 3000' in x for x in logs)
    r["log_model_filter"] = any(re.search(r"model-|container_name", x) for x in logs)
    # local port-8888 collision, pkill -f self-kill
    r["port_8888_collision"] = bool(re.search(r"8888[^\n]{0,80}(not available|already in use|in use|taken)|Address already in use[^\n]{0,40}8888", allout, re.I))
    r["pkill_f_calls"] = sum(1 for x in io if "pkill -f" in x["input"])
    r["exit_144"] = sum(1 for x in io if x["is_error"] and "Exit code 144" in x["output"])
    rows.append(r)

cols = ["scenario", "variant", "pass", "turns", "cost", "skills", "job_starts", "job_pinned", "app_creates", "app_create_pinned",
        "app_extra_versions", "model_api_creates", "model_api_create_pinned", "model_api_extra_versions", "stale_commit_signs",
        "instance_log_calls", "log_tail_used", "log_max3000", "log_model_filter", "port_8888_collision", "pkill_f_calls", "exit_144",
        "commit_ids_seen"]
for r in rows:
    print(" | ".join(f"{c}={r[c]}" for c in cols if r.get(c) not in (None, [], 0, False) or c in ("scenario", "variant", "pass", "turns")))
if "--json" in sys.argv:
    Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(rows, indent=2))
