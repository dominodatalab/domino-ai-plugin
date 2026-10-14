"""Run scenarios x variants: setup, remote Claude Code run (streamed, redacted), checks, cleanup."""
from __future__ import annotations

import copy
import json
import os
import re
import secrets
import shlex
import threading
import time
from pathlib import Path

from . import checks as ck
from . import transcript as tr
from .domino import Domino
from .remote import Remote

_lock = threading.Lock()


def _tmpl(obj, v: dict):
    if isinstance(obj, str):
        return re.sub(r"\{\{(\w+)\}\}", lambda m: str(v.get(m.group(1), m.group(0))), obj)
    if isinstance(obj, list):
        return [_tmpl(x, v) for x in obj]
    if isinstance(obj, dict):
        return {k: _tmpl(x, v) for k, x in obj.items()}
    return obj


def _read_token(cfg) -> str:
    with open(os.path.expanduser(cfg["claude"]["oauth_token_file"])) as f:
        return f.read().strip()


def remote_claude_cmd(cfg, run_dir: str, plugin_dir: str | None, cfg_dir: str, out: str, timeout_s: int) -> str:
    """Command line for remote/run-claude.sh (installed by `prep`). Holds no secrets: the token goes over stdin."""
    c = cfg["claude"]
    env = " ".join(f"{k}={shlex.quote(str(val))}" for k, val in (c.get("extra_env") or {}).items())
    args = [run_dir, cfg_dir, out, str(int(timeout_s)), c["model"], str(int(c["max_turns"]))] + ([plugin_dir] if plugin_dir else [])
    return f"env {env} bash {cfg['remote']['root']}/bin/run-claude.sh " + " ".join(shlex.quote(a) for a in args)


def stream_remote(r: Remote, out: str, red, sink, deadline: float, log) -> int | None:
    """Tail the redacted remote transcript with short SSH polls (tolerates tunnel drops). Returns the exit code."""
    off, buf, fails = 0, b"", 0
    q = shlex.quote(out)
    while True:
        try:
            p = r.run(f"cat {q}.rc 2>/dev/null; printf '\\n--E2E--\\n'; tail -c +{off + 1} {q} 2>/dev/null", timeout=120)
            ok = p.returncode == 0 and b"\n--E2E--\n" in p.stdout
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            fails += 1
            if fails > 30:
                log(f"lost the Workspace for too long while streaming {out}")
                return None
            time.sleep(10)
            continue
        fails = 0
        head, data = p.stdout.split(b"\n--E2E--\n", 1)
        off += len(data)
        buf += data
        *lines, buf = buf.split(b"\n")
        for ln in lines:
            sink(red(ln.decode("utf-8", "replace")))
        rc = head.strip().decode("utf-8", "replace")
        if rc:
            if buf:
                sink(red(buf.decode("utf-8", "replace")))
            return int(rc) if rc.lstrip("-").isdigit() else None
        if time.time() > deadline:
            r.run(f"pkill -TERM -s $(cat {q}.pid) 2>/dev/null; kill $(cat {q}.pid) 2>/dev/null", timeout=60)
            log(f"wall-clock limit hit, killed {out}")
            deadline = time.time() + 90
        time.sleep(5)


def lane_for(cfg, st, ptype: str, variant: str, overrides: dict | None = None) -> str:
    """Variant i of plugin.variants runs in lane '<ptype>-<i>' when it exists, else in the shared '<ptype>' lane."""
    if overrides and variant in overrides:
        return f"{ptype}-{overrides[variant]}" if not overrides[variant].startswith(ptype) else overrides[variant]
    allv = cfg["plugin"]["variants"]
    key = f"{ptype}-{allv.index(variant)}" if variant in allv else None
    return key if key in st["workspaces"] else ptype


