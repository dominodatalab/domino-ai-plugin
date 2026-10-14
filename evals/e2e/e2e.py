#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Live end-to-end harness for the Domino AI plugin.

A weak model runs Claude Code with a plugin build inside real Domino Workspaces; each scenario is graded by what
happened in Domino (Jobs, Datasets, Apps, experiments, endpoints, HPC Jobs), checked through the Domino API and in
the Workspace, plus transcript evidence. See README.md.

  uv run e2e.py provision [--lane dfs-0 ...]        # Projects, Datasets, Workspaces (started), Dom CLI SSH
  uv run e2e.py prep [--lane ...]                   # copy builds and remote scripts in, warm the MCP server
  uv run e2e.py run --run-dir runs/<name> [--scenario ID ...] [--variant V ...] [--project-type T]
  uv run e2e.py report runs/<name>                  # results.md: scenario x variant table and per-run detail
  uv run e2e.py teardown [--lane ...]               # stop/delete Workspaces, delete Datasets, archive Projects

The config is config.local.yaml next to this file, or -c PATH, or $E2E_CONFIG.
Secrets: the Domino token is minted in memory; the Claude OAuth token is read from the configured file and sent
to the remote `claude` process over SSH stdin only. Transcripts are redacted as they stream in.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from e2elib.domino import Domino, DominoError  # noqa: E402
from e2elib import remote as rm  # noqa: E402

STATE_DIR = HERE / "state"
STATE = STATE_DIR / "state.json"


def load_cfg(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"projects": {}, "workspaces": {}, "created": []}


def save_state(st: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(st, indent=2))


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def scenarios(sel=None) -> list[dict]:
    out = []
    for p in sorted((HERE / "scenarios").glob("*.yaml")):
        s = yaml.safe_load(p.read_text())
        s["_file"] = p.name
        if not sel or s["id"] in sel:
            out.append(s)
    return out


# ------------------------------------------------------------------------------------------------- provision
def lane_keys(cfg, args) -> list[str]:
    """Lanes are '<project_type>-<n>': one Project + Workspace each. Variant i runs in lane i (see runner)."""
    types = sorted({s["project_type"] for s in scenarios()})
    if getattr(args, "lane", None):
        return args.lane
    n = getattr(args, "lanes", None) or cfg["workspace"].get("lanes_per_type", len(cfg["plugin"]["variants"]))
    return [f"{t}-{i}" for t in types for i in range(n)]


def lane_type(key: str) -> str:
    return key.split("-")[0]


def cmd_provision(cfg, args):
    d = Domino(cfg["domino"])
    st = load_state()
    me = d.whoami()
    st["user"] = {"id": me.get("id"), "userName": me.get("userName")}
    stamp = time.strftime("%m%d%H%M")
    keys = lane_keys(cfg, args)
    for key in keys:
        t = lane_type(key)
        if key in st["projects"]:
            log(f"project {key} exists: {st['projects'][key]['name']}")
            continue
        name = f"{cfg['projects']['name_prefix']}-{key}-{stamp}"
        body = {"name": name, "description": "Scratch project for the Domino AI plugin end-to-end eval. Safe to delete.",
                "visibility": "Private"}
        if t == "git":
            g = cfg["projects"]["git_repo"]
            body["mainRepository"] = {"uri": g["uri"], "serviceProvider": g["service_provider"], "defaultRef": {"refType": "head"}}
        r = d.post("/api/projects/v2/projects", body)
        p = r.get("project", r)
        st["projects"][key] = {"id": p["id"], "name": p.get("name", name), "owner": p.get("ownerUsername") or me.get("userName"),
                               "datasets": {}, "type": t}
        st["created"].append({"kind": "project", "id": p["id"], "name": name})
        save_state(st)
        log(f"created project {key}: {name} {p['id']}")
        time.sleep(3)
        existing = {x.get("name"): x for x in d.datasets(p["id"])}
        for ds in cfg["projects"]["datasets"]:
            if ds in existing:
                dsid = existing[ds]["id"]
            else:
                r = d.post("/api/datasetrw/v1/datasets", {"name": ds, "projectId": p["id"], "description": "e2e eval scratch"})
                dsid = r.get("dataset", r)["id"]
                st["created"].append({"kind": "dataset", "id": dsid, "name": ds, "project": key})
            st["projects"][key]["datasets"][ds] = {"id": dsid}
        for x in d.datasets(p["id"]):  # record default datasets too (for teardown)
            if x.get("name") not in st["projects"][key]["datasets"]:
                st["projects"][key]["datasets"][x["name"]] = {"id": x["id"], "default": True}
        save_state(st)
    w = cfg["workspace"]
    for key in keys:
        if key in st["workspaces"]:
            continue
        pid = st["projects"][key]["id"]
        body = {"name": f"e2e-{key}", "environmentId": w["environment_id"], "hardwareTierId": {"value": w["hardware_tier"]},
                "tools": w["tools"], "externalVolumeMounts": [], "ssh": {"enabled": True},
                "persistence": {"persistPackages": False, "persistHomeDirectory": False}}
        r = d.post(f"/v4/workspace/project/{pid}/workspace", body)
        wid = r.get("id") or r.get("workspace", {}).get("id")
        st["workspaces"][key] = {"id": wid, "project_id": pid, "type": lane_type(key)}
        st["created"].append({"kind": "workspace", "id": wid, "project": key})
        save_state(st)
        log(f"created workspace {key}: {wid}")
    wait_running(d, st, cfg, keys)
    cmd_connect(cfg, args)


