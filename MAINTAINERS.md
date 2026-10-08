# Maintainers

This file says who is accountable for this repository. Review routing is a separate thing:
[`.github/CODEOWNERS`](.github/CODEOWNERS) names the reviewers for every skill and every other
path, and branch protection requires one of them to approve a change. Maintainers own the
repository as a whole: its release process, its CI, its standards and its security response.

Domino Data Lab owns and governs this repository.

## Current maintainers

| Name | GitHub | Role | Responsible for |
|---|---|---|---|
| Theo Linnemann | [@DDL-Theo-Linnemann](https://github.com/DDL-Theo-Linnemann) | Lead maintainer | Releases, CI, contribution standards, default owner of every path |
| AJ Rossman | [@ddl-aj-rossman](https://github.com/ddl-aj-rossman) | Maintainer | OpenAI distribution: portable manifest, listing assets, package build |
| Bira Ignacio | [@ddl-bira-ignacio](https://github.com/ddl-bira-ignacio) | Maintainer | Domino API, SDK and MCP server skills |

## Roles

- **Lead maintainer.** Owns the release process (`develop` to `main` promotion, version bumps,
  tags and GitHub Releases), branch protection and CI. Breaks ties. Is the default code owner,
  so any path without a more specific owner routes to the lead.
- **Maintainer.** Has admin or write access, reviews and merges within their area, and can cut a
  release with the lead's agreement.
- **Area reviewer.** Listed in `CODEOWNERS` for one or more skills. Reviews changes to those
  skills for product accuracy against the Domino version they claim. Area reviewers are the
  product and engineering owners of the matching docs.domino.ai sections.

## Responsibilities

Maintainers aim to:

- Respond to pull requests in their area within five business days, even if only to say when a
  full review will happen.
- Triage new issues within five business days: label them, close support requests with a pointer
  to [SUPPORT.md](SUPPORT.md), and route skill problems to the skill's code owners.
- Handle vulnerability reports under [SECURITY.md](SECURITY.md).
- Keep skills current: when a Domino release changes a feature, the skill's code owners update the
  skill or open an issue for it before the release ships to customers.
- Hold the standards in [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md), including
  the model-attestation requirement, which only a human may tick.

## Becoming a maintainer or area reviewer

Ask the lead maintainer, or be nominated by an existing maintainer. Area reviewers are normally the
people who own the matching product area in Domino's documentation. Write access is granted through
Domino IT; the access change and the `CODEOWNERS` (and, for maintainers, this file) update go in
together.

## Stepping down

Maintainers and reviewers can step down at any time by opening a PR that removes them from this file
and from `CODEOWNERS`. Someone with no review activity for six months may be moved to the emeritus
list below by the lead maintainer, after asking them.

## Emeritus

None yet.

## Decisions and escalation

Changes inside one area are decided by that area's code owners. Cross-cutting changes (release
scheme, repository layout, supported agents, standards) are decided by the maintainers, with the lead
maintainer deciding when there is no agreement.

## Contact

- Bugs and feature requests: [GitHub issues](https://github.com/dominodatalab/domino-ai-plugin/issues).
- Help using Domino: see [SUPPORT.md](SUPPORT.md).
- Security: see [SECURITY.md](SECURITY.md). Do not open a public issue.
