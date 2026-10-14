"""Redaction and stream-json transcript parsing."""
from __future__ import annotations

import json
import re

_PATTERNS = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), "[REDACTED_ANTHROPIC_TOKEN]"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)(bearer\s+)(?!\[REDACTED)[A-Za-z0-9._\-~+/=]{20,}"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(CLAUDE_CODE_OAUTH_TOKEN[\"']?\s*=\s*[\"']?)(?!\[REDACTED|\$)[^\s\"'$}]{8,}"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(X-Domino-Api-Key[\"']?\s*[:=]\s*[\"']?)(?![\"'$]|\[REDACTED|\{)[A-Za-z0-9]{20,}"), r"\1[REDACTED]"),
]


class Redactor:
    def __init__(self, literals: list[str]):
        self.literals = [x for x in literals if x and len(x) >= 12]

    def __call__(self, s: str) -> str:
        for lit in self.literals:
            if lit in s:
                s = s.replace(lit, "[REDACTED_SECRET]")
        for pat, rep in _PATTERNS:
            s = pat.sub(rep, s)
        return s


def parse(lines: list[str], build_root: str | None = None) -> dict:
    """Summarise a Claude Code stream-json transcript."""
    out = {"init": {}, "tool_uses": [], "skills": [], "skill_files_read": [], "mcp_tools": [], "result": {},
           "assistant_turns": 0, "final_text": "", "subagents": [], "tool_io": []}
    by_id = {}
    last_text = ""
    for ln in lines:
        try:
            m = json.loads(ln)
        except json.JSONDecodeError:
            continue
        t = m.get("type")
        if t == "system" and m.get("subtype") == "init":
            out["init"] = {k: m.get(k) for k in ("model", "mcp_servers", "plugins", "skills", "slash_commands",
                                                 "permissionMode", "claude_code_version", "agents")}
            out["init"]["tools"] = m.get("tools")
        elif t == "assistant":
            msg = m.get("message", {})
            if not m.get("parent_tool_use_id"):
                out["assistant_turns"] += 1
            for c in msg.get("content", []) or []:
                if c.get("type") == "text" and not m.get("parent_tool_use_id"):
                    last_text = c.get("text", "")
                if c.get("type") != "tool_use":
                    continue
                name, inp = c.get("name", ""), c.get("input") or {}
                rec = {"name": name, "sub": bool(m.get("parent_tool_use_id"))}
                io = {"name": name, "input": json.dumps(inp)[:4000], "output": "", "is_error": False}
                by_id[c.get("id")] = io
                out["tool_io"].append(io)
                if name == "Skill":
                    sk = inp.get("skill") or inp.get("command") or inp.get("name")
                    rec["skill"] = sk
                    out["skills"].append(sk)
                elif name.startswith("mcp__"):
                    out["mcp_tools"].append(name)
                elif name in ("Task", "Agent"):
                    out["subagents"].append(inp.get("subagent_type"))
                elif name == "Read":
                    fp = inp.get("file_path", "")
                    mm = re.search(r"/skills/([^/]+)/([^/]+)$", fp)
                    if mm and (build_root is None or build_root in fp):
                        out["skill_files_read"].append(f"{mm.group(1)}/{mm.group(2)}")
                elif name == "Bash":
                    cmd = inp.get("command", "")
                    for mm in re.finditer(r"/skills/([\w\-]+)/([\w\-.]+\.md)", cmd):
                        out["skill_files_read"].append(f"{mm.group(1)}/{mm.group(2)}")
                    rec["cmd"] = cmd[:300]
                elif name in ("WebFetch", "WebSearch"):
                    rec["arg"] = (inp.get("url") or inp.get("query") or "")[:200]
                out["tool_uses"].append(rec)
        elif t == "user":
            cont = (m.get("message") or {}).get("content")
            for c in cont if isinstance(cont, list) else []:
                if c.get("type") == "tool_result" and c.get("tool_use_id") in by_id:
                    body = c.get("content")
                    if isinstance(body, list):
                        body = " ".join(x.get("text", "") for x in body if isinstance(x, dict))
                    by_id[c["tool_use_id"]]["output"] = str(body)[:8000]
                    by_id[c["tool_use_id"]]["is_error"] = bool(c.get("is_error"))
        elif t == "result":
            out["result"] = {k: m.get(k) for k in ("subtype", "is_error", "num_turns", "total_cost_usd", "duration_ms",
                                                   "duration_api_ms", "usage", "modelUsage")}
            out["final_text"] = m.get("result") or last_text
    if not out["final_text"]:
        out["final_text"] = last_text
    return out