def ws_status(d, pid, wid):
    r = d.get(f"/v4/workspace/project/{pid}/workspace/{wid}")
    s = (r or {}).get("mostRecentSession") or {}
    return (s.get("sessionStatusInfo") or {}).get("rawExecutionDisplayStatus"), s.get("executionId")


def wait_running(d, st, cfg, keys=None):
    t0 = time.time()
    pending = {k: v for k, v in st["workspaces"].items() if keys is None or k in keys}
    while pending and time.time() - t0 < cfg["workspace"]["start_timeout_s"]:
        for t, w in list(pending.items()):
            s, eid = ws_status(d, w["project_id"], w["id"])
            if s == "Running":
                st["workspaces"][t]["execution_id"] = eid
                save_state(st)
                log(f"workspace {t} Running")
                pending.pop(t)
            elif s in ("Failed", "Error", "Stopped"):
                raise SystemExit(f"workspace {t} is {s}")
        if pending:
            time.sleep(15)
    if pending:
        raise SystemExit(f"workspaces not running after timeout: {list(pending)}")


def cmd_connect(cfg, args):
    st = load_state()
    w = cfg["workspace"]
    used = {x.get("port") for x in st["workspaces"].values()}
    for t, ws in st["workspaces"].items():
        r = rm.Remote(ws["id"], STATE_DIR)
        if ws.get("dom_pid") and _alive(ws["dom_pid"]) and rm.wait_ssh(r, timeout=20):
            log(f"ssh {t} ok (existing dom connect)")
            continue
        base = w.get("ssh_port_base", 2400) + 10 * len(used)
        port = rm.free_port(base)
        used.add(port)
        pid = rm.start_dom_connect(w["dom_cli"], ws["id"], w["ssh_user"], port, cfg["domino"]["host"], STATE_DIR / f"dom-{t}.log")
        ws.update({"dom_pid": pid, "port": port})
        save_state(st)
        time.sleep(5)
        if not rm.wait_ssh(r, timeout=300):
            raise SystemExit(f"ssh to {t} workspace failed; see {STATE_DIR}/dom-{t}.log")
        log(f"ssh {t} ok on port {port}")


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ------------------------------------------------------------------------------------------------- prep
def cmd_prep(cfg, args):
    st = load_state()
    root = cfg["remote"]["root"]
    for key, ws in st["workspaces"].items():
        if args.lane and key not in args.lane:
            continue
        t = lane_type(key)
        r = rm.Remote(ws["id"], STATE_DIR)
        r.push_dir(HERE / "remote", f"{root}/bin")
        r.sh(f"mkdir -p {cfg['remote']['run_root'][t]} && bash {root}/bin/reset.sh --baseline {cfg['remote']['run_root'][t]}")
        for name, local in cfg["plugin"]["builds"].items():
            dst = f"{root}/builds/{name}"
            r.push_dir((HERE / local).resolve(), dst)
            rc, out = r.sh(f"cd {dst}/mcp-servers/domino_mcp_server && timeout 300 uv sync -q 2>&1 | tail -3; echo rc=$?", timeout=400)
            log(f"{key}: pushed {name}; mcp uv sync: {out.strip()[-80:]}")
        rc, out = r.sh(f"mkdir -p {cfg['remote']['run_root'][t]} && claude --version && uv --version && python3 --version && "
                       "echo DOMINO_IS_GIT_BASED=$DOMINO_IS_GIT_BASED DOMINO_API_PROXY=${DOMINO_API_PROXY:+set} "
                       "DOMINO_HOST=${DOMINO_HOST:-unset} DOMINO_USER_API_KEY=${DOMINO_USER_API_KEY:+set} && "
                       "ls -d /domino/datasets/local/* /mnt/data/* 2>/dev/null; df -h /mnt | tail -1")
        log(f"{key}:\n{out}")
        # Where an image could carry Domino skills or plugins that would leak into a no-plugin run. The runner sets a
        # fresh CLAUDE_CONFIG_DIR per run, so only managed settings and Project-level .claude dirs could still apply.
        rc, inv = r.sh("for d in $HOME/.claude/skills $HOME/.claude/plugins /mnt/artifacts/.domino/.coding-assistants/.claude/skills "
                       "/etc/claude-code /mnt/.claude /mnt/code/.claude; do [ -e \"$d\" ] && echo \"present: $d\"; done; "
                       "find / -xdev \\( -path /proc -o -path /tmp/e2e -o -path /sys \\) -prune -o -name SKILL.md -print 2>/dev/null "
                       "| grep -i domino | grep -v '^/tmp/e2e' | head -5; echo inventory-done", timeout=300)
        ws["skill_inventory"] = [ln for ln in inv.splitlines() if ln and ln != "inventory-done"]
        log(f"{key}: Domino skill inventory outside the harness: {ws['skill_inventory'] or 'none'}")
        ws["datasets_dir"] = _datasets_dir(r, t, st)
        ws["dataset_paths"] = {}
        for name in cfg["projects"]["datasets"]:
            rc, out = r.sh(f'for p in "$DOMINO_DATASETS_DIR/local/{name}" "$DOMINO_DATASETS_DIR/{name}" "/mnt/data/{name}" '
                           f'"/domino/datasets/local/{name}"; do [ -d "$p" ] && echo "$p" && break; done')
            ws["dataset_paths"][name] = out.strip().splitlines()[-1] if out.strip() else ""
        log(f"{key}: dataset paths {ws['dataset_paths']}")
        save_state(st)


