"""Scenario checks (graded by what happened in Domino) and cleanup actions.

Every check returns {"type", "pass", "required", "detail"}. A run passes when every required check passes.
Objects are attributed to a run by creation time inside the run window, so runs in one project are sequential.
"""
from __future__ import annotations

import base64
import fnmatch
import json
import re
import shlex
import time
import urllib.parse
import urllib.request

from .domino import Domino, ts_ms


class Ctx:
    def __init__(self, d: Domino, r, cfg: dict, st: dict, ptype: str, v: dict, t0: float, t1: float, tx: dict, log):
        self.d, self.r, self.cfg, self.st, self.ptype, self.v = d, r, cfg, st, ptype, v
        self.t0, self.t1, self.tx, self.log = t0, t1, tx, log
        self.pid = st["projects"][ptype]["id"]

    def in_window(self, t: float, slack: float = 5) -> bool:
        return self.t0 - slack <= t <= self.t1 + slack


def _res(spec, ok, detail):
    return {"type": spec["type"], "pass": bool(ok), "required": spec.get("required", True), "detail": detail}


# ---------------------------------------------------------------------------------------------------- jobs
def check_job_succeeded(c: Ctx, spec):
    jobs = [j for j in c.d.jobs(c.pid, 100) if c.in_window(ts_ms((j.get("stageTimes") or {}).get("submissionTime")))]
    if not jobs:
        return _res(spec, False, "no Job was started in this project during the run")
    deadline = time.time() + c.cfg["compute"]["job_timeout_s"]
    seen = []
    for j in jobs:
        jj = j
        while not (jj.get("status") or {}).get("isCompleted") and time.time() < deadline:
            time.sleep(10)
            jj = c.d.job(j["id"])
        st = (jj.get("status") or {}).get("executionStatus")
        out = c.d.job_stdout(j["id"]) if st == "Succeeded" else ""
        done_at = ts_ms((jj.get("stageTimes") or {}).get("completedTime"))
        seen.append({"id": j["id"], "number": j.get("number"), "command": j.get("runCommand"), "status": st,
                     "completed_before_session_end": bool(done_at) and done_at <= c.t1 + 5,
                     "hardwareTier": (jj.get("hardwareTier") or {}).get("id") if isinstance(jj.get("hardwareTier"), dict) else jj.get("hardwareTierId"),
                     "stdout_tail": out[-600:], "_out": out})
    rx = spec.get("stdout_regex")
    ok = [s for s in seen if s["status"] == "Succeeded" and (not rx or re.search(rx, s["_out"]))
          and (not spec.get("finished_before_reply") or s["completed_before_session_end"])]
    for s in seen:
        s.pop("_out", None)
    return _res(spec, bool(ok), {"jobs": seen, "matched": [s["id"] for s in ok]})


# ---------------------------------------------------------------------------------------------------- reply / transcript
def check_reply_regex(c: Ctx, spec):
    text = c.tx.get("final_text") or ""
    miss = [p for p in spec["patterns"] if not re.search(p, text)]
    return _res(spec, not miss, {"missing": miss, "reply_tail": text[-400:]})


def check_tool_used(c: Ctx, spec):
    names = [t["name"] for t in c.tx.get("tool_uses", [])]
    hit = [n for n in names if re.search(spec["name_regex"], n)]
    return _res(spec, bool(hit), {"matched": hit[:5], "mcp_tools": sorted(set(c.tx.get("mcp_tools", [])))})


def check_tool_io_regex(c: Ctx, spec):
    """Some tool call whose input matches input_regex returned output matching output_regex (evidence of a step)."""
    hits = [x for x in c.tx.get("tool_io", []) if re.search(spec["input_regex"], x["name"] + " " + x["input"])]
    good = [x for x in hits if re.search(spec["output_regex"], x["output"]) and not x["is_error"]
            and not (spec.get("output_not_regex") and re.search(spec["output_not_regex"], x["output"]))]
    if spec.get("expect") == "absent":       # pass only when no such call happened
        return _res(spec, not hits, {"matching_calls": len(hits), "first_call": hits[0]["input"][:200] if hits else None})
    return _res(spec, bool(good), {"matching_calls": len(hits), "successful": len(good),
                                   "first_call": hits[0]["input"][:200] if hits else None})