def run_one(cfg, st, here: Path, out_root: Path, scen: dict, variant: str, log, do_check=True, lane: str | None = None) -> dict:
    ptype = scen["project_type"]
    lane = lane or lane_for(cfg, st, ptype, variant)
    ws = st["workspaces"][lane]
    r = Remote(ws["id"], here / "state")
    d = Domino(cfg["domino"])
    tag = "r" + secrets.token_hex(3)
    build = (cfg["plugin"].get("variant_build") or {}).get(variant, variant)   # repeats such as next-r2 -> next
    run_id = f"{scen['id']}-{variant}-{tag}"
    run_dir = f"{cfg['remote']['run_root'][ptype]}/{run_id}"
    proj = st["projects"][lane]
    ds_name = cfg["projects"]["datasets"][0]
    dsdir = ws.get("datasets_dir") or ("/mnt/data" if ptype == "git" else "/domino/datasets/local")
    v = {"run_tag": tag, "run_dir": run_dir, "job_tier": cfg["compute"]["job_tier"],
         "model_api_tier": cfg["compute"].get("model_api_tier", cfg["compute"]["job_tier"]),
         "dataset": ds_name, "dataset_id": proj["datasets"][ds_name]["id"], "datasets_dir": dsdir,
         "dataset_path": (ws.get("dataset_paths") or {}).get(ds_name) or f"{dsdir}/{ds_name}", "project_name": proj["name"], "project_id": proj["id"],
         "username": st["user"]["userName"], "home": "/home/" + cfg["workspace"]["ssh_user"],
         "run_root": cfg["remote"]["run_root"][ptype]}
    s = _tmpl(copy.deepcopy(scen), v)
    odir = out_root / scen["id"] / variant
    odir.mkdir(parents=True, exist_ok=True)
    res = {"scenario": scen["id"], "variant": variant, "build": build, "run_id": run_id, "run_tag": tag, "project_type": ptype,
           "lane": lane, "project": proj["name"], "workspace": ws["id"]}
    log(f"[{lane}] START {run_id}")
    # reset the shared Workspace to its baseline, then setup
    if cfg["remote"].get("reset_between_runs", True):
        r.sh(f"bash {cfg['remote']['root']}/bin/reset.sh {shlex.quote(cfg['remote']['run_root'][ptype])}", timeout=120)
    r.sh(f"mkdir -p {shlex.quote(run_dir)}")
    res["setup"] = []
    for a in s.get("setup", []):
        res["setup"] += ck.ACTIONS[a["type"]](ck.Ctx(d, r, cfg, st, lane, v, 0, 0, {}, log), a)
    # run
    plugin_dir = None if build == "none" else f"{cfg['remote']['root']}/builds/{build}"
    cfg_dir = f"{cfg['remote']['root']}/cc/{run_id}"
    timeout_s = int(s.get("timeout_s", cfg["claude"]["run_timeout_s"]))
    token = _read_token(cfg)
    red = tr.Redactor([token])
    out = f"{cfg['remote']['root']}/out/{run_id}.jsonl"
    cmd = remote_claude_cmd(cfg, run_dir, plugin_dir, cfg_dir, out, timeout_s)
    t0 = time.time()
    p = r.run(cmd, input=(token + "\n" + s["prompt"]).encode(), timeout=120)
    del token
    if b"STARTED" not in p.stdout:
        raise RuntimeError(f"remote start failed rc={p.returncode}: {p.stderr.decode()[-300:]}")
    lines = []
    with open(odir / "transcript.jsonl", "w") as f:
        def sink(ln):
            lines.append(ln)
            f.write(ln + "\n")
            f.flush()
        rc = stream_remote(r, out, red, sink, t0 + timeout_s + 60, log)
    _, err = r.sh(f"cat {shlex.quote(out)}.err 2>/dev/null | tail -c 20000; rm -f {shlex.quote(out)} {shlex.quote(out)}.rc "
                  f"{shlex.quote(out)}.err {shlex.quote(out)}.pid")
    (odir / "stderr.txt").write_text(red(err))
    t1 = time.time()
    tx = tr.parse(lines, build_root=plugin_dir)
    res.update({"t0": t0, "t1": t1, "wall_s": round(t1 - t0, 1), "exit_code": rc,
                "num_turns": tx["result"].get("num_turns"), "cost_usd": tx["result"].get("total_cost_usd"),
                "result_subtype": tx["result"].get("subtype"), "is_error": tx["result"].get("is_error"),
                "skills": tx["skills"], "skill_files_read": sorted(set(tx["skill_files_read"])),
                "mcp_tools": tx["mcp_tools"], "subagents": tx["subagents"],
                "mcp_servers": tx["init"].get("mcp_servers"), "model": tx["init"].get("model"),
                "tools_used": [t["name"] for t in tx["tool_uses"]], "final_text": tx["final_text"][-3000:],
                "init_skills": [x for x in (tx["init"].get("skills") or []) if isinstance(x, str)],
                "init_plugins": [(x.get("name") if isinstance(x, dict) else x) for x in (tx["init"].get("plugins") or [])]})
    log(f"[{lane}] ran {run_id}: {res['wall_s']}s turns={res['num_turns']} cost={res['cost_usd']} "
        f"skills={res['skills']} mcp={sorted(set(res['mcp_tools']))}")
    # checks
    ctx = ck.Ctx(d, r, cfg, st, lane, v, t0, t1, tx, log)
    res["checks"] = []
    if do_check:
        checks = list(s.get("check", []))
        if build == "none":   # a no-plugin run must not see Domino skills from the image or the Project
            checks.append({"type": "no_domino_skills_visible", "required": True})
        for c in checks:
            if c.get("only_builds") and build not in c["only_builds"]:
                res["checks"].append({"type": c["type"], "pass": True, "required": False, "detail": "skipped for this build"})
                continue
            try:
                res["checks"].append(ck.CHECKS[c["type"]](ctx, c))
            except Exception as e:  # noqa: BLE001
                res["checks"].append({"type": c["type"], "pass": False, "required": c.get("required", True),
                                      "detail": f"check error: {type(e).__name__}: {str(e)[:300]}"})
        res["pass"] = all(x["pass"] for x in res["checks"] if x["required"])
    # cleanup
    res["cleanup"] = []
    for a in s.get("cleanup", []):
        try:
            res["cleanup"] += ck.ACTIONS[a["type"]](ctx, a)
        except Exception as e:  # noqa: BLE001
            res["cleanup"].append(f"cleanup error {a['type']}: {e}")
    (odir / "result.json").write_text(json.dumps(res, indent=2, default=str))
    log(f"[{lane}] DONE {run_id}: pass={res.get('pass')} " +
        "; ".join(f"{x['type']}={'ok' if x['pass'] else 'FAIL'}" for x in res["checks"]))
    with _lock:
        with open(out_root / "results.jsonl", "a") as f:
            f.write(json.dumps({k: res[k] for k in res if k not in ("final_text",)}, default=str) + "\n")
    return res


