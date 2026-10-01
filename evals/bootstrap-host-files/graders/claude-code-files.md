---
type: llm
---

PASS if the plan says it will create or update `CLAUDE.md`, and register the Storybook MCP server in `.mcp.json` (mentioning `.claude/settings.local.json` is fine).
FAIL if it plans to create `AGENTS.md` or `.codex/config.toml` as the files it writes, or if it names neither `CLAUDE.md` nor `.mcp.json`.