def check_no_domino_skills_visible(c: Ctx, spec):
    """Baseline guard: the session's init lists no Domino skill, slash command or plugin."""
    init = c.tx.get("init", {})
    names = [str(x) for x in (init.get("skills") or [])] + [str(x) for x in (init.get("slash_commands") or [])] + \
            [str(x.get("name") if isinstance(x, dict) else x) for x in (init.get("plugins") or [])]
    leaked = [n for n in names if re.search(r"(?i)domino", n)]
    return _res(spec, not leaked, {"leaked": leaked[:10], "skills_listed": len(init.get("skills") or [])})


def check_skill_loaded(c: Ctx, spec):
    """The model invoked a skill whose name matches skill_regex (Skill tool call)."""
    hits = [x["input"] for x in c.tx.get("tool_io", []) if x["name"] == "Skill" and re.search(spec["skill_regex"], x["input"])]
    return _res(spec, bool(hits), {"skills": c.tx.get("skills", [])})


def check_reply_not_regex(c: Ctx, spec):
    text = c.tx.get("final_text") or ""
    found = [m.group(0) for p in spec["patterns"] for m in [re.search(p, text)] if m]
    return _res(spec, not found, {"found": found, "reply_head": text[:300]})


def check_conditional_io(c: Ctx, spec):
    """If any tool call matches when_input_regex, each such call must match every require_input_regex, none of
    forbid_input_regex, and an earlier call must match before_input_regex. No matching call passes."""
    io = c.tx.get("tool_io", [])
    txt = [x["name"] + " " + x["input"] for x in io]
    idx = [i for i, t in enumerate(txt) if re.search(spec["when_input_regex"], t)]
    if not idx:
        return _res(spec, True, {"attempted": False})
    bad = []
    for i in idx:
        inp = io[i]["input"]
        miss = [r for r in spec.get("require_input_regex", []) if not re.search(r, inp)]
        forb = [r for r in spec.get("forbid_input_regex", []) if re.search(r, inp)]
        before = (not spec.get("before_input_regex")) or any(re.search(spec["before_input_regex"], t) for t in txt[:i])
        if miss or forb or not before:
            bad.append({"call": i, "missing": miss, "forbidden": forb, "preceded_by_upload": before, "input": inp[:300]})
    return _res(spec, not bad, {"attempted": True, "calls": len(idx), "problems": bad})


def check_nothing_started(c: Ctx, spec):
    """No standard Job, HPC Job or new Workspace was created in the Project during the run."""
    jobs = [j["id"] for j in c.d.jobs(c.pid, 100) if c.in_window(ts_ms((j.get("stageTimes") or {}).get("submissionTime")))]
    hpc = c.d.get("/api/hpc/v1/jobs", params={"projectId": c.pid, "limit": 50}, ok=None)
    hpc_jobs = (hpc.get("jobs") or []) if isinstance(hpc, dict) else []
    wss = c.d.get(f"/v4/workspace/project/{c.pid}/workspace", ok=None)
    wl = wss if isinstance(wss, list) else ((wss or {}).get("workspaces") or (wss or {}).get("items") or []) if isinstance(wss, (dict, list)) else []
    harness_ws = c.st["workspaces"].get(c.ptype, {}).get("id")
    new_ws = [w.get("id") for w in wl if isinstance(w, dict) and w.get("id") != harness_ws and c.in_window(ts_ms(w.get("createdAt")))]
    return _res(spec, not jobs and not hpc_jobs and not new_ws,
                {"jobs_started": jobs, "hpc_jobs": [h.get("id") for h in hpc_jobs], "workspaces_created": new_ws})