def run_matrix(cfg, st, args, here: Path, state_dir: Path, scens: list[dict]):
    out_root = Path(args.run_dir) if args.run_dir else here / "runs" / time.strftime("%Y%m%d-%H%M%S")
    out_root.mkdir(parents=True, exist_ok=True)
    variants = args.variant or cfg["plugin"]["variants"]
    types = args.project_type or sorted({s["project_type"] for s in scens})
    logf = open(out_root / "harness.log", "a")

    def log(msg):
        line = time.strftime("%H:%M:%S ") + msg
        with _lock:
            print(line, flush=True)
            logf.write(line + "\n")
            logf.flush()

    overrides = dict(x.split("=", 1) for x in (getattr(args, "lane_of", None) or []))
    jobs: dict[str, list] = {}
    for s_ in scens:
        if s_["project_type"] not in types:
            continue
        for var in variants:
            jobs.setdefault(lane_for(cfg, st, s_["project_type"], var, overrides), []).append((s_, var))

    def worker(lane, items):
        for s_, var in items:
            try:
                run_one(cfg, st, here, out_root, s_, var, log, do_check=not args.no_check, lane=lane)
            except Exception as e:  # noqa: BLE001
                log(f"[{lane}] ERROR {s_['id']} {var}: {type(e).__name__}: {e}")

    log("lanes: " + "; ".join(f"{k}: {len(v)} runs" for k, v in jobs.items()))
    th = [threading.Thread(target=worker, args=(k, v)) for k, v in jobs.items()]
    for t in th:
        t.start()
    for t in th:
        t.join()
    log(f"all done: {out_root}")
