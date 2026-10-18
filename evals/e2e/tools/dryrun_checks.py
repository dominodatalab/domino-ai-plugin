#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Offline dry-run of scenario checks: real scenario YAML + real check code, mocked Domino/Workspace, synthetic
stream-json transcripts. Each case states whether the run should pass. usage: dryrun_checks.py"""
import copy, fnmatch, json, shlex, subprocess, sys, tempfile, time
from pathlib import Path
import yaml
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from e2elib import checks as ck, transcript as trx
from e2elib.runner import _tmpl

T0 = time.time() - 120; T1 = time.time()
class FakeD:
    host = "https://domino.example.com"
    def __init__(s, jobs=None, hpc=None, wss=None, apps=None, pages=None):
        s._jobs, s._hpc, s._wss, s._apps, s._pages = jobs or [], hpc or [], wss or [], apps or [], pages or {}
    def fetch(s, url, accept="*/*"):   # app_assets_ok: {url: (status, body)}; unknown URLs are 404
        code, body = s._pages.get(url, (404, ""))
        return code, url, body
    def jobs(s, pid, n): return s._jobs
    def get(s, path, params=None, ok=None):
        if path.startswith("/api/hpc/v1/jobs"): return {"jobs": s._hpc, "totalCount": len(s._hpc)}
        if path.startswith("/v4/workspace/project/"): return s._wss
        if path.startswith("/api/apps/v1/apps"): return {"items": s._apps}
        return {}
    def request(s, method, path, url=None, ok=None, raw=False, headers=None, **kw):   # app_url_ok
        return (200, "<html></html>") if s._apps else (404, "")
class FakeR:
    def __init__(s, files=None, dirs=("/domino/datasets/local/e2e-data", "/mnt/data/e2e-data")): s.files = files or {}; s.dirs = set(dirs)
    def sh(s, cmd, timeout=300):
        if cmd.startswith("test -d "):
            p = cmd[8:].split(" &&")[0].strip().strip("'"); return (0, "EXISTS") if p in s.dirs else (1, "")
        if cmd.startswith("cat "):
            p = cmd[4:].strip().strip("'"); return (0, s.files[p]) if p in s.files else (1, "No such file")
        if cmd.startswith("cd ") and "for f in $(ls " in cmd:   # source_regex: concatenate the named files
            rd = cmd[3:].split(" &&")[0].strip().strip("'")
            names = cmd.split("$(ls ", 1)[1].split(" 2>/dev/null")[0].split()
            return 0, "".join(f"=== {n}\n{s.files[rd + '/' + n]}\n" for n in names if rd + "/" + n in s.files)
        if cmd.startswith("find ") and " -name " in cmd:   # ws_file: files whose name matches the glob
            glob = shlex.split(cmd.split(" -name ", 1)[1])[0]
            return 0, "".join(f"{len(v)} {k}\n" for k, v in s.files.items() if fnmatch.fnmatch(k.rsplit("/", 1)[-1], glob))
        if cmd.startswith("bash -n "):
            p = cmd[8:].split(" &&")[0].strip().strip("'")
            if p not in s.files: return 1, ""
            with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f: f.write(s.files[p])
            rc = subprocess.run(["bash", "-n", f.name], capture_output=True).returncode
            return rc, "SYNTAX_OK" if rc == 0 else "syntax error"
        return 0, ""

def tr(calls, final, skills_in_init=()):
    """calls: list of (tool_name, input_dict, output_text)."""
    lines = [json.dumps({"type": "system", "subtype": "init", "model": "claude-haiku-5-5", "skills": list(skills_in_init),
                         "slash_commands": [], "plugins": [], "mcp_servers": [], "tools": []})]
    for i, (name, inp, out) in enumerate(calls):
        lines.append(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}]}}))
        lines.append(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": out}]}}))
    lines.append(json.dumps({"type": "result", "subtype": "success", "num_turns": len(calls) + 1, "total_cost_usd": 0.1, "result": final}))
    return trx.parse(lines)

def run(sid, build, tx, d=None, r=None, ptype=None):
    scen = yaml.safe_load((HERE / "scenarios" / f"{sid}.yaml").read_text())
    ptype = scen["project_type"]
    run_dir = f"/mnt{'/code' if ptype == 'git' else ''}/e2e-runs/{sid}-{build}-rdry"
    v = {"run_tag": "rdry", "run_dir": run_dir, "job_tier": "small-k8s", "dataset": "e2e-data", "dataset_id": "ds1",
         "datasets_dir": "/mnt/data" if ptype == "git" else "/domino/datasets",
         "dataset_path": "/mnt/data/e2e-data" if ptype == "git" else "/domino/datasets/local/e2e-data",
         "project_name": "p", "project_id": "pid", "username": "u", "home": "/home/ubuntu",
         "run_root": "/mnt/code/e2e-runs" if ptype == "git" else "/mnt/e2e-runs"}
    s = _tmpl(copy.deepcopy(scen), v)
    L = f"{ptype}-0"
    st = {"projects": {L: {"id": "pid", "datasets": {"e2e-data": {"id": "ds1"}}}}, "workspaces": {L: {"id": "harness-ws"}}}
    c = ck.Ctx(d or FakeD(), r or FakeR(), {"compute": {"job_timeout_s": 1}}, st, L, v, T0, T1, tx, lambda *a: None)
    checks = list(s.get("check", [])) + ([{"type": "no_domino_skills_visible"}] if build == "none" else [])
    out = []
    for x in checks:
        if x.get("only_builds") and build not in x["only_builds"]:
            continue
        rr = ck.CHECKS[x["type"]](c, x); out.append(rr)
    return all(o["pass"] for o in out if o["required"]), [(o["type"], o["pass"]) for o in out], s

SK = lambda n: ("Skill", {"skill": f"dominodatalab:{n}"}, f"Launching skill: dominodatalab:{n}")
SUP = ("Bash", {"command": 'curl -s "$DOMINO_API_PROXY/api/hpc/v1/jobs/submit-supported?projectId=$DOMINO_PROJECT_ID&dataPlaneId=000000000000000000000000"'}, '{"supported":false}')
PLANES = ("Bash", {"command": 'curl -s "$DOMINO_API_PROXY/v4/dataplanes/dataplanes"'}, '[{"id":"000000000000000000000000","name":"Local","isLocal":true,"status":{"supportsSlurm":false}}]')
SYNC = ("mcp__plugin_dominodatalab_domino_server__sync_local_file_to_domino", {"local_file_path": "/mnt/e2e-runs/x/hpc/sweep.sh", "domino_file_path": "hpc/sweep.sh"}, '{"success":true,"commitId":"abc"}')
def POST(fp="hpc/sweep.sh", cpu=4, wt="02:00:00"):
    body = json.dumps({"projectId": "pid", "filePath": fp, "dataPlaneId": "000000000000000000000000", "config": {"cpu": cpu, "walltime": wt}})
    return ("Bash", {"command": f"curl -s -X POST \"$DOMINO_API_PROXY/api/hpc/v1/jobs\" -H 'Content-Type: application/json' -d '{body}'"}, '{"errors":["(503) Unexpected response code"]}')
HONEST11 = ("No. This deployment has no Slurm-enabled data plane: submit-supported returned false and the only data plane (Local) "
            "has supportsSlurm false. To run your sbatch scripts an administrator needs a data plane deployed with Slurm, the Slurm "
            "client and worker environments, a worker hardware tier on that plane, and a Dataset as the shared file system.")
HONEST12 = "I could not submit it: HPC submission is not available on this deployment (submit-supported returned false). Nothing was created."
GOOD_SWEEP = {"dfs": "#!/bin/bash\n#SBATCH --array=0-9\numask 077\nD=/domino/datasets/local/e2e-data\nread -r LR DEPTH < <(sed -n \"$((SLURM_ARRAY_TASK_ID+1))p\" \"$D/params.txt\")\npython3 \"$D/train.py\" --lr \"$LR\" > \"$D/results/run_$SLURM_ARRAY_TASK_ID.txt\" 2>&1\n",
              "git": "#!/bin/bash\n#SBATCH --array=0-9\numask 077\nD=/mnt/data/e2e-data\nread -r LR DEPTH < <(sed -n \"$((SLURM_ARRAY_TASK_ID+1))p\" \"$D/params.txt\")\necho \"$LR $DEPTH\" | tee \"$D/results/run_$SLURM_ARRAY_TASK_ID.txt\"\n"}
BAD_SWEEP = "#!/bin/bash\n#SBATCH --array=0-9\n#SBATCH --output=/domino/datasets/local/e2e-data/out_%a.txt\nLR=$(sed -n \"${SLURM_ARRAY_TASK_ID}p\" /mnt/code/params.txt)\npython3 train.py --lr $LR\n"

cases = []
def case(name, expect, got):
    ok, detail, _ = got; cases.append((name, expect, ok, detail))

# s11
case("s11 next good", True, run("s11-hpc-availability", "next", tr([SK("domino-hpc-slurm"), SUP, PLANES], HONEST11)))
case("s11 next skill not loaded", False, run("s11-hpc-availability", "next", tr([SUP], HONEST11)))
case("s11 none good (no skill needed)", True, run("s11-hpc-availability", "none", tr([PLANES], HONEST11)))
case("s11 none claims yes, no API check", False, run("s11-hpc-availability", "none", tr([], "Yes, you can run them: Slurm is available here.")))
case("s11 none sees Domino skills (contamination)", False, run("s11-hpc-availability", "none", tr([PLANES], HONEST11, ["dominodatalab:domino-hpc-slurm"])))
case("s11 next good but created a Workspace", False, run("s11-hpc-availability", "next", tr([SK("domino-hpc-slurm"), SUP], HONEST11),
     d=FakeD(wss=[{"id": "new-ws", "createdAt": int(time.time() * 1000)}])))
# s12
case("s12 next refuses after submit-supported", True, run("s12-hpc-submit", "next", tr([SK("domino-hpc-slurm"), SUP], HONEST12)))
case("s12 next syncs then correct POST, honest", True, run("s12-hpc-submit", "next", tr([SK("domino-hpc-slurm"), SYNC, POST()], "The start failed with a 500 (503 Unexpected response code); Slurm is not available here, nothing was created.")))
case("s12 next POST without upload", False, run("s12-hpc-submit", "next", tr([SK("domino-hpc-slurm"), POST()], HONEST12)))
case("s12 next absolute filePath", False, run("s12-hpc-submit", "next", tr([SK("domino-hpc-slurm"), SYNC, POST(fp="/mnt/e2e-runs/x/hpc/sweep.sh")], HONEST12)))
case("s12 next wrong walltime", False, run("s12-hpc-submit", "next", tr([SK("domino-hpc-slurm"), SYNC, POST(wt="2:00")], HONEST12)))
case("s12 none falls back to slurm clusterType job", False, run("s12-hpc-submit", "none", tr([("Bash", {"command": 'curl -X POST "$DOMINO_API_PROXY/api/jobs/v1/jobs" -d \'{"projectId":"pid","runCommand":"bash hpc/sweep.sh","computeCluster":{"clusterType":"slurm"}}\''}, '{"job":{"id":"j1"}}')], "Submitted successfully; status: Queued."),
     d=FakeD(jobs=[{"id": "j1", "stageTimes": {"submissionTime": int(time.time() * 1000)}}])))
case("s12 next claims success / invents id", False, run("s12-hpc-submit", "next", tr([SK("domino-hpc-slurm"), SUP], "The HPC job was submitted successfully (job 6acd...). Status: Submitted.")))
# s13
for t in ("dfs", "git"):
    rd = f"/mnt{'/code' if t == 'git' else ''}/e2e-runs/s13-hpc-author-{t}-next-rdry/sweep.sbatch"
    case(f"s13 {t} next good script", True, run(f"s13-hpc-author-{t}", "next", tr([SK("domino-hpc-slurm")], "Saved sweep.sbatch."), r=FakeR({rd: GOOD_SWEEP[t]})))
    case(f"s13 {t} next bad script", False, run(f"s13-hpc-author-{t}", "next", tr([SK("domino-hpc-slurm")], "Saved."), r=FakeR({rd: BAD_SWEEP})))
    case(f"s13 {t} next wrong project-type path", False, run(f"s13-hpc-author-{t}", "next", tr([SK("domino-hpc-slurm")], "Saved."), r=FakeR({rd: GOOD_SWEEP['git' if t == 'dfs' else 'dfs']})))
    case(f"s13 {t} next syntax error", False, run(f"s13-hpc-author-{t}", "next", tr([SK("domino-hpc-slurm")], "Saved."), r=FakeR({rd: GOOD_SWEEP[t] + "if then\n"})))
    case(f"s13 {t} next placeholder Dataset (H3)", False, run(f"s13-hpc-author-{t}", "next", tr([SK("domino-hpc-slurm")], "Saved."),
         r=FakeR({rd: GOOD_SWEEP[t].replace("e2e-data", "<dataset-name>")})))
    case(f"s13 {t} next Dataset that does not exist", False, run(f"s13-hpc-author-{t}", "next", tr([SK("domino-hpc-slurm")], "Saved."),
         r=FakeR({rd: GOOD_SWEEP[t].replace("e2e-data", "my-data")})))
    case(f"s13 {t} next via $DOMINO_DATASETS_DIR", True, run(f"s13-hpc-author-{t}", "next", tr([SK("domino-hpc-slurm")], "Saved."),
         r=FakeR({rd: GOOD_SWEEP[t] + ("# also ${DOMINO_DATASETS_DIR}/local/e2e-data\n" if t == "dfs" else "# also $DOMINO_DATASETS_DIR/e2e-data\n")})))
    case(f"s13 {t} next copied template my-dataset", False, run(f"s13-hpc-author-{t}", "next", tr([SK("domino-hpc-slurm")], "Saved."),
         r=FakeR({rd: GOOD_SWEEP[t].replace("e2e-data", "my-dataset")})))
    case(f"s13 {t} next Dataset via variable", True, run(f"s13-hpc-author-{t}", "next", tr([SK("domino-hpc-slurm")], "Saved."),
         r=FakeR({rd: GOOD_SWEEP[t].replace("D=/domino/datasets/local/e2e-data", "DS=e2e-data\nD=/domino/datasets/local/$DS").replace("D=/mnt/data/e2e-data", "DS=\"e2e-data\"\nD=/mnt/data/${DS}")})))
    case(f"s13 {t} next file missing", False, run(f"s13-hpc-author-{t}", "next", tr([SK("domino-hpc-slurm")], "Saved."), r=FakeR({})))
# s14
case("s14 next MPI cluster", True, run("s14-mpi-disambiguation", "next", tr([SK("domino-distributed-computing")], "Use an MPI compute cluster attached to a Job: clusterType MPI with 4 GPU worker nodes, then run mpirun. Nothing launched yet.")))
case("s14 next routes to Slurm", False, run("s14-mpi-disambiguation", "next", tr([SK("domino-distributed-computing")], "Use an MPI cluster, or wrap it in an sbatch script and submit via /api/hpc/v1/jobs.")))

# s15
RD15 = "/mnt/code/e2e-runs/s15-rust-app-author-git-next-rdry"
GOOD_RUST = {"rust-toolchain.toml": '[toolchain]\nchannel = "1.99.1"\n',
             "Cargo.toml": '[lints.clippy]\npedantic = { level = "warn", priority = -1 }\n',
             ".gitignore": "/target/\n",
             "app.sh": '#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "$0")"\nexec "$run"\n'}
def rust(**over):
    files = {**GOOD_RUST, **over}
    return FakeR({f"{RD15}/{k}": v for k, v in files.items() if v is not None})
DONE15 = "Created the service; cargo clippy and the tests pass. Nothing was published."
case("s15 next good project", True, run("s15-rust-app-author-git", "next", tr([SK("domino-rust-apps")], DONE15), r=rust()))
case("s15 next app.sh compiles", False, run("s15-rust-app-author-git", "next", tr([SK("domino-rust-apps")], DONE15),
     r=rust(**{"app.sh": "#!/usr/bin/env bash\ncargo build --release && exec target/release/app\n"})))
case("s15 next floating stable channel", False, run("s15-rust-app-author-git", "next", tr([SK("domino-rust-apps")], DONE15),
     r=rust(**{"rust-toolchain.toml": '[toolchain]\nchannel = "stable"\n'})))
case("s15 next pedantic without priority", False, run("s15-rust-app-author-git", "next", tr([SK("domino-rust-apps")], DONE15),
     r=rust(**{"Cargo.toml": '[lints.clippy]\npedantic = "warn"\n'})))
case("s15 next skill not loaded", False, run("s15-rust-app-author-git", "next", tr([], DONE15), r=rust()))

# s17
GOOD_APP_SH = ('#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "$0")"\nwant=$(bash scripts/stamp.sh)\n'
               'export BUILD_DIR=dist/2026.10.15 APP_BUILD=2026.10.15\nexec node server.js\n')
RUNNING = [{"id": "a1", "name": "e2e-vite-rdry", "url": "/apps/x/",
            "currentVersion": {"currentInstance": {"status": "Running"}}}]
def vite(app_sh=GOOD_APP_SH, stamp=True, build="next"):
    RD17 = f"/mnt/e2e-runs/s17-vite-app-publish-dfs-{build}-rdry"
    files = {f"{RD17}/app.sh": app_sh}
    if stamp:
        files[f"{RD17}/dist/2026.10.15.stamp"] = "abc\nbuild=2026.10.15\n"
    return FakeR(files)
DONE17 = "Published e2e-vite-rdry; it is Running at https://apps.example/apps/x/."
case("s17 next good app", True, run("s17-vite-app-publish-dfs", "next", tr([SK("domino-app-init")], DONE17), d=FakeD(apps=RUNNING), r=vite()))
case("s17 next builds in app.sh", False, run("s17-vite-app-publish-dfs", "next", tr([SK("domino-app-init")], DONE17), d=FakeD(apps=RUNNING),
     r=vite(app_sh="#!/bin/bash\nset -e\nnpm ci && npm run build\nexec node server.js\n")))
case("s17 next serve via npx", False, run("s17-vite-app-publish-dfs", "next", tr([SK("domino-apps")], DONE17), d=FakeD(apps=RUNNING),
     r=vite(app_sh="#!/bin/bash\nexec npx serve -s dist -l 8888\n")))
case("s17 next no dated build", False, run("s17-vite-app-publish-dfs", "next", tr([SK("domino-app-init")], DONE17), d=FakeD(apps=RUNNING),
     r=vite(stamp=False)))
case("s17 next app not running", False, run("s17-vite-app-publish-dfs", "next", tr([SK("domino-app-init")], DONE17), d=FakeD(),
     r=vite()))
case("s17 next skill not loaded", False, run("s17-vite-app-publish-dfs", "next", tr([], DONE17), d=FakeD(apps=RUNNING), r=vite()))
case("s17 none good app", True, run("s17-vite-app-publish-dfs", "none", tr([], DONE17), d=FakeD(apps=RUNNING), r=vite(build="none")))

# s18: the App page and its assets are served under /apps/x/; Domino's injected /favicon.ico link 404s and is skipped
APP = "https://domino.example.com/apps/x/"
def page(css="/apps/x/static/styles.css", js="/apps/x/rsjs-runtime.js"):
    return (f'<html><head><link rel="icon" href="/favicon.ico"><link rel="stylesheet" href="{css}">'
            f'<script type="module" src="{js}"></script></head><body>Proa E2E rdry</body></html>')
GOOD_PAGES = {APP: (200, page()), APP + "static/styles.css": (200, "body{}"), APP + "rsjs-runtime.js": (200, "export {}")}
ROOT_PAGES = {APP: (200, page(css="/static/styles.css", js="/rsjs-runtime.js"))}   # URLs that escape the prefix
PROA_APP_SH = ('#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "$0")"\n# built with proa build in a Job\n'
               'export PORT=8888 PROA_HOST=0.0.0.0 PROA_BASE_PATH="${DOMINO_RUN_HOST_PATH:-}" RUST_LOG=info\nexec "$run"\n')
def proa(app_sh=PROA_APP_SH, build="next"):
    return FakeR({f"/mnt/code/e2e-runs/s18-proa-app-publish-git-{build}-rdry/site/app.sh": app_sh})
PROA_RUNNING = [{**RUNNING[0], "name": "e2e-proa-rdry"}]
DONE18 = "Published e2e-proa-rdry; it is Running at https://apps.example/apps/x/."
S18 = "s18-proa-app-publish-git"
case("s18 next good site", True, run(S18, "next", tr([SK("domino-rust-apps")], DONE18), d=FakeD(apps=PROA_RUNNING, pages=GOOD_PAGES), r=proa()))
case("s18 next assets escape the prefix", False, run(S18, "next", tr([SK("domino-rust-apps")], DONE18),
     d=FakeD(apps=PROA_RUNNING, pages=ROOT_PAGES), r=proa()))
case("s18 next only one asset", False, run(S18, "next", tr([SK("domino-rust-apps")], DONE18),
     d=FakeD(apps=PROA_RUNNING, pages={APP: (200, '<link rel="stylesheet" href="/apps/x/s.css">'), APP + "s.css": (200, "")}), r=proa()))
case("s18 next proa build in app.sh", False, run(S18, "next", tr([SK("domino-rust-apps")], DONE18), d=FakeD(apps=PROA_RUNNING, pages=GOOD_PAGES),
     r=proa(app_sh=PROA_APP_SH.replace('exec "$run"', 'proa build --locked\nexec target/release/site'))))
case("s18 next no base path", False, run(S18, "next", tr([SK("domino-rust-apps")], DONE18), d=FakeD(apps=PROA_RUNNING, pages=GOOD_PAGES),
     r=proa(app_sh=PROA_APP_SH.replace(' PROA_BASE_PATH="${DOMINO_RUN_HOST_PATH:-}"', ''))))
case("s18 next app not running", False, run(S18, "next", tr([SK("domino-rust-apps")], DONE18), d=FakeD(pages=GOOD_PAGES), r=proa()))
case("s18 next skill not loaded", False, run(S18, "next", tr([], DONE18), d=FakeD(apps=PROA_RUNNING, pages=GOOD_PAGES), r=proa()))
case("s18 none good site", True, run(S18, "none", tr([], DONE18), d=FakeD(apps=PROA_RUNNING, pages=GOOD_PAGES), r=proa(build="none")))

bad = 0
for name, expect, ok, detail in cases:
    flag = "ok " if ok == expect else "MISMATCH"; bad += ok != expect
    print(f"{flag} expect={'PASS' if expect else 'FAIL'} got={'PASS' if ok else 'FAIL'}  {name}  {detail if ok != expect or not ok else ''}")
print(f"\n{len(cases) - bad}/{len(cases)} cases graded as intended")
sys.exit(1 if bad else 0)
