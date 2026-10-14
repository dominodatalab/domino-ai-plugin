"""Summarise a run directory: results.jsonl -> results.md (scenario x variant table and per-run detail)."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def load(run_dir: Path) -> list[dict]:
    out = {}
    for p in sorted(run_dir.glob("*/*/result.json")):
        r = json.loads(p.read_text())
        out[(r["scenario"], r["variant"])] = r  # latest result per scenario/variant wins
    return list(out.values())


def cell(r):
    if r is None:
        return "-"
    mark = "PASS" if r.get("pass") else "FAIL"
    cost = f"${r['cost_usd']:.2f}" if isinstance(r.get("cost_usd"), (int, float)) else "?"
    return f"{mark} ({r.get('num_turns')}t, {cost}, {int(r.get('wall_s') or 0)}s)"


def write_report(run_dir: Path, scens: list[dict]) -> Path:
    rs = load(run_dir)
    by = {(r["scenario"], r["variant"]): r for r in rs}
    order = ["next", "next-r2", "main", "develop", "none"]
    present = sorted({r["variant"] for r in rs}, key=lambda v: (order.index(v) if v in order else 99, v))
    variants = present
    lines = [f"# Results: {run_dir.name}", "", "| Scenario | " + " | ".join(variants) + " |",
             "|---|" + "---|" * len(variants)]
    tot = defaultdict(lambda: [0, 0, 0.0, 0.0])
    for s in scens:
        if not any((s["id"], v) in by for v in variants):
            continue
        lines.append(f"| {s['id']} | " + " | ".join(cell(by.get((s["id"], v))) for v in variants) + " |")
        for v in variants:
            r = by.get((s["id"], v))
            if r:
                t = tot[v]
                t[0] += 1
                t[1] += 1 if r.get("pass") else 0
                t[2] += r.get("cost_usd") or 0
                t[3] += r.get("wall_s") or 0
    lines.append("| **Pass rate** | " + " | ".join(f"**{tot[v][1]}/{tot[v][0]}** (${tot[v][2]:.2f}, {tot[v][3]/60:.0f} min)"
                                               for v in variants) + " |")
    lines += ["", "## Per run", ""]
    for r in sorted(rs, key=lambda x: (x["scenario"], variants.index(x["variant"]) if x["variant"] in variants else 9)):
        lines.append(f"### {r['scenario']} / {r['variant']}: {'PASS' if r.get('pass') else 'FAIL'}")
        lines.append(f"- run `{r['run_id']}`; turns {r.get('num_turns')}; cost {r.get('cost_usd')}; wall {r.get('wall_s')} s; "
                     f"result `{r.get('result_subtype')}`")
        lines.append(f"- skills (Skill tool): {r.get('skills') or 'none'}; skill files read: {r.get('skill_files_read') or 'none'}")
        lines.append(f"- MCP tools: {sorted(set(r.get('mcp_tools') or [])) or 'none'}; subagents: {r.get('subagents') or 'none'}")
        for c in r.get("checks", []):
            det = json.dumps(c["detail"], default=str)
            lines.append(f"- check `{c['type']}`{'' if c['required'] else ' (optional)'}: {'ok' if c['pass'] else 'FAIL'}: "
                         f"{det[:500]}")
        lines.append("")
    p = run_dir / "results.md"
    p.write_text("\n".join(lines))
    print(p)
    return p