def check_script_lint(c: Ctx, spec):
    """Lint a script the model wrote: bash -n, required and forbidden patterns (outside #SBATCH lines where asked)."""
    path = spec["path"]
    rc, src = c.r.sh(f"cat {shlex.quote(path)}")
    if rc != 0:
        return _res(spec, False, {"error": f"{path} not found"})
    rc2, out2 = c.r.sh(f"bash -n {shlex.quote(path)} && echo SYNTAX_OK")
    body = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#SBATCH"))
    res = {"bash_n": "SYNTAX_OK" in out2}
    for name, rx in (spec.get("require") or {}).items():
        res[name] = bool(re.search(rx, src, re.M))
    for name, rx in (spec.get("require_in_body") or {}).items():
        res[name] = bool(re.search(rx, body, re.M))
    for name, rx in (spec.get("forbid") or {}).items():
        res[name] = not re.search(rx, src, re.M)
    found = []
    if spec.get("dataset_exists"):   # every Dataset the script names must exist in the Project (no placeholders)
        roots = r"(/domino/datasets/local|/mnt/data|\$\{?DOMINO_DATASETS_DIR\}?(?:/local)?)/"
        resolved = src     # substitute simple NAME=value assignments so D=/mnt/data/$DS resolves
        for var, val in re.findall(r"^\s*(?:export\s+)?([A-Za-z_]\w*)=[\"']?([A-Za-z0-9._-]+)[\"']?\s*(?:#.*)?$", src, re.M):
            resolved = re.sub(r"\$\{?" + var + r"\}?(?!\w)", val, resolved)
        names = re.findall(roots + r"([^/\s\"'$;)}]+)", resolved)
        placeholders = [n for _, n in names if re.search(r"[<>]", n)]
        for root, n in names:
            if re.search(r"[<>]", n) or n in ("snapshots", "local"):
                continue
            base = "/mnt/data" if root == "/mnt/data" else "/domino/datasets/local" if "local" in root else \
                ("/mnt/data" if c.ptype.startswith("git") else "/domino/datasets/local")
            rc3, out3 = c.r.sh(f"test -d {shlex.quote(base + '/' + n)} && echo EXISTS")
            found.append((n, "EXISTS" in out3))
        res["dataset_exists"] = bool(found) and all(ok for _, ok in found) and not placeholders
        if spec.get("template_name"):   # the skill's example name copied verbatim, and no such Dataset exists
            res["not_copied_template"] = not any(n == spec["template_name"] and not ok for n, ok in found)
    return _res(spec, all(res.values()), {"criteria": res, "lines": len(src.splitlines()),
                                          **({"datasets_named": found} if spec.get("dataset_exists") else {})})


# ---------------------------------------------------------------------------------------------------- files
def check_ws_file(c: Ctx, spec):
    roots = " ".join(shlex.quote(x) for x in ["/tmp", c.v["home"], "/mnt", "/domino"])
    rc, out = c.r.sh(f"find {roots} -name {shlex.quote(spec['name_glob'])} -type f -printf '%s %p\\n' 2>/dev/null; true",
                     timeout=300)
    files = []
    for ln in out.splitlines():
        parts = ln.split(" ", 1)
        if len(parts) == 2 and parts[0].isdigit():
            files.append((int(parts[0]), parts[1]))
    under = lambda p, roots: any(p == x or p.startswith(x.rstrip("/") + "/") for x in roots if x)  # noqa: E731
    good = [f for f in files if under(f[1], spec["must_be_under"]) and f[0] >= spec.get("min_bytes", 0)]
    bad = [f for f in files if under(f[1], spec.get("must_not_be_under", [])) and not under(f[1], spec["must_be_under"])]
    return _res(spec, bool(good) and not bad, {"found": files, "ok": good, "misplaced": bad})


