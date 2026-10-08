# Security policy

## Reporting a vulnerability in this repository

Report it privately through GitHub:
[Report a vulnerability](https://github.com/dominodatalab/domino-ai-plugin/security/advisories/new).
Do not open a public issue, pull request or discussion for a suspected vulnerability.

In scope:

- The bundled MCP server under `mcp-servers/`.
- Skill content that would lead an agent to expose credentials, weaken access controls, run
  untrusted code, or send data somewhere the user did not intend.
- Manifests, install and update scripts, and CI workflows in this repository.

Please include the affected file or skill, the agent you used (Claude Code, Codex, ChatGPT,
Gemini CLI or Antigravity) and its version, the plugin version from `.claude-plugin/plugin.json`,
and steps to reproduce.

The maintainers listed in [MAINTAINERS.md](MAINTAINERS.md) acknowledge reports, agree a fix and a
disclosure date with the reporter, and publish a GitHub security advisory when the fix ships.

## Vulnerabilities in the Domino platform

This repository contains agent skills and an MCP server, not the Domino platform. For security
questions about Domino itself, see the [Domino Trust Center](https://trust.domino.ai/) or contact
Domino support through your account team.

## Supported versions

Only the latest release on `main` receives fixes. Release branches named `release-X.Y` receive
fixes only when the maintainers decide a backport is needed for that Domino line.
