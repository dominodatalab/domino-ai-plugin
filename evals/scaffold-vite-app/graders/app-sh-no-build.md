---
type: regex
target: { source: file, path: app.sh }
match: not_contains
pattern: '\bnpm\s+(ci|i|install|run)\b|\bvite\s+build\b|\bnpx\b'
---
