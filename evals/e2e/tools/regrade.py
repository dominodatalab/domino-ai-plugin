#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Re-run a scenario's current checks against a finished run (same window, tag and lane). Updates result.json,
keeping the original checks under "checks_original". usage: regrade.py CONFIG RUN_DIR SCENARIO VARIANT [--cleanup]"""
import json, sys, time
from pathlib import Path
import yaml
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from e2elib import checks as ck
from e2elib.domino import Domino
from e2elib.remote import Remote
from e2elib.runner import _tmpl

cfg = yaml.safe_load(open(sys.argv[1]))
rdir, sid, var = Path(sys.argv[2]), sys.argv[3], sys.argv[4]
st = json.loads((HERE / "state/state.json").read_text())
res_p = rdir / sid / var / "result.json"
res = json.loads(res_p.read_text())
scen = yaml.safe_load((HERE / "scenarios" / f"{sid}.yaml").read_text())
lane = res.get("lane") or res["project_type"]
ws = st["workspaces"][lane]; proj = st["projects"][lane]
ds = cfg["projects"]["datasets"][0]
v = {"run_tag": res["run_tag"], "run_dir": f"{cfg['remote']['run_root'][res['project_type']]}/{res['run_id']}",
     "job_tier": cfg["compute"]["job_tier"], "model_api_tier": cfg["compute"].get("model_api_tier"), "dataset": ds,
     "dataset_id": proj["datasets"][ds]["id"], "datasets_dir": ws.get("datasets_dir"),
     "dataset_path": (ws.get("dataset_paths") or {}).get(ds), "project_name": proj["name"], "project_id": proj["id"],
     "username": st["user"]["userName"], "home": "/home/" + cfg["workspace"]["ssh_user"],
     "run_root": cfg["remote"]["run_root"][res["project_type"]]}
s = _tmpl(scen, v)
from e2elib import transcript as trx
tx = trx.parse((rdir / sid / var / "transcript.jsonl").read_text().splitlines())
tx["final_text"] = tx.get("final_text") or res.get("final_text", "")
c = ck.Ctx(Domino(cfg["domino"]), Remote(ws["id"], HERE / "state"), cfg, st, lane, v, res["t0"], res["t1"], tx, print)
res.setdefault("checks_original", res.get("checks"))
res["checks"] = [ck.CHECKS[x["type"]](c, x) for x in s.get("check", [])]
res["pass"] = all(x["pass"] for x in res["checks"] if x["required"])
res["regraded_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
if "--cleanup" in sys.argv:
    res["cleanup"] = res.get("cleanup", []) + [y for a in s.get("cleanup", []) for y in ck.ACTIONS[a["type"]](c, a)]
res_p.write_text(json.dumps(res, indent=2, default=str))
print(sid, var, "pass=", res["pass"], [(x["type"], x["pass"], json.dumps(x["detail"])[:300]) for x in res["checks"]])
