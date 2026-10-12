---
type: regex
target: { source: file, path: flow.py }
match: not_contains
flags: m
pattern: '^(?!\s*#)[^\n]*\)\s*\[\s*[\x27"]\w+[\x27"]\s*\]'
---