def _datasets_dir(r, t, st):
    rc, out = r.sh('echo "${DOMINO_DATASETS_DIR:-}"')
    v = out.strip().splitlines()[-1] if out.strip() else ""
    if v:
        return v
    return "/mnt/data" if t == "git" else f"/domino/datasets/local"


# ------------------------------------------------------------------------------------------------- run
def cmd_run(cfg, args):
    from e2elib.runner import run_matrix
    run_matrix(cfg, load_state(), args, HERE, STATE_DIR, scenarios(args.scenario))


def cmd_report(cfg, args):
    from e2elib.report import write_report
    write_report(Path(args.run_dir), scenarios())


# ------------------------------------------------------------------------------------------------- teardown
def cmd_teardown(cfg, args):
    d = Domino(cfg["domino"])
    st = load_state()
    done = []
    sel = set(args.lane or list(st["workspaces"]) + list(st["projects"]))
    wss = {k: v for k, v in st["workspaces"].items() if k in sel}
    prs = {k: v for k, v in st["projects"].items() if k in sel}
    for t, ws in wss.items():
        pid, wid = ws["project_id"], ws["id"]
        d.request("POST", f"/v4/workspace/project/{pid}/workspace/{wid}/stop", body={}, ok=None)
    for t, ws in wss.items():
        pid, wid = ws["project_id"], ws["id"]
        for _ in range(60):
            s, _e = ws_status(d, pid, wid)
            if s in (None, "Stopped", "Completed", "Failed", "Succeeded"):
                break
            time.sleep(10)
        for _ in range(8):  # delete right after stop often returns 500 "try again"
            code, _ = d.request("DELETE", f"/v4/workspace/project/{pid}/workspace/{wid}", ok=None, raw=True)
            if code == 200:
                break
            time.sleep(15)
        done.append(f"workspace {wid}: stop+delete HTTP {code}")
        if ws.get("dom_pid") and _alive(ws["dom_pid"]):
            os.kill(ws["dom_pid"], signal.SIGTERM)
            done.append(f"dom connect pid {ws['dom_pid']} killed")
        if rm.remove_ssh_host(wid):
            done.append(f"ssh Host {wid} removed from ~/.domino/ssh/config")
    for t, p in prs.items():
        for name, ds in p.get("datasets", {}).items():
            code, _ = d.request("DELETE", f"/api/datasetrw/v1/datasets/{ds['id']}", ok=None, raw=True)
            done.append(f"dataset {name} {ds['id']}: DELETE HTTP {code}")
        code, _ = d.request("DELETE", f"/api/projects/beta/projects/{p['id']}", ok=None, raw=True)
        done.append(f"project {p['name']} {p['id']}: archive HTTP {code}")
    for x in done:
        log(x)
    st.setdefault("teardown_log", []).append({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "lanes": sorted(sel), "log": done})
    for k in wss:
        st["workspaces"].pop(k, None)
    for k in prs:
        st.setdefault("retired_projects", {})[k] = st["projects"].pop(k)
    save_state(st)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default=os.environ.get("E2E_CONFIG", str(HERE / "config.local.yaml")))
    sub = ap.add_subparsers(dest="cmd", required=True)
    pv = sub.add_parser("provision")
    pv.add_argument("--lane", action="append", help="lane key such as dfs-0 (repeatable); default: every type x variant")
    pv.add_argument("--lanes", type=int, help="lanes per project type")
    sub.add_parser("connect")
    pp = sub.add_parser("prep")
    pp.add_argument("--lane", action="append")
    r = sub.add_parser("run")
    r.add_argument("--scenario", action="append")
    r.add_argument("--variant", action="append")
    r.add_argument("--project-type", action="append")
    r.add_argument("--run-dir")
    r.add_argument("--no-check", action="store_true")
    r.add_argument("--lane-of", action="append", help="VARIANT=LANE override, e.g. develop=dfs-1")
    rp = sub.add_parser("report")
    rp.add_argument("run_dir")
    td = sub.add_parser("teardown")
    td.add_argument("--lane", action="append", help="tear down only these lanes (default: all)")
    args = ap.parse_args()
    cfg = load_cfg(args.config)
    {"provision": cmd_provision, "connect": cmd_connect, "prep": cmd_prep, "run": cmd_run, "report": cmd_report,
     "teardown": cmd_teardown}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
