"""Condensed view of a redacted stream-json transcript: tool calls, truncated results, final reply."""
import json, sys
path = sys.argv[1]
width = int(sys.argv[2]) if len(sys.argv) > 2 else 400
n = 0
for ln in open(path):
    try:
        m = json.loads(ln)
    except json.JSONDecodeError:
        continue
    t = m.get("type")
    sub = "  [sub]" if m.get("parent_tool_use_id") else ""
    if t == "system" and m.get("subtype") == "init":
        print("INIT model=%s mcp=%s plugins=%s" % (m.get("model"), [(x["name"].split(":")[-1], x["status"]) for x in m.get("mcp_servers", [])],
                                                   [p.get("name") for p in m.get("plugins", []) or []]))
    elif t == "assistant":
        for c in m["message"].get("content", []):
            if c.get("type") == "text" and c.get("text", "").strip():
                print(f"--- TEXT{sub}: " + c["text"].strip()[:width].replace("\n", " | "))
            elif c.get("type") == "tool_use":
                n += 1
                inp = c.get("input") or {}
                s = inp.get("command") or inp.get("skill") or inp.get("file_path") or inp.get("url") or inp.get("query") or json.dumps(inp)
                print(f"#{n} {c['name']}{sub}: " + str(s)[:width].replace("\n", " | "))
    elif t == "user":
        cont = m["message"].get("content")
        if isinstance(cont, list):
            for c in cont:
                if c.get("type") == "tool_result":
                    body = c.get("content")
                    if isinstance(body, list):
                        body = " ".join(x.get("text", "") for x in body if isinstance(x, dict))
                    flag = " ERR" if c.get("is_error") else ""
                    print(f"   => {flag}" + str(body)[:width].replace("\n", " | "))
    elif t == "result":
        print(f"RESULT subtype={m.get('subtype')} turns={m.get('num_turns')} cost={m.get('total_cost_usd')} dur={m.get('duration_ms')}")
        print("FINAL: " + str(m.get("result"))[:3000])