def check_source_regex(c: Ctx, spec):
    rc, out = c.r.sh(f"cd {shlex.quote(c.v['run_dir'])} && for f in $(ls {spec.get('glob', '*.py')} 2>/dev/null); do "
                     "echo \"=== $f\"; cat \"$f\"; done")
    src = out
    miss = [p for p in spec.get("must_match", []) if not re.search(p, src)]
    bad = [p for p in spec.get("must_not_match", []) if re.search(p, src)]
    return _res(spec, bool(src.strip()) and not miss and not bad, {"missing": miss, "forbidden_found": bad,
                                                                    "files": re.findall(r"^=== (.+)$", src, re.M)})


def check_script_runs(c: Ctx, spec):
    rc, out = c.r.sh(f"cd {shlex.quote(c.v['run_dir'])} && timeout 180 {spec['cmd']}", timeout=240)
    miss = [p for p in spec.get("output_regex", []) if not re.search(re.escape(p) if spec.get("literal", True) else p, out)]
    return _res(spec, rc == 0 and not miss, {"rc": rc, "missing": miss, "output_tail": out[-600:]})


# ---------------------------------------------------------------------------------------------------- datasets
def check_snapshot_created(c: Ctx, spec):
    ds = c.st["projects"][c.ptype]["datasets"][spec["dataset"]]["id"]
    snaps = c.d.snapshots(ds)
    new = [s for s in snaps if c.in_window(ts_ms(s.get("createdAt") or s.get("creationTime")))]
    good = [s for s in new if str(s.get("status", "")).lower() in ("active", "pending", "copying")]
    return _res(spec, bool(good), {"new_snapshots": [{"id": s.get("id"), "status": s.get("status"),
                                                       "version": s.get("version")} for s in new]})


# ---------------------------------------------------------------------------------------------------- apps
def _apps(c: Ctx, name_regex):
    r = c.d.get("/api/apps/v1/apps", params={"projectId": c.pid, "limit": 100})
    items = r.get("items", []) if isinstance(r, dict) else []
    out = []
    for a in items:
        cv = a.get("currentVersion") or {}
        created = ts_ms(cv.get("createdAt")) or ts_ms(a.get("updatedAt"))
        if re.search(name_regex, a.get("name") or "") or c.in_window(created):
            out.append(a)
    return out


def _app_status(a):
    return ((a.get("currentVersion") or {}).get("currentInstance") or {}).get("status")


def check_app_running(c: Ctx, spec):
    deadline = time.time() + spec.get("wait_s", 600)
    while True:
        apps = _apps(c, spec["name_regex"])
        st = [(a["id"], a.get("name"), _app_status(a), a.get("url")) for a in apps]
        if any(s[2] == "Running" for s in st) or time.time() > deadline or (apps and all(s[2] in ("Failed", "Stopped", "Error") for s in st)):
            break
        if not apps and time.time() > c.t1 + 60:
            break
        time.sleep(15)
    return _res(spec, any(s[2] == "Running" for s in st), {"apps": st})


def check_app_url_ok(c: Ctx, spec):
    apps = [a for a in _apps(c, spec["name_regex"]) if _app_status(a) == "Running"]
    if not apps:
        return _res(spec, False, "no running app")
    url = apps[0].get("url") or ""
    if url.startswith("/"):
        url = c.d.host + url
    code, body = c.d.request("GET", "", url=url, ok=None, raw=True, headers={"Accept": "text/html"})
    return _res(spec, code == 200, {"url": url, "http": code, "note": "fetched with the harness bearer token"})


_TAG = re.compile(r"<(link|script)\b([^>]*)>", re.I)


