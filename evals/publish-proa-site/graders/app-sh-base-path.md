---
type: regex
target: { source: file, path: app.sh }
match: contains
pattern: 'PROA_BASE_PATH="?\$\{?DOMINO_RUN_HOST_PATH'
---
