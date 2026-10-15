---
type: llm
---

PASS if the reply tells the user (1) to build the app once in a Workspace or Job (for example with
`scripts/build-dist.sh`) and save the build before publishing, after which app.sh only serves that build and
never runs npm; (2) to set the model endpoint URL and token as Domino Project environment variables read by the
backend, not as `VITE_` variables; and (3) how to roll back, by starting an earlier App version or by reverting
the code so the kept previous build is served again.
FAIL if it tells the user to run `npm ci` or `npm run build` inside app.sh, puts the model token in a `VITE_`
variable or the repository, or says nothing about rolling back.