def _attr(attrs, name):
    m = re.search(rf'\b{name}\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
    return m.group(1) if m else None


def _page_assets(html):
    """Stylesheets, module preloads and scripts the page loads. Icons are skipped: Domino's proxy inserts a
    /favicon.ico link that returns 404 on the Apps host for every App."""
    out = set()
    for tag, attrs in _TAG.findall(html):
        if tag.lower() == "script":
            ref = _attr(attrs, "src")
        else:
            rel = (_attr(attrs, "rel") or "").lower().split()
            ref = _attr(attrs, "href") if {"stylesheet", "modulepreload"} & set(rel) else None
        if ref:
            out.add(ref)
    return sorted(out)


def check_app_assets_ok(c: Ctx, spec):
    """The App page and every same-host stylesheet, module preload and script it references return 200 through
    Domino's App proxy. A page that loads but whose assets escape the App's URL prefix fails here."""
    apps = [a for a in _apps(c, spec["name_regex"]) if _app_status(a) == "Running"]
    if not apps:
        return _res(spec, False, "no running app")
    url = apps[0].get("url") or ""
    if url.startswith("/"):
        url = c.d.host + url
    code, page, html = c.d.fetch(url, "text/html")
    if code != 200:
        return _res(spec, False, {"url": url, "http": code})
    host = urllib.parse.urlsplit(page).netloc
    assets = {}
    for ref in _page_assets(html):
        target = urllib.parse.urljoin(page, ref)
        if urllib.parse.urlsplit(target).netloc == host:
            assets[ref] = c.d.fetch(target)[0]
    ok = len(assets) >= spec.get("min_assets", 1) and all(v == 200 for v in assets.values())
    return _res(spec, ok, {"page": page, "assets": assets})


def cleanup_delete_apps(c: Ctx, spec):
    done = []
    for a in _apps(c, spec["name_regex"]):
        cv = a.get("currentVersion") or {}
        if cv.get("id"):
            c.d.request("POST", f"/api/apps/v1/apps/{a['id']}/versions/{cv['id']}/stop", body={}, ok=None)
        code, _ = c.d.request("DELETE", f"/api/apps/v1/apps/{a['id']}", ok=None, raw=True)
        done.append(f"app {a['id']} {a.get('name')}: DELETE {code}")
    return done


# ---------------------------------------------------------------------------------------------------- model APIs
def _model_apis(c: Ctx, name_regex):
    r = c.d.get("/api/modelServing/v1/modelApis", params={"projectId": c.pid, "limit": 100}, ok=None)
    items = (r.get("items") or r.get("modelApis") or r.get("data") or []) if isinstance(r, dict) else (r or [])
    out = []
    for m in items:
        created = ts_ms((m.get("metadata") or {}).get("created"))
        if re.search(name_regex, m.get("name") or "") or c.in_window(created):
            out.append(m)
    return out


def check_model_api_predicts(c: Ctx, spec):
    deadline = c.t1 + spec.get("wait_s", 900)
    detail = {}
    while True:
        ms = _model_apis(c, spec["name_regex"])
        if not ms:
            return _res(spec, False, "no Model API created in this project during the run")
        m = c.d.get(f"/api/modelServing/v1/modelApis/{ms[0]['id']}")
        dep = ((m.get("activeVersion") or {}).get("deployment") or {})
        detail = {"id": m["id"], "name": m.get("name"), "status": dep.get("status"), "versions": len(ms)}
        if dep.get("status") in ("Running", "Failed", "Stopped") or time.time() > deadline:
            break
        time.sleep(20)
    if detail["status"] != "Running":
        if time.time() > deadline:
            detail["skipped"] = "deploy took longer than the wait budget"
        return _res(spec, False, detail)
    toks = [t.get("token") or t.get("accessToken") for t in ((m.get("access") or {}).get("accessTokens") or []) if isinstance(t, dict)]
    toks = [t for t in toks if t]
    url = f"{c.d.host}/models/{m['id']}/latest/model"
    hdr = {"Content-Type": "application/json"}
    if toks:
        hdr["Authorization"] = "Basic " + base64.b64encode(f"{toks[0]}:{toks[0]}".encode()).decode()
    req = urllib.request.Request(url, data=json.dumps(spec["payload"]).encode(), headers=hdr, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            code, body = resp.status, resp.read().decode()[:400]
    except urllib.error.HTTPError as e:
        code, body = e.code, e.read().decode()[:400]
    except Exception as e:  # noqa: BLE001
        code, body = 0, str(e)[:200]
    detail.update({"predict_http": code, "predict_body": body, "auth": "access token" if toks else "none"})
    return _res(spec, code == 200 and '"result"' in body, detail)


def delete_model_api(d: Domino, mid: str) -> str:
    """Stop every version's deployment (internal /v4 route), then archive (DELETE returns 500 while one runs)."""
    vs = d.get(f"/api/modelServing/v1/modelApis/{mid}/versions", ok=None)
    vids = [v["id"] for v in ((vs.get("items") or vs.get("versions") or []) if isinstance(vs, dict) else (vs or []))]
    for vid in vids:
        d.request("POST", f"/v4/models/{mid}/{vid}/stopModelDeployment", body={}, ok=None)
    code = 0
    for _ in range(12):
        code, _ = d.request("DELETE", f"/api/modelServing/v1/modelApis/{mid}", ok=None, raw=True)
        if code in (200, 204, 404):
            break
        time.sleep(15)
    return f"stopped {len(vids)} version(s), DELETE {code}"


def _model_logs(d: Domino, mid: str, vid: str) -> list[str]:
    r = d.get(f"/api/modelServing/v1/modelApis/{mid}/versions/{vid}/instanceLogs", params={"maxResults": 3000}, ok=None)
    out = []
    for x in (r.get("logs") or []) if isinstance(r, dict) else []:
        cn = next((t["value"] for t in x.get("tags", []) if t.get("key") == "kubernetes.container_name"), "")
        if cn.startswith("model-"):
            out.append(x.get("log", ""))
    return out


def check_model_api_healthy(c: Ctx, spec):
    """Endpoint built, Running, and its model container loaded the function (no crash loop)."""
    deadline = c.t1 + spec.get("wait_s", 900)
    while True:
        ms = _model_apis(c, spec["name_regex"])
        if not ms:
            return _res(spec, False, "no Model API created in this project during the run")
        m = c.d.get(f"/api/modelServing/v1/modelApis/{ms[0]['id']}")
        av = m.get("activeVersion") or {}
        st = (av.get("deployment") or {}).get("status")
        if st in ("Running", "Failed", "Stopped") or time.time() > deadline:
            break
        time.sleep(20)
    detail = {"id": m["id"], "name": m.get("name"), "status": st, "endpoints_in_window": len(ms)}
    if st != "Running":
        if time.time() > deadline:
            detail["skipped"] = "deploy took longer than the wait budget"
        return _res(spec, False, detail)
    time.sleep(60)                                   # a crash-looping container flips back to Starting
    st2 = ((c.d.get(f"/api/modelServing/v1/modelApis/{m['id']}").get("activeVersion") or {}).get("deployment") or {}).get("status")
    logs = _model_logs(c.d, m["id"], av["id"])
    ready = [i for i, ln in enumerate(logs) if "WSGI app 0" in ln and "ready" in ln]
    dead = [i for i, ln in enumerate(logs) if "no app loaded" in ln or "GAME OVER" in ln]
    healthy = st2 == "Running" and bool(ready) and (not dead or max(ready) > max(dead))
    err = next((ln for ln in reversed(logs) if "Error" in ln or "Traceback" in ln), "")
    detail.update({"status_after_60s": st2, "app_loaded": bool(ready), "crash_loop_markers": len(dead), "last_error": err[:200]})
    return _res(spec, healthy, detail)


def cleanup_delete_model_apis(c: Ctx, spec):
    return [f"model API {m['id']} {m.get('name')}: {delete_model_api(c.d, m['id'])}" for m in _model_apis(c, spec["name_regex"])]


# ---------------------------------------------------------------------------------------------------- MLflow (queried in the Workspace)
_MLFLOW_PY = r'''
import json, sys, warnings
warnings.filterwarnings("ignore")
from mlflow.tracking import MlflowClient
c = MlflowClient()
like = sys.argv[1]
out = []
for e in c.search_experiments(filter_string=f"name LIKE '{like}'", view_type=3):
    runs = c.search_runs([e.experiment_id], max_results=50)
    ntr = None
    try:
        import mlflow
        try:
            tr = mlflow.search_traces(locations=[e.experiment_id], max_results=50)
        except TypeError:
            tr = mlflow.search_traces(experiment_ids=[e.experiment_id], max_results=50)
        ntr = len(tr)
    except Exception as ex:
        ntr = "error: " + str(ex)[:120]
    out.append({"name": e.name, "id": e.experiment_id, "stage": e.lifecycle_stage,
                "runs": [{"id": r.info.run_id, "metrics": r.data.metrics} for r in runs], "traces": ntr})
print("MLFLOW_JSON=" + json.dumps(out))
'''


def _mlflow(c: Ctx, like):
    cmd = f"cd /tmp && python3 - {shlex.quote(like)} <<'PY'\n{_MLFLOW_PY}\nPY"
    rc, out = c.r.sh(cmd, timeout=180)
    m = re.search(r"^MLFLOW_JSON=(.*)$", out, re.M)
    return (json.loads(m.group(1)) if m else None), out[-500:]


def check_mlflow_runs(c: Ctx, spec):
    exps, raw = _mlflow(c, spec["experiment_like"])
    if exps is None:
        return _res(spec, False, {"error": raw})
    hits = [(e["name"], r["id"], r["metrics"].get(spec["metric"])) for e in exps for r in e["runs"]
            if r["metrics"].get(spec["metric"]) is not None and r["metrics"][spec["metric"]] >= spec.get("min_value", 0)]
    return _res(spec, bool(hits), {"experiments": [{"name": e["name"], "runs": len(e["runs"])} for e in exps], "hits": hits[:3]})


def check_mlflow_traces(c: Ctx, spec):
    exps, raw = _mlflow(c, spec["experiment_like"])
    if exps is None:
        return _res(spec, False, {"error": raw})
    n = sum(e["traces"] for e in exps if isinstance(e["traces"], int))
    return _res(spec, n >= spec.get("min_traces", 1),
                {"experiments": [{"name": e["name"], "runs": len(e["runs"]), "traces": e["traces"]} for e in exps]})


def cleanup_mlflow_delete_experiments(c: Ctx, spec):
    py = ("from mlflow.tracking import MlflowClient\nc=MlflowClient()\n"
          f"for e in c.search_experiments(filter_string=\"name LIKE '{spec['experiment_like']}'\"):\n"
          "    c.delete_experiment(e.experiment_id); print('deleted experiment', e.name)\n")
    rc, out = c.r.sh(f"cd /tmp && python3 - <<'PY'\n{py}\nPY", timeout=120)
    return [ln for ln in out.splitlines() if ln.startswith("deleted")] or [f"mlflow cleanup rc={rc}"]


# ---------------------------------------------------------------------------------------------------- shell / files
def action_ws_shell(c: Ctx, spec):
    rc, out = c.r.sh(spec["cmd"], timeout=spec.get("timeout_s", 300))
    return [f"ws_shell rc={rc}"]


def action_ws_file(c: Ctx, spec):
    p = spec["path"]
    data = spec["content"].encode()
    proc = c.r.run(f"mkdir -p $(dirname {shlex.quote(p)}) && cat > {shlex.quote(p)}", input=data, timeout=60)
    return [f"ws_file {p} rc={proc.returncode}"]


CHECKS = {k[len("check_"):]: v for k, v in globals().items() if k.startswith("check_")}
ACTIONS = {**{k[len("cleanup_"):]: v for k, v in globals().items() if k.startswith("cleanup_")},
           **{k[len("action_"):]: v for k, v in globals().items() if k.startswith("action_")}}
