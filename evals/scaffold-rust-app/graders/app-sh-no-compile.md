---
type: regex
target: { source: file, path: app.sh }
match: not_contains
pattern: 'cargo\s+(\+\S+\s+)?(build|run|install)'
---
